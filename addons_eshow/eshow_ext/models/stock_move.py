
from collections import defaultdict
from datetime import timedelta
from itertools import groupby
from odoo.tools import groupby as groupbyelem
from operator import itemgetter

from odoo import _, api, Command, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression
from odoo.tools.float_utils import float_compare, float_is_zero, float_round
from odoo.tools.misc import clean_context, OrderedSet

PROCUREMENT_PRIORITIES = [('0', 'Normal'), ('1', 'Urgent')]


class StockMove(models.Model):
    _inherit = "stock.move"

    invoice_lines = fields.One2many('account.move.line', 'stock_move_id', string="Bill Lines", readonly=True, copy=False)

    qty_invoiced = fields.Float(compute='_compute_qty_invoiced', string="Billed Qty", digits='Product Unit of Measure', store=True)

    qty_to_invoice = fields.Float(compute='_compute_qty_invoiced', string='To Invoice Quantity', store=True, readonly=True,
                                  digits='Product Unit of Measure')

    picking_partner_id = fields.Many2one(
        related='picking_id.partner_id', string='Picking Partner', readonly=True, store=True)

    product_name = fields.Char(
        related='product_id.name', string='Product Name', readonly=True)

    product_default_code = fields.Char(
        related='product_id.default_code', string='Product Default Code', readonly=True)

    invoice_status = fields.Selection([
        ('no', 'Nothing to Bill'),
        ('to invoice', 'Waiting Bills'),
        ('invoiced', 'Fully Billed'),
        ],
        related='picking_id.invoice_status', string='Billing Status', readonly=True)

    def _get_invoice_lines(self):
        self.ensure_one()
        if self._context.get('accrual_entry_date'):
            return self.invoice_lines.filtered(
                lambda l: l.move_id.invoice_date and l.move_id.invoice_date <= self._context['accrual_entry_date']
            )
        else:
            return self.invoice_lines

    @api.depends('invoice_lines.move_id.state', 'invoice_lines.quantity', 'quantity_done', 'product_uom_qty', 'picking_id.state')
    def _compute_qty_invoiced(self):
        for line in self:
            # compute qty_invoiced
            qty = 0.0
            for inv_line in line._get_invoice_lines():
                if inv_line.move_id.state not in ['cancel']:
                    if inv_line.move_id.move_type == 'in_invoice':
                        if line.is_return_move():
                            qty -= inv_line.product_uom_id._compute_quantity(inv_line.quantity, line.product_uom)
                        else:
                            qty += inv_line.product_uom_id._compute_quantity(inv_line.quantity, line.product_uom)
                    elif inv_line.move_id.move_type == 'in_refund':
                        if line.is_return_move():
                            qty += inv_line.product_uom_id._compute_quantity(inv_line.quantity, line.product_uom)
                        else:
                            qty -= inv_line.product_uom_id._compute_quantity(inv_line.quantity, line.product_uom)

            line.qty_invoiced = qty

            # compute qty_to_invoice
            if line.state in ['done']:
                if line.product_id.purchase_method == 'purchase':
                    line.qty_to_invoice = line.product_qty - line.qty_invoiced
                else:
                    line.qty_to_invoice = line.quantity_done - line.qty_invoiced
            else:
                line.qty_to_invoice = 0

    def _prepare_invoice_line(self, account_move=False):
        self.ensure_one()
        aml_currency = account_move and account_move.currency_id or self.purchase_line_id.currency_id
        date = account_move and account_move.date or fields.Date.today()

        qty_to_invoice = self.qty_to_invoice

        if self.is_return_move():
            qty_to_invoice = -1 * qty_to_invoice

        res = {
            'display_type': '',
            'sequence': self.sequence,
            'name': '%s: %s' % (date.strftime("%Y-%m-%d"), self.purchase_line_id.order_id.name),
            'product_id': self.product_id.id,
            'product_uom_id': self.product_uom.id,
            'quantity': qty_to_invoice,
            'price_unit': self.purchase_line_id.currency_id._convert(self.purchase_line_id.price_unit, aml_currency, self.company_id, date, round=False),
            'tax_ids': [(6, 0, self.purchase_line_id.taxes_id.ids)],
            'analytic_account_id': self.purchase_line_id.account_analytic_id.id,
            'analytic_tag_ids': [(6, 0, self.purchase_line_id.analytic_tag_ids.ids)],
            'purchase_line_id': self.purchase_line_id.id,
            'stock_move_id': self.id,
            'stock_picking_id': self.picking_id.id,
        }
        if not account_move:
            return res

        if self.currency_id == account_move.company_id.currency_id:
            currency = False
        else:
            currency = account_move.currency_id

        res.update({
            'move_id': account_move.id,
            'currency_id': currency and currency.id or False,
            'date_maturity': account_move.invoice_date_due,
            'partner_id': account_move.partner_id.id,
        })
        return res

    def action_create_invoice(self):
        result = self.picking_id.action_create_invoice()
        return result
        # picking_ids = {}
        # picking_ids2 = ()
        # for move in self:
        #     if not picking_ids.get(move.picking_id.id):
        #         picking_ids.setdefault(move.picking_id.id, move.picking_id)
        # for picking_id in picking_ids.values():
        #     picking_ids2 += picking_id
        # picking_ids2.action_create_invoice()

    def is_return_move(self):
        if self.location_dest_id.usage == 'supplier' or self.location_id.usage == 'customer':
            return True
        else:
            return False

