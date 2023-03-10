# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import time
from ast import literal_eval
from datetime import date, timedelta, datetime
from itertools import groupby
from operator import attrgetter, itemgetter
from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import UserError
from odoo.osv.expression import expression
from odoo.tools import date_utils, float_compare

FBA_SHIPMENT_STATES = [
    ("working", "Working"),
    ("shipped", "Shipped"),
    ("in_transit", "In Transit"),
    ("delivered", "Delivered"),
    ("check_in", "Check In"),
    ("receiving", "Receiving"),
    ("closed", "Closed"),
    ("cancelled", "Cancelled"),
    ("delete", "Delete"),
    ("error", "Error"),
]

class Picking(models.Model):
    _inherit = "stock.picking"

    # Used to search on pickings
    shop_product_id = fields.Many2one('web.sale.shop.product', 'Shop Product', related='move_lines.shop_product_id', readonly=True)

    shipping_method = fields.Many2one("web.sale.shipping.method", string="Shipping Method")

    estimate_ship_days = fields.Integer("Estimate Ship Days", compute="_compute_estimate_arriving_date", store=True)

    estimate_arriving_date = fields.Date("Estimate Arriving Date",
        compute="_compute_estimate_arriving_date", inverse="_set_estimate_arriving_date", store=True)

    estimate_arriving_date_manually_changed = fields.Boolean("Estimate Arriving Date Manually Changed", default=False)

    shipping_forecast_date = fields.Date('Date', index=True, help='Forecast Period which the picking belongs to.')

    lx_shipment_id = fields.Integer("LX Shipment ID", index=True, readonly=True)
    lx_shipment_sn = fields.Char("LX Shipment SN", index=True, readonly=True)
    delivery_date = fields.Date("Delivery Date", help="Actual Delivery Date", readonly=True)
    lx_state = fields.Selection([("-1", "To Pick"), ("0", "To Ship"), ("1", "Shipped"), ("3", "Cancel")],
                                "LX State", index=True, readonly=True)
    lx_create_time = fields.Datetime("LX Create Time", readonly=True)
    lx_update_time = fields.Datetime("LX Update Time", readonly=True)
    lx_remark = fields.Char("LX Remark", readonly=True)
    lx_warehouse_id = fields.Integer("LX Warehouse ID", readonly=True)
    lx_logistics_channel_name = fields.Char("LX Logistics Channel Name", readonly=True)

    fba_shipment_state = fields.Selection(FBA_SHIPMENT_STATES, "FBA Shipment Status",
        compute="_compute_fba_shipment_state", index=True, store=True)

    procurement_launched = fields.Boolean("Procurement Launched", default=False)

    @api.depends("state", "partner_id", "delivery_date", "shipping_method")
    def _compute_estimate_arriving_date(self):
        for picking in self:
            estimate_ship_days = 30

            if picking.delivery_date:
                ship_date = picking.delivery_date
            elif picking.state == "done":
                ship_date = picking.date_done
            else:
                ship_date = picking.scheduled_date

            if picking.shipping_method:
                estimate_ship_days = picking.shipping_method.estimate_ship_days
            elif picking.partner_id.default_shipping_method_id:
                estimate_ship_days = picking.partner_id.default_shipping_method_id.estimate_ship_days

            if ship_date:
                picking.estimate_ship_days = estimate_ship_days
                if not picking.estimate_arriving_date_manually_changed:
                    picking.estimate_arriving_date = date_utils.add(ship_date, days=estimate_ship_days)

    def _set_estimate_arriving_date(self):
        for picking in self:
            picking.estimate_arriving_date_manually_changed = True

    @api.depends("move_lines", "move_lines.fba_shipment_state")
    def _compute_fba_shipment_state(self):
        pickings = self.filtered(lambda r: r.move_document_type == 'sale_out' and r.partner_id.is_web_shop == True)
        picking_moves_shipment_state_map = defaultdict(dict)
        picking_move_lines = defaultdict(set)
        for move in self.env['stock.move'].search([('picking_id', 'in', pickings.ids)]):
            picking_id = move.picking_id
            move_shipment_state = move.fba_shipment_state
            picking_moves_shipment_state_map[picking_id.id].update({
                'any_working': picking_moves_shipment_state_map[picking_id.id].get('any_working', False) or move_shipment_state == 'working' or move_shipment_state == False,
                'any_shipped': picking_moves_shipment_state_map[picking_id.id].get('any_shipped', False) or move_shipment_state == 'shipped',
                'any_in_transit': picking_moves_shipment_state_map[picking_id.id].get('any_in_transit', False) or move_shipment_state == 'in_transit',
                'any_delivered': picking_moves_shipment_state_map[picking_id.id].get('any_delivered',
                                                                             False) or move_shipment_state == 'delivered',
                'any_check_in': picking_moves_shipment_state_map[picking_id.id].get('any_check_in',
                                                                            False) or move_shipment_state == 'check_in',
                'any_receiving': picking_moves_shipment_state_map[picking_id.id].get('any_receiving',
                                                                            False) or move_shipment_state == 'receiving',
                'all_closed': picking_moves_shipment_state_map[picking_id.id].get('all_closed',
                                                                             True) and move_shipment_state == 'closed',
                'all_cancelled': picking_moves_shipment_state_map[picking_id.id].get('all_cancelled',
                                                                         True) and move_shipment_state == 'cancelled',
                'all_delete': picking_moves_shipment_state_map[picking_id.id].get('all_delete',
                                                                            True) and move_shipment_state == 'delete',
                'any_error': picking_moves_shipment_state_map[picking_id.id].get('any_error',
                                                                            False) or move_shipment_state == 'error',
            })
            picking_move_lines[picking_id.id].add(move.id)
        for picking in pickings:
            picking_id = (picking.ids and picking.ids[0]) or picking.id
            if not picking_moves_shipment_state_map[picking_id]:
                picking.fba_shipment_state = 'working'
            elif picking_moves_shipment_state_map[picking_id]['any_error']:
                picking.fba_shipment_state = 'error'
            elif picking_moves_shipment_state_map[picking_id]['any_receiving']:
                picking.fba_shipment_state = 'receiving'
            elif picking_moves_shipment_state_map[picking_id]['any_check_in']:
                picking.fba_shipment_state = 'check_in'
            elif picking_moves_shipment_state_map[picking_id]['any_delivered']:
                picking.fba_shipment_state = 'delivered'
            elif picking_moves_shipment_state_map[picking_id]['any_in_transit']:
                picking.fba_shipment_state = 'in_transit'
            elif picking_moves_shipment_state_map[picking_id]['any_shipped']:
                picking.fba_shipment_state = 'shipped'
            elif picking_moves_shipment_state_map[picking_id]['any_working']:
                picking.fba_shipment_state = 'working'
            elif picking_moves_shipment_state_map[picking_id]['all_closed']:
                picking.fba_shipment_state = 'closed'
            elif picking_moves_shipment_state_map[picking_id]['all_cancelled']:
                picking.fba_shipment_state = 'cancelled'
            elif picking_moves_shipment_state_map[picking_id]['all_delete']:
                picking.fba_shipment_state = 'delete'
            else:
                # 在接收以后，如果没有all_closed，all_cancelled，all_delete
                # 则默认为receiving
                picking.fba_shipment_state = 'receiving'

    def write(self, vals):
        rtn = super(Picking, self).write(vals)
        if self.move_document_type == 'sale_out' and self.partner_id.is_web_shop \
            and "shipping_forecast_date" in vals:
            for move in self.move_lines:
                domain = [
                    ("company_id", "=", move.company_id.id),
                    ("date", "<=", move.picking_id.shipping_forecast_date),
                    ("date", ">", move.picking_id.shipping_forecast_date + relativedelta(month=1)),
                    ("shipping_schedule_id.shop_product_id", "=", move.shop_product_id.id),
                ]
                forecast = self.env["web.sale.shipping.forecast"].search(domain, limit=1)
                if forecast:
                    move.shipping_forecast_id = forecast
                else:
                    move.shipping_forecast_id = False
        return rtn

    def do_replenish(self):
        """
            Create procurements based on picking.
        """
        self.ensure_one()

        if self.procurement_launched:
            raise UserError(_("Procurement can only run once."))
        procurements = []
        moves = self.move_lines
        extra_values = self._get_procurement_extra_values()

        for move in moves:
            procurements.append(self.env['procurement.group'].Procurement(
                move.product_id,
                move.product_uom_qty,
                move.product_uom,
                move.location_id,
                move.product_id.name,
                self.name,
                move.company_id, extra_values
            ))

        if procurements:
            self.env['procurement.group'].with_context(skip_lead_time=True).run(procurements)

        self.procurement_launched = True

        notification = {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Notification'),
                'message': _('Procurements have been launched'),
                'sticky': True,
                'className': 'bg-success',
            }
        }
        return notification

    def _get_procurement_extra_values(self):
        """ Extra values that could be added in the vals for procurement.

        return values pass to the procurement run method.
        rtype dict
        """
        self.ensure_one()
        group_name = self.name
        # 取得对应计划时间的Group Id
        procurement_group = self.env['procurement.group'].search([("name", "=", group_name), ])
        # 如果没有，则新增一个
        if not procurement_group:
            values = [{"name": group_name, "move_type": "direct"}]
            procurement_group = self.env['procurement.group'].create(values)
        else:
            procurement_group = procurement_group[0]

        return {
            'date_planned': self.scheduled_date,
            'warehouse_id': self.location_id.warehouse_id,
            'group_id': procurement_group.id,
        }

    def _get_replenishment_order_notification(self):
        self.ensure_one()
        domain = [('orderpoint_id', 'in', self.ids)]
        if self.env.context.get('written_after'):
            domain = expression.AND([domain, [('write_date', '>', self.env.context.get('written_after'))]])
        move = self.env['stock.move'].search(domain, limit=1)
        if move.picking_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('The inter-warehouse transfers have been generated'),
                    'sticky': True,
                }
            }
        return False
