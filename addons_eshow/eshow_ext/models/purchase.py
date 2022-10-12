# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from datetime import datetime, time
from dateutil.relativedelta import relativedelta
from functools import partial
from itertools import groupby
import json

from markupsafe import escape, Markup
from pytz import timezone, UTC
from werkzeug.urls import url_encode

from odoo import api, fields, models, SUPERUSER_ID, _

from odoo.osv import expression
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from odoo.tools.float_utils import float_compare, float_is_zero, float_round
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.misc import formatLang, get_lang, format_amount


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def _prepare_notes(self, partner_id):

        partner_id = self.env['res.partner'].browse(partner_id)

        notes = ""
        if partner_id:
            if partner_id.purchase_order_notes:
                notes = partner_id.purchase_order_notes
            else:
                notes = """1. 以上价格包含增值税和运费。<br>
                    2. 付款条件： [付款条件]<br>
                    3. 质量要求：按采购方图纸、封样或技术协议的要求执行。<br>
                    4. 其他说明： <br>"""

            payment_term = "与供应商商定。"
            if partner_id.property_supplier_payment_term_id:
                payment_term = partner_id.property_supplier_payment_term_id.name

            notes = notes.replace("[付款条件]", payment_term)
        return notes

    @api.onchange('partner_id')
    def _compute_notes(self):
        for order in self:
            if order.partner_id:
                order.notes = order._prepare_notes(order.partner_id.id)

    @api.model
    def create(self, vals):
        vals["notes"] = self._prepare_notes(vals['partner_id'])
        res = super(PurchaseOrder, self).create(vals)
        return res

    def _create_picking(self):
        """
            Tim Wang modified at 20220708
            修正如果是退货订单，生成的出库单丢失Partner Id 的情况
        """
        StockPicking = self.env['stock.picking']
        for order in self.filtered(lambda po: po.state in ('purchase', 'done')):
            if any(product.type in ['product', 'consu'] for product in order.order_line.product_id):
                order = order.with_company(order.company_id)
                pickings = order.picking_ids.filtered(lambda x: x.state not in ('done', 'cancel'))
                if not pickings:
                    res = order._prepare_picking()
                    picking = StockPicking.with_user(SUPERUSER_ID).create(res)
                else:
                    picking = pickings[0]
                moves = order.order_line._create_stock_moves(picking)
                moves = moves.filtered(lambda x: x.state not in ('done', 'cancel'))._action_confirm()

                seq = 0
                for move in sorted(moves, key=lambda move: move.date):
                    seq += 5
                    move.sequence = seq
                moves._action_assign()

                """
                    Tim Wang modified at 20220708
                    修正如果是退货订单，生成的出库单丢失Partner Id 的情况
                """
                for move in moves:
                    if not move.picking_id.partner_id:
                        move.picking_id.partner_id = order.partner_id

                picking.message_post_with_view('mail.message_origin_link',
                    values={'self': picking, 'origin': order},
                    subtype_id=self.env.ref('mail.mt_note').id)
        return True

    def action_create_invoice(self):
        """Create the invoice associated to the PO.
        """
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')

        # 1) Prepare invoice vals and clean-up the section lines
        invoice_vals_list = []
        for order in self:
            if order.invoice_status != 'to invoice':
                continue

            order = order.with_company(order.company_id)
            pending_section = None
            # Invoice values.
            invoice_vals = order._prepare_invoice()
            # Invoice line values (keep only necessary sections).
            for line in order.order_line:
                if line.display_type == 'line_section':
                    pending_section = line
                    continue
                if not float_is_zero(line.qty_to_invoice, precision_digits=precision):
                    if pending_section:
                        res_list = pending_section._prepare_account_move_line_2()
                        for res in res_list:
                            invoice_vals['invoice_line_ids'].append((0, 0, res))
                        pending_section = None
                    res_list = line._prepare_account_move_line_2()
                    for res in res_list:
                        invoice_vals['invoice_line_ids'].append((0, 0, res))
            invoice_vals_list.append(invoice_vals)

        if not invoice_vals_list:
            raise UserError(_('There is no invoiceable line. If a product has a control policy based on received quantity, please make sure that a quantity has been received.'))

        # 2) group by (company_id, partner_id, currency_id) for batch creation
        new_invoice_vals_list = []
        for grouping_keys, invoices in groupby(invoice_vals_list, key=lambda x: (x.get('company_id'), x.get('partner_id'), x.get('currency_id'))):
            origins = set()
            payment_refs = set()
            refs = set()
            ref_invoice_vals = None
            for invoice_vals in invoices:
                if not ref_invoice_vals:
                    ref_invoice_vals = invoice_vals
                else:
                    ref_invoice_vals['invoice_line_ids'] += invoice_vals['invoice_line_ids']
                origins.add(invoice_vals['invoice_origin'])
                payment_refs.add(invoice_vals['payment_reference'])
                refs.add(invoice_vals['ref'])
            ref_invoice_vals.update({
                'ref': ', '.join(refs)[:2000],
                'invoice_origin': ', '.join(origins),
                'payment_reference': len(payment_refs) == 1 and payment_refs.pop() or False,
            })
            new_invoice_vals_list.append(ref_invoice_vals)
        invoice_vals_list = new_invoice_vals_list

        # 3) Create invoices.
        moves = self.env['account.move']
        AccountMove = self.env['account.move'].with_context(default_move_type='in_invoice')
        for vals in invoice_vals_list:
            moves |= AccountMove.with_company(vals['company_id']).create(vals)

        # 4) Some moves might actually be refunds: convert them if the total amount is negative
        # We do this after the moves have been created since we need taxes, etc. to know if the total
        # is actually negative or not
        moves.filtered(lambda m: m.currency_id.round(m.amount_total) < 0).action_switch_invoice_into_refund_credit_note()

        return self.action_view_invoice(moves)


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    def _prepare_account_move_line_1(self, move=False):
        self.ensure_one()
        res = super()._prepare_account_move_line(move)

        if self.name != self.product_id.display_name:
            name = '%s - %s' % (self.order_id.name, self.name)
        else:
            name = '%s' % (self.order_id.name,)

        if self.product_id.detailed_type in ('product', 'consu'):
            # name += '\nDetail:'
            for stock_move in self.move_ids:
                if stock_move.state == 'done':
                    for move_line in stock_move.move_line_ids:
                        if move_line.picking_id.picking_type_id.sequence_code == 'IN':
                            # 收货入库
                            name += '\n%s\t%s' % (move_line.date.strftime("%Y-%m-%d"), move_line.qty_done)
                        else:
                            # 退货
                            name += '\n%s\t%s' % (move_line.date.strftime("%Y-%m-%d"), move_line.qty_done * -1)


        res.update({
            'name': name,
        })
        return res

    """
    Tim Wang modified at 20220630
    按Stock Move Line 生成Account Move的明细数据
    """
    def _prepare_account_move_line_2(self, move=False):
        self.ensure_one()
        aml_currency = move and move.currency_id or self.currency_id

        res_list = []

        date = move and move.date or fields.Date.today()


        if self.product_id.detailed_type in ('product', 'consu'):
            for stock_move in self.move_ids:
                if stock_move.state == 'done':
                    for move_line in stock_move.move_line_ids:
                        if move_line.picking_id.picking_type_id.sequence_code == 'IN':
                            # 收货入库
                            res = {
                                'display_type': self.display_type,
                                'sequence': self.sequence,
                                'name': '%s\t%s' % (move_line.date.strftime("%Y-%m-%d"), self.order_id.name),
                                'product_id': self.product_id.id,
                                'product_uom_id': self.product_uom.id,
                                'quantity': move_line.qty_done,
                                'price_unit': self.currency_id._convert(self.price_unit, aml_currency, self.company_id,
                                                                        date, round=False),
                                'tax_ids': [(6, 0, self.taxes_id.ids)],
                                'analytic_account_id': self.account_analytic_id.id,
                                'analytic_tag_ids': [(6, 0, self.analytic_tag_ids.ids)],
                                'purchase_line_id': self.id,
                            }
                        else:
                            # 退货
                            res = {
                                'display_type': self.display_type,
                                'sequence': self.sequence,
                                'name': '%s\t%s\t%s' % (move_line.date.strftime("%Y-%m-%d"), '退货', self.order_id.name),
                                'product_id': self.product_id.id,
                                'product_uom_id': self.product_uom.id,
                                'quantity': move_line.qty_done * -1,
                                'price_unit': self.currency_id._convert(self.price_unit, aml_currency, self.company_id,
                                                                        date, round=False),
                                'tax_ids': [(6, 0, self.taxes_id.ids)],
                                'analytic_account_id': self.account_analytic_id.id,
                                'analytic_tag_ids': [(6, 0, self.analytic_tag_ids.ids)],
                                'purchase_line_id': self.id,
                            }
                        if move:
                            if self.currency_id == move.company_id.currency_id:
                                currency = False
                            else:
                                currency = move.currency_id

                            res.update({
                                'move_id': move.id,
                                'currency_id': currency and currency.id or False,
                                'date_maturity': move.invoice_date_due,
                                'partner_id': move.partner_id.id,
                            })
                        res_list.append(res)

        return res_list

