from collections import defaultdict, namedtuple
from math import log10

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _, SUPERUSER_ID, registry
from odoo.exceptions import UserError
from odoo.tools.date_utils import start_of, end_of, add, subtract
from odoo.tools.float_utils import float_round, float_compare
from odoo.osv.expression import OR, AND
from collections import OrderedDict
from datetime import datetime
import math

_STATES = [
    ("draft", "Draft"),
    ("sales_confirmed", "Sales Confirmed"),
    ("logistics_confirmed", "Logistics Confirmed"),
    ("done", "Done"),
]

_SALE_QTY_COMPUTE_METHOD = [
    ("by_product", "By Single Product"),
    ("by_group_weight", "By Group (Weight Factor)"),
    ("by_group_sale_qty", "By Group (Sale Qty Last 28 days)"),
]


class ShippingScheduleGroup(models.Model):
    _name = "web.sale.shipping.schedule.group"
    _order = "name"
    _check_company_auto = True

    name = fields.Char(string='Name', index=True, )

    shop_id = fields.Many2one("web.sale.shop", string="Default Shop", index=True, check_company=True)

    company_id = fields.Many2one(
        comodel_name="res.company", string="Company", index=True, required=True, default=lambda self: self.env.company)

    schedule_year = fields.Integer(string="Year", readonly=True, index=True, )
    schedule_month = fields.Integer(string="Month", readonly=True, index=True, )

    sale_qty_7 = fields.Integer(string='7 Days Sale')
    sale_qty_14 = fields.Integer(string='14 Days Sale')
    sale_qty_28 = fields.Integer(string='28 Days Sale')
    sale_qty_30 = fields.Integer(string='30 Days Sale')
    sale_qty_30_y_1 = fields.Integer(string='30 Days Sale Last Year')

    sale_qty_str = fields.Char(string="Sale Qty", compute='_compute_sale_qty_str')

    qty_available = fields.Integer(string="Available Qty")

    estimate_monthly_sale_qty_1 = fields.Integer(string="Estimate Monthly Sale Qty 1")

    estimate_monthly_sale_qty_2 = fields.Integer(string="Estimate Monthly Sale Qty 2")

    advised_monthly_sale_qty = fields.Integer(string="Advised Monthly Sale Qty")

    monthly_sale_qty = fields.Integer(string="Monthly Sale Qty")

    monthly_sale_qty_changed = fields.Boolean(string="Monthly Sale Qty Manually Changed", default=False)

    state = fields.Selection(
        selection=_STATES,
        string="Status",
        index=True,
        required=True,
        copy=True,
        default="draft",
        store=True,
        compute="_compute_state",
    )

    need_focus = fields.Boolean(string="Need Focus", default=False, index=True)

    salesperson_id = fields.Many2one(comodel_name='res.users', string='Salesperson', index=True, )

    shipping_schedule_ids = fields.One2many('web.sale.shipping.schedule', 'shipping_schedule_group_id',
        'Shipping Schedule',
        domain=[('state', '!=', 'canceled'), (  'shop_product_id.product_id', '!=', False), ('shop_product_id.state', 'in', ['new', 'normal'])],
        check_company=True)

    safety_available_days = fields.Integer(string="Safety Available Days", required=True, default=45)

    sale_qty_compute_method = fields.Selection(
        selection=_SALE_QTY_COMPUTE_METHOD,
        string="Sale Qty Compute Method",
        required=True,
        copy=True,
        default="by_product",
    )

    is_default_group = fields.Boolean("Default schedule of a shop")

    @api.depends("shipping_schedule_ids", "shipping_schedule_ids.state")
    def _compute_state(self):
        for schedule_group in self:
            shipping_schedule_ids = schedule_group.shipping_schedule_ids.filtered(
                lambda r:r.state != 'canceled' and r.shop_product_id.product_id != False
                    and r.shop_product_id.state in ['new', 'normal'])
            states = shipping_schedule_ids.mapped("state")
            if "draft" in states:
                schedule_group.state = "draft"
            elif "sales_confirmed" in states:
                schedule_group.state = "sales_confirmed"
            elif "logistics_confirmed" in states:
                schedule_group.state = "logistics_confirmed"
            else:
                schedule_group.state = "done"

    def action_reset_monthly_sale_qty(self):
        for schedule_group in self:
            schedule_group.monthly_sale_qty_changed = False
            schedule_group.monthly_sale_qty = schedule_group.advised_monthly_sale_qty
            schedule_group._set_schedule_monthly_sale_qty()

    def action_set_schedule_monthly_sale_qty(self):
        self._set_schedule_monthly_sale_qty()

    @api.onchange('monthly_sale_qty')
    def _onchange_monthly_sale_qty(self):
        self.monthly_sale_qty_changed = True

    def _set_schedule_monthly_sale_qty(self):
        for schedule_group in self:
            if schedule_group.sale_qty_compute_method == 'by_product':
                for schedule in schedule_group.shipping_schedule_ids:
                    schedule.advised_monthly_sale_qty = (
                        schedule.estimate_monthly_sale_qty_1 + schedule.estimate_monthly_sale_qty_2) / 2
            elif schedule_group.sale_qty_compute_method == 'by_group_weight':
                total_weight_factor = sum(schedule_group.shipping_schedule_ids.mapped("sale_weight_factor"))
                for schedule in schedule_group.shipping_schedule_ids:
                    schedule.advised_monthly_sale_qty = int(schedule_group.monthly_sale_qty \
                                                            * (schedule.sale_weight_factor / total_weight_factor))
            elif schedule_group.sale_qty_compute_method == 'by_group_sale_qty':
                total_sale_qty_30 = sum(schedule_group.shipping_schedule_ids.mapped("sale_qty_30"))
                if total_sale_qty_30 == 0:
                    for schedule in schedule_group.shipping_schedule_ids:
                        schedule.advised_monthly_sale_qty = 0
                else:
                    for schedule in schedule_group.shipping_schedule_ids:
                        schedule.advised_monthly_sale_qty = int(schedule_group.monthly_sale_qty \
                                                                * (schedule.sale_qty_30 / total_sale_qty_30))
            for schedule in schedule_group.shipping_schedule_ids:
                schedule._save_shipping_forecast()
        return True

    @api.depends('sale_qty_7', 'sale_qty_14', 'sale_qty_30')
    def _compute_sale_qty_str(self):
        for schedule in self:
            schedule.sale_qty_str = "%s/%s/%s" % (schedule.sale_qty_7, schedule.sale_qty_14, schedule.sale_qty_30)

    def _compute_estimate_monthly_sale(self, sale_qty_7, sale_qty_14, sale_qty_30):
        # 加权平均法
        estimate_monthly_sale_qty_1 = round(
            (sale_qty_7 / 7 * 0.5 + sale_qty_14 / 14 * 0.3 + sale_qty_30 / 30 * 0.2) * 30, 0)
        if estimate_monthly_sale_qty_1 < 0:
            estimate_monthly_sale_qty_1 = 0

        # 导数趋势法
        k1 = (sale_qty_7 / 7 - sale_qty_14 / 14) / 7
        k2 = (sale_qty_14 / 14 - sale_qty_30 / 30) / 14
        k3 = (k1 + k2) / 2
        estimate_monthly_sale_qty_2 = round((sale_qty_7 / 7 + k3 * 14) * 30, 0)
        if estimate_monthly_sale_qty_2 < 0:
            estimate_monthly_sale_qty_2 = 0

        advised_monthly_sale_qty = int((estimate_monthly_sale_qty_1 + estimate_monthly_sale_qty_2) / 2)

        return estimate_monthly_sale_qty_1, estimate_monthly_sale_qty_2, advised_monthly_sale_qty

    def refresh_group_data(self):
        for schedule_group in self:
            schedules = schedule_group.shipping_schedule_ids.filtered(lambda r: r.state != "canceled")
            if schedules:
                schedule_group.schedule_year = schedules[0].schedule_year
                schedule_group.schedule_month = schedules[0].schedule_month

            schedule_group.sale_qty_7 = sum(schedules.mapped("sale_qty_7"))
            schedule_group.sale_qty_14 = sum(schedules.mapped("sale_qty_14"))
            schedule_group.sale_qty_28 = sum(schedules.mapped("sale_qty_28"))
            schedule_group.sale_qty_30 = sum(schedules.mapped("sale_qty_30"))
            schedule_group.sale_qty_30_y_1 = sum(schedules.mapped("sale_qty_30_y_1"))
            schedule_group.qty_available = sum(schedules.mapped("qty_available"))

            estimate_monthly_sale_qty_1, estimate_monthly_sale_qty_2, advised_monthly_sale_qty = \
                self._compute_estimate_monthly_sale(schedule_group.sale_qty_7, schedule_group.sale_qty_14,
                                                    schedule_group.sale_qty_30)

            schedule_group.estimate_monthly_sale_qty_1 = estimate_monthly_sale_qty_1
            schedule_group.estimate_monthly_sale_qty_2 = estimate_monthly_sale_qty_2
            schedule_group.advised_monthly_sale_qty = advised_monthly_sale_qty

            if not schedule_group.monthly_sale_qty_changed:
                schedule_group.monthly_sale_qty = advised_monthly_sale_qty

            schedule_group._set_schedule_monthly_sale_qty()
