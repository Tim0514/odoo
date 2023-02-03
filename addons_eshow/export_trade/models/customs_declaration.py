import base64
import logging
import datetime
from io import BufferedReader, BytesIO

from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError
from odoo.tools import float_compare
import pdfplumber

_logger = logging.getLogger(__name__)


class CustomsDeclaration(models.Model):
    _name = "sale.customs.declaration"
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin', 'utm.mixin']
    _description = "Customs Declaration"
    _order = "name"
    _check_company_auto = True

    @api.model
    def _default_currency_id(self):
        return self.env['res.currency'].sudo().name_search('USD')[0]

    STATES = [
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('done', 'Locked'),
        ('cancel', 'Cancelled')
    ]

    READONLY_STATES = {
        'draft': [('readonly', False)],
        'confirmed': [('readonly', True)],
        'done': [('readonly', True)],
        'cancel': [('readonly', True)],
    }

    company_id = fields.Many2one('res.company', 'Company', required=True, index=True, states=READONLY_STATES,
                                 default=lambda self: self.env.company.id)

    name = fields.Char(
        string="Reference", required=True, copy=False,
        readonly=True, states={'draft': [('readonly', False)]}, index=True,
        default=lambda self: _('New')
    )

    customs_declaration_number = fields.Char(
        string="Customs Declaration Number",
        index=True,
    )

    partner_id = fields.Many2one(
        'res.partner', string='Customer', states=READONLY_STATES,
        change_default=True, tracking=True, domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]")

    create_date = fields.Datetime(string='Creation Date', default=fields.Datetime.now, readonly=True, index=True,
                                  help="Date on which document is created.")

    declare_date = fields.Datetime(
        string='Declare Date', required=True, states=READONLY_STATES, index=True, copy=False,
        default=fields.Datetime.now, help="Date when products are declared to customs.")

    # amount_total = fields.Monetary(compute='_compute_amount', string='Total', readonly=True)
    amount_total = fields.Monetary(compute='_compute_amount', string='Total', store=True, readonly=True)

    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        store=True, ondelete="restrict", default=_default_currency_id)

    state = fields.Selection(selection=STATES, string='Status', readonly=True, index=True, copy=False, default='draft',
                             tracking=True)

    note = fields.Html('Notes')

    customs_declaration_file = fields.Binary(string='Document', attachment=True, copy=False)
    customs_declaration_file_name = fields.Char(string='Document File Name')

    customs_declaration_line_ids = fields.One2many(
        'sale.customs.declaration.line', 'customs_declaration_id', string='Customs Declaration Lines')

    customs_declaration_stock_move_ids = fields.One2many(
        'sale.customs.declaration.stock.move', 'customs_declaration_id', string='Customs Declaration Stock Moves')

    # Used to search on pickings
    product_id = fields.Many2one('product.product', 'Product', related='customs_declaration_line_ids.product_id',
                                 readonly=True)

    _sql_constraints = [(
        'unique_name',
        'UNIQUE(name)',
        "Reference must be unique."
    )]

    @api.depends('customs_declaration_line_ids.product_qty')
    def _compute_amount(self):
        for declaration in self:
            amount_total = 0.0
            for line in declaration.customs_declaration_line_ids:
                line._compute_amount()
                amount_total += line.total_declare_price
            declaration.update({
                'amount_total': amount_total,
            })

    @api.model
    def create(self, vals):
        company_id = vals.get('company_id', self.default_get(['company_id'])['company_id'])
        # Ensures default picking type and currency are taken from the right company.
        self_comp = self.with_company(company_id)
        if vals.get('name', _("New")) == _("New"):
            seq_date = None
            if 'create_date' in vals:
                seq_date = fields.Datetime.context_timestamp(self, fields.Datetime.to_datetime(vals['create_date']))
            vals['name'] = self_comp.env['ir.sequence'].next_by_code('sale.customs.declaration',
                                                                     sequence_date=seq_date) or '/'
        res = super(CustomsDeclaration, self_comp).create(vals)
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_if_cancelled(self):
        for declaration in self:
            if not declaration.state in ['draft', 'cancel']:
                raise UserError(_('In order to delete a customs declaration, you must cancel it first.'))

    def unlink(self):
        stock_moves = self.customs_declaration_stock_move_ids.stock_move_id
        super(CustomsDeclaration, self).unlink()
        stock_moves._compute_undeclared_qty()

    def action_cancel(self):
        for customs_declaration_stock_move_ids in self.customs_declaration_stock_move_ids:
            customs_declaration_stock_move_ids.write({'product_qty': 0})
        self.write({'state': 'cancel'})

    def action_confirm(self):
        for customs_declaration in self:
            if len(customs_declaration.customs_declaration_line_ids) == 0:
                raise UserError(_('Products not found in customs declaration: %s') % customs_declaration.name)
        self.write({'state': 'confirmed'})

    def action_done(self):
        for customs_declaration in self:
            if customs_declaration.customs_declaration_number is False:
                raise UserError(_('Number can not be empty in customs declaration: %s') % customs_declaration.name)
            if customs_declaration.declare_date is False:
                raise UserError(
                    _('Declare date can not be empty in customs declaration: %s') % customs_declaration.name)
            if customs_declaration.customs_declaration_file is False:
                raise UserError(_('File can not be empty in customs declaration: %s') % customs_declaration.name)
        self.write({'state': 'done'})

    def action_draft(self):
        self.write({'state': 'draft'})

    @api.onchange('customs_declaration_file')
    def _process_customs_declaration_file(self):
        for declaration in self:
            if declaration.customs_declaration_file:
                b_handle = BytesIO()
                b_handle.write(base64.decodebytes(declaration.customs_declaration_file))

                # This is important.
                b_handle.seek(0)

                br = BufferedReader(b_handle)

                err_msg = False

                try:
                    with pdfplumber.open(br) as pdf_file:
                        first_page = pdf_file.pages[0]
                        # 提取字符串
                        text = first_page.extract_text()

                        # 判断文件是否报关单
                        if text.split('\n')[0] != '中华人民共和国海关出口货物报关单':
                            err_msg = _('Can not get customs declaration info from the document, '
                                        'you must input the data yourself.')
                        else:
                            try:
                                # 报关单号
                                customs_declaration_number = text.split('\n')[2].split(' ')[1].split('：')[1]
                            except:
                                customs_declaration_number = False
                                err_msg = _('Can not get customs declaration number from the document, '
                                            'you must input the data yourself.')

                            try:
                                the_date = text.split('\n')[4].split(' ')

                                if len(the_date) < 4:
                                    # 申报日期
                                    declare_date = the_date[2]
                                    # # 出口日期
                                    # export_date = False
                                else:
                                    # 申报日期
                                    declare_date = text.split('\n')[4].split(' ')[3]
                                    # # 出口日期
                                    # export_date = text.split('\n')[4].split(' ')[2]

                                if declare_date:
                                    try:
                                        declare_date = datetime.datetime.strptime(declare_date, '%Y%m%d')
                                    except:
                                        declare_date = False

                                # if export_date:
                                #     try:
                                #         export_date = datetime.datetime.strptime(declare_date, '%Y%m%d')
                                #     except:
                                #         export_date = export_date

                            except:
                                err_msg = _('Can not get declare date from the document, '
                                            'you must input the data yourself.')
                except:
                    err_msg = _('Can not get customs declaration info from the document, '
                                'you must input the data yourself.')
                if err_msg:
                    return {
                        'warning':
                            {
                                'title': 'Warning',
                                'message': err_msg,
                            }
                    }
                else:
                    declaration.write(
                        {'customs_declaration_number': customs_declaration_number, 'declare_date': declare_date})


class CustomsDeclarationLine(models.Model):
    _name = "sale.customs.declaration.line"
    _description = "Customs Declaration Line"
    _order = "customs_declaration_id, product_id"

    name = fields.Text(string='Description')
    product_id = fields.Many2one(
        'product.product', string='Product', readonly=True, required=True, )
    sequence = fields.Integer(string='Sequence', default=10)
    unit_cost = fields.Float(string='Unit Cost', required=True, digits='Product Price')
    unit_declare_price = fields.Float(string='Unit Declare Price', required=True, digits='Product Price')

    product_qty = fields.Float(
        string='Quantity', digits='Product Unit of Measure', required=True, default=0, readonly=True,
        store=True, compute='_compute_amount')
    product_uom = fields.Many2one('uom.uom', related='product_id.uom_id', string='Unit of Measure', required=True)

    weight_total = fields.Float('Total Weight', digits='Stock Weight', required=True, default=0)

    total_cost = fields.Monetary(string='Total Cost', currency_field='cost_currency_id', store=True, readonly=True)
    total_declare_price = fields.Monetary(string='Total Declare Price', store=True, readonly=True)

    line_note = fields.Html('Line Notes')

    customs_declaration_id = fields.Many2one('sale.customs.declaration', string='Customs Declaration Reference',
                                             index=True, required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', related='customs_declaration_id.company_id', string='Company',
                                 store=True, readonly=True)
    state = fields.Selection(related='customs_declaration_id.state', store=True)
    partner_id = fields.Many2one('res.partner', related='customs_declaration_id.partner_id', string='Partner',
                                 readonly=True, store=True)
    cost_currency_id = fields.Many2one(related='product_id.currency_id', string='Cost Currency', readonly=True)
    currency_id = fields.Many2one(related='customs_declaration_id.currency_id', string='Currency', readonly=True)

    customs_delaration_stock_move_ids = fields.One2many(
        'sale.customs.declaration.stock.move', inverse_name='customs_declaration_line_id',
        string='Stock Move', check_company=True)

    @api.depends('customs_delaration_stock_move_ids.product_qty')
    def _compute_amount(self):
        for declaration_line in self:
            product_qty = 0.0
            for move_line in declaration_line.customs_delaration_stock_move_ids:
                product_qty += move_line.product_qty

            total_cost = declaration_line.unit_cost * product_qty
            total_declare_price = declaration_line.unit_declare_price * product_qty

            declaration_line.write({
                'product_qty': product_qty,
                'total_cost': total_cost,
                'total_declare_price': total_declare_price,
            })


class CustomsDeclarationStockMove(models.Model):
    _name = "sale.customs.declaration.stock.move"
    _description = "Customs Declaration Stock Move"
    _order = "customs_declaration_id, product_id, stock_move_id"

    name = fields.Text(string='Description')
    stock_move_id = fields.Many2one('stock.move', string='Stock Move', ondelete="cascade")
    product_id = fields.Many2one('product.product', related='stock_move_id.product_id', string='Product',
                                 readonly=True, store=True)
    stock_move_name = fields.Char(related='stock_move_id.name', string='Stock Move Reference', readonly=True)
    sequence = fields.Integer(string='Sequence', default=10)

    product_qty = fields.Float(
        string='Quantity', digits='Product Unit of Measure', default=0)
    product_uom = fields.Many2one('uom.uom', related='product_id.uom_id', string='Unit of Measure', readonly=True)

    customs_declaration_id = fields.Many2one(
        'sale.customs.declaration', string='Customs Declaration Reference',
        index=True, required=True, ondelete='cascade')
    customs_declaration_line_id = fields.Many2one(
        'sale.customs.declaration.line', string='Customs Declaration Line Reference',
        index=True, required=True, ondelete='cascade')

    company_id = fields.Many2one('res.company', related='customs_declaration_id.company_id', string='Company',
                                 store=True, readonly=True)

    partner_id = fields.Many2one('res.partner', related='customs_declaration_id.partner_id', string='Partner',
                                 readonly=True, store=True)

    stock_move_date = fields.Datetime(
        related='stock_move_id.date', string='Date Scheduled', readonly=True)

    stock_move_qty = fields.Float(related='stock_move_id.product_uom_qty', string='Stock Move Qty', readonly=True)

    undeclared_qty = fields.Float(string='Undeclared Qty', readonly=True)

    stock_picking_id = fields.Many2one('stock.picking', related='stock_move_id.picking_id', readonly=True)

    def unlink(self):
        customs_declaration_line_ids = self.customs_declaration_line_id
        stock_moves = self.stock_move_id
        super(CustomsDeclarationStockMove, self).unlink()

        # stock_moves._compute_undeclared_qty()

        # 将数量为0的申报产品删除
        customs_declaration_line_ids.filtered(
            lambda r: float_compare(
                r.product_qty, 0,
                precision_rounding=r.product_uom.rounding) == 0)
        customs_declaration_line_ids.unlink()

        # for customs_declaration_line in customs_declaration_line_ids:
        #     if float_compare(
        #             customs_declaration_line.product_qty, 0,
        #             precision_rounding=customs_declaration_line.product_uom.rounding) == 0:
        #         customs_declaration_line.unlink()

    @api.onchange('product_qty')
    def onchange_product_qty(self):
        for line in self:
            if line.product_qty > line.undeclared_qty:
                raise UserError(_('Product quantity must less or equal to undeclared quantity.'))
