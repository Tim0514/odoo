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


class ShippingForecast(models.Model):
    _name = "web.sale.shipping.forecast"
    _order = 'date'
    _description = 'Product Shipping Forecast at Date'

    shipping_schedule_id = fields.Many2one('web.sale.shipping.schedule', required=True, ondelete='cascade')
    date = fields.Date('Date', required=True)

    # 期初库存
    starting_inventory_qty = fields.Integer(string="Starting Inventory Qty", default=0)
    # 期末库存
    ending_inventory_qty = fields.Integer(string="Existing Arriving Qty", compute="_compute_ending_inventory_qty")

    # 预计销量
    forecast_sale_qty = fields.Integer(string="Forecast Sale Qty")
    forecast_sale_qty_changed = fields.Boolean(string="Forecast sale qty has been manually changed", default=False)

    # 计划到货数量
    arriving_qty_confirmed = fields.Integer(string="Forecast Arriving Qty", default=0)

    # 运营申请数量
    arriving_qty_apply = fields.Integer(string="Apply Qty")
    arriving_qty_apply_changed = fields.Boolean(string="Arriving qty applied by salesperson has been manually changed",
                                                default=False)

    # 物流确认数量
    arriving_qty_verify = fields.Integer(string="Confirm Qty")
    arriving_qty_verify_changed = fields.Boolean(string="Arriving qty verified by logistics has been manually changed",
                                                 default=False)

    # 需要新增的到货数量，如果是负数，则表示要减少的到货数量
    arriving_qty_increase = fields.Integer(string="Additional Arriving Qty")

    # 已经发货在途的到货数量，这个数据是从领星里面下载下来参考用的，不参与计算
    arriving_qty_existing = fields.Integer(string="Existing Arriving Qty", default=0)

    # 安全库存数量
    safety_inventory_qty = fields.Integer(string="Safety Inventory Qty")
    safety_inventory_qty_changed = fields.Boolean(string="Safety inventory qty has been manually changed",
                                                  default=False)

    # 本次shipping_schedule运算中，该forecast 是否已进行了补货。
    procurement_launched = fields.Boolean('Procurement has been run for this forecast', default=False)

    # 对应已补货数量
    replenished_qty = fields.Integer(string="Replenished Qty")
    # 根据可用库存和需要新增的到货数量，计算出的实际需要补货的数量，在补货完成后，该数量需增加到对应已补货数量中去。
    replenish_qty_required = fields.Integer(string="Replenish Qty Required")

    # incoming_qty 预测本地库存
    # replenish_qty 需安排补货数量

    @api.depends('starting_inventory_qty')
    def _compute_ending_inventory_qty(self):
        for forecast in self:
            ending_inventory_qty = forecast.starting_inventory_qty \
                                   + forecast.arriving_qty_verify - forecast.forecast_sale_qty
            ending_inventory_qty = ending_inventory_qty if ending_inventory_qty >= 0 else 0

            forecast.ending_inventory_qty = ending_inventory_qty


class ShippingSchedule(models.Model):
    _name = "web.sale.shipping.schedule"
    _description = "Shipping Schedule"
    _order = "schedule_year desc, schedule_month desc, shop_id, seller_sku"

    # shop_warehouse_id = fields.Many2one("web.sale.warehouse", string='Web Shop Warehouse', readonly=True, )
    # shop_warehouse_name = fields.Char(
    #     string='Web Shop Warehouse', related="shop_warehouse_id.name",
    #     readonly=True, store=True, index=True, )

    shop_product_id = fields.Many2one(comodel_name="web.sale.shop.product", string="Shop Product", readonly=True, )

    shop_id = fields.Many2one("web.sale.shop", string="Default Shop", store=True, index=True,
                                      related="shop_product_id.shop_id")

    company_id = fields.Many2one(
        comodel_name="res.company", related="shop_product_id.company_id", string="Company", store=True)

    warehouse_id = fields.Many2one(
        comodel_name="stock.warehouse", related="company_id.warehouse_id", string="Warehouse", store=True)

    product_id = fields.Many2one(
        comodel_name="product.product", related="shop_product_id.product_id", string="Product",
        store=True, readonly=True, )
    product_default_code = fields.Char(
        related="product_id.default_code", string="Default Code",
        readonly=True, store=True, index=True, )

    product_name = fields.Char(
        related="product_id.name", string="Product Name",
        readonly=True, store=True, index=True, )

    seller_sku = fields.Char(
        related="shop_product_id.seller_sku", string="MSKU",
        readonly=True, store=True, index=True, )

    product_uom_id = fields.Many2one('uom.uom', string='Product UoM',
                                     related='product_id.uom_id')

    schedule_year = fields.Integer(string="Year", readonly=True, index=True, )
    schedule_month = fields.Integer(string="Month", readonly=True, index=True, )

    sale_qty_7 = fields.Float(string='7 Days Sale')
    sale_qty_14 = fields.Float(string='14 Days Sale')
    sale_qty_28 = fields.Float(string='28 Days Sale')

    sale_qty_str = fields.Char(string="Sale Qty", compute='_compute_sale_qty_str')

    qty_available = fields.Integer(string="Available Qty")
    qty_shipped = fields.Integer(string="Shipped Qty")
    estimate_monthly_sale_qty_1 = fields.Integer(string="Estimate Monthly Sale Qty 1")
    estimate_monthly_sale_qty_2 = fields.Integer(string="Estimate Monthly Sale Qty 2")
    advised_monthly_sale_qty = fields.Integer(string="Advised Monthly Sale Qty")

    state = fields.Selection(
        selection=_STATES,
        string="Status",
        index=True,
        required=True,
        copy=True,
        default="draft",
    )

    product_state = fields.Selection(string="Product State", related="shop_product_id.state")

    need_focus = fields.Boolean(string="Need Focus", default=False)

    salesperson_id = fields.Many2one(
        comodel_name='res.users', related="shop_product_id.salesperson_id", string='Salesperson', index=True,
    )

    forecast_ids = fields.One2many('web.sale.shipping.forecast', 'shipping_schedule_id',
                                   'Forecasted quantity at date')

    safety_available_days = fields.Integer(string="Safety Available Days", required=True, default=45)

    shipping_schedule_group_id = fields.Many2one(comodel_name='web.sale.shipping.schedule.group',
        string='Shipping Schedule Group', ondelete="set null")

    sale_weight_factor = fields.Integer("Sale Weight Factor", default=100,
                                        help="Sale weight factor in group for allocating sale quantity.")

    # 过去30天中，如果可售数量, 待调仓数量, 调仓中, 入库中 四个数据加起来，出现过0 则为True
    is_out_of_stock_occurred = fields.Boolean(string="Is out of stock occurred", default=False,
                                              help="Is out of stock occurred in last 30 days")

    @api.depends('sale_qty_7', 'sale_qty_14', 'sale_qty_28')
    def _compute_sale_qty_str(self):
        for schedule in self:
            schedule.sale_qty_str = "%s/%s/%s" % (schedule.sale_qty_7, schedule.sale_qty_14, schedule.sale_qty_28)

    def _compute_estimate_monthly_sale(self, sale_qty_7, sale_qty_14, sale_qty_28):
        # 加权平均法
        estimate_monthly_sale_qty_1 = round(
            (sale_qty_7 / 7 * 0.5 + sale_qty_14 / 14 * 0.3 + sale_qty_28 / 28 * 0.2) * 30, 0)
        if estimate_monthly_sale_qty_1 < 0:
            estimate_monthly_sale_qty_1 = 0

        # 导数趋势法
        k1 = (sale_qty_7 / 7 - sale_qty_14 / 14) / 7
        k2 = (sale_qty_14 / 14 - sale_qty_28 / 28) / 14
        k3 = (k1 + k2) / 2
        estimate_monthly_sale_qty_2 = round((sale_qty_7 / 7 + k3 * 14) * 30, 0)
        if estimate_monthly_sale_qty_2 < 0:
            estimate_monthly_sale_qty_2 = 0

        advised_monthly_sale_qty = int((estimate_monthly_sale_qty_1 + estimate_monthly_sale_qty_2) / 2)

        return estimate_monthly_sale_qty_1, estimate_monthly_sale_qty_2, advised_monthly_sale_qty

    def _create_shipping_schedule(self, use_new_cursor=False, company_id=False):

        if not company_id:
            company_id = self.env.company.id

        first_day = start_of(fields.Date.today(), self.env.company.manufacturing_period)
        # 去掉时分秒
        first_day = datetime.strptime(first_day.strftime('%Y-%m-%d'), '%Y-%m-%d')
        schedule_year = first_day.year
        schedule_month = first_day.month

        shop_inventory_obj = self.env["web.sale.shop.inventory"]
        product_weekly_stat_obj = self.env["web.sale.shop.product.weekly.stat"]
        domain = [
            ("company_id", "=", company_id),
            ("product_id", "!=", False),
            ("is_latest_inventory", "=", True),
        ]
        shop_inventories = shop_inventory_obj.search(domain)

        shipping_schedules = self.search([])
        shipping_schedules_by_product = {}
        for shipping_schedule in shipping_schedules:
            shipping_schedules_by_product.setdefault(shipping_schedule.shop_product_id.id, shipping_schedule)

        shipping_schedules_refreshed = []

        for shop_inventory in shop_inventories:
            # domain = [
            #     ("shop_warehouse_id", "=", shop_inventory.shop_warehouse_id.id),
            #     ("shop_product_id", "=", shop_inventory.shop_product_id.id),
            # ]
            # shipping_schedule = self.search(domain)
            shipping_schedule = shipping_schedules_by_product.get(shop_inventory.shop_product_id.id)

            sale_qty_7, sale_qty_14, sale_qty_28 = product_weekly_stat_obj.get_product_sale_data(
                shop_inventory.shop_product_id, first_day)

            estimate_monthly_sale_qty_1, estimate_monthly_sale_qty_2, advised_monthly_sale_qty = \
                self._compute_estimate_monthly_sale(sale_qty_7, sale_qty_14, sale_qty_28)

            shipping_schedule_vals = {
                "shop_product_id": shop_inventory.shop_product_id.id,
                "schedule_year": schedule_year,
                "schedule_month": schedule_month,
                "qty_available": shop_inventory.sellable_quantity,
                "qty_shipped": shop_inventory.get_shipped_quantity(),
                "sale_qty_7": sale_qty_7,
                "sale_qty_14": sale_qty_14,
                "sale_qty_28": sale_qty_28,
                "estimate_monthly_sale_qty_1": estimate_monthly_sale_qty_1,
                "estimate_monthly_sale_qty_2": estimate_monthly_sale_qty_2,
                "advised_monthly_sale_qty": advised_monthly_sale_qty,
                "is_out_of_stock_occurred": shop_inventory.is_out_of_stock_occurred,
                "state": "draft",
            }

            if shipping_schedule:
                shipping_schedule.write(shipping_schedule_vals)
            else:
                shipping_schedule = self.create(shipping_schedule_vals)

            shipping_schedules_refreshed.append(shipping_schedule)

        # 给所有未设置shipping_schedule_group的计划设置为默认group
        shipping_schedules_without_group = filter(lambda r: not r.shipping_schedule_group_id, shipping_schedules_refreshed)
        for shipping_schedule in shipping_schedules_without_group:
            shop_id = shipping_schedule.shop_id
            shipping_schedule_group_id = shop_id.default_shipping_schedule_group_id
            if not shipping_schedule_group_id:
                shop_id._create_default_shipping_schedule_group_id()
                shipping_schedule_group_id = shop_id.default_shipping_schedule_group_id
            shipping_schedule.shipping_schedule_group_id = shipping_schedule_group_id

        # 刷新shipping_schedule_group信息
        schedule_group_obj = self.env["web.sale.shipping.schedule.group"]
        schedule_groups = schedule_group_obj.search([])
        schedule_groups.refresh_group_data()

        for shipping_schedule in shipping_schedules_refreshed:
            shipping_schedule._save_shipping_forecast()

        return True

    def _compute_forecast_values(self):
        self.ensure_one()
        company_id = self.env.company
        date_range = company_id._get_date_range()

        date_start = date_range[0][0]
        date_stop = date_range[-1][1]

        factory_available_qty = self._get_factory_available_qty(date_start, date_stop)[self.product_id.id]
        factory_available_qty_tmp = factory_available_qty

        previous_forecast = None
        for index, (date_start, date_stop) in enumerate(date_range):
            existing_forecasts = self.forecast_ids.filtered(
                lambda p: p.date >= date_start and p.date <= date_stop)

            forecast_sale_qty = sum(existing_forecasts.mapped("forecast_sale_qty"))

            for forecast in existing_forecasts:
                if previous_forecast:
                    starting_inventory_qty = previous_forecast.ending_inventory_qty
                else:
                    starting_inventory_qty = forecast.starting_inventory_qty

                if forecast.safety_inventory_qty_changed:
                    safety_inventory_qty = forecast.safety_inventory_qty
                else:
                    if self.env.company.manufacturing_period == "month":
                        safety_inventory_qty = forecast_sale_qty / 30 * self.safety_available_days
                    elif self.env.company.manufacturing_period == "week":
                        safety_inventory_qty = forecast_sale_qty / 7 * self.safety_available_days
                    else:
                        # day
                        safety_inventory_qty = forecast_sale_qty * self.safety_available_days

                if forecast.arriving_qty_apply_changed:
                    arriving_qty_apply = forecast.arriving_qty_apply
                else:
                    arriving_qty_apply = forecast.forecast_sale_qty + safety_inventory_qty - starting_inventory_qty
                    arriving_qty_apply = arriving_qty_apply if arriving_qty_apply >= 0 else 0

                arriving_qty_apply = self._get_qty_with_mpq(self.product_id, arriving_qty_apply)

                if forecast.arriving_qty_verify_changed:
                    arriving_qty_verify = forecast.arriving_qty_verify
                else:
                    arriving_qty_verify = arriving_qty_apply

                arriving_qty_verify = self._get_qty_with_mpq(self.product_id, arriving_qty_verify)

                arriving_qty_increase = arriving_qty_verify - forecast.arriving_qty_confirmed

                forecast_value = {}
                forecast_value["starting_inventory_qty"] = starting_inventory_qty
                forecast_value["arriving_qty_increase"] = arriving_qty_increase
                forecast_value["safety_inventory_qty"] = safety_inventory_qty
                forecast_value["arriving_qty_apply"] = arriving_qty_apply
                forecast_value["arriving_qty_verify"] = arriving_qty_verify
                forecast_value["arriving_qty_increase"] = arriving_qty_increase

                # 写回forecast
                forecast.write(forecast_value)

                previous_forecast = forecast

    def set_forecast_sale_qty(self, date_index, quantity, force_set=True):
        """ Save the forecast quantity:
        params date_index: The manufacturing period
        params quantity: The new total forecasted quantity
        """
        # Get the last date of current period
        self.ensure_one()
        date_start, date_stop = self.company_id._get_date_range()[date_index]
        existing_forecasts = self.forecast_ids.filtered(lambda f:
                                                        f.date >= date_start and f.date <= date_stop)

        forecast_sale_qty = float_round(float(quantity), precision_rounding=self.product_uom_id.rounding)
        forecast_sale_qty_to_add = forecast_sale_qty - sum(existing_forecasts.mapped('forecast_sale_qty'))

        for forecast in existing_forecasts:
            if forecast_sale_qty_to_add > 0:
                # 预测销售比原来计划大
                new_forecast_sale_qty = forecast.forecast_sale_qty + forecast_sale_qty_to_add
                forecast_sale_qty_to_add = 0
                forecast.write({
                    "forecast_sale_qty": new_forecast_sale_qty,
                    "forecast_sale_qty_changed": True,
                })
            elif forecast_sale_qty_to_add < 0:
                # 预测销售比原来计划小，需要做减法
                new_forecast_sale_qty = forecast.forecast_sale_qty + forecast_sale_qty_to_add
                if new_forecast_sale_qty < 0:
                    # 如果当期数量不够减，需要滚动到下一期
                    forecast_sale_qty_to_add = forecast_sale_qty_to_add + new_forecast_sale_qty
                    new_forecast_sale_qty = 0
                forecast.write({
                    "forecast_sale_qty": new_forecast_sale_qty,
                    "forecast_sale_qty_changed": True,
                })
        self._compute_forecast_values()
        return True

    def set_arriving_qty_apply(self, date_index, quantity, force_set=True):
        """ Save the forecast quantity:
        params date_index: The manufacturing period
        params quantity: The new total forecasted quantity
        """
        # Get the last date of current period
        self.ensure_one()
        date_start, date_stop = self.company_id._get_date_range()[date_index]
        existing_forecasts = self.forecast_ids.filtered(lambda f:
                                                        f.date >= date_start and f.date <= date_stop)

        arriving_qty_apply = float_round(float(quantity), precision_rounding=self.product_uom_id.rounding)
        arriving_qty_apply_to_add = arriving_qty_apply - sum(existing_forecasts.mapped('arriving_qty_apply'))

        for forecast in existing_forecasts:
            if arriving_qty_apply_to_add > 0:
                # 比原来数据大
                new_arriving_qty_apply = forecast.arriving_qty_apply + arriving_qty_apply_to_add
                arriving_qty_apply_to_add = 0
                forecast.write({
                    "arriving_qty_apply": new_arriving_qty_apply,
                    "arriving_qty_apply_changed": True,
                })
            elif arriving_qty_apply_to_add < 0:
                # 比原来数据小，需要做减法
                new_arriving_qty_apply = forecast.arriving_qty_apply + arriving_qty_apply_to_add
                if new_arriving_qty_apply < 0:
                    # 如果当期数量不够减，需要滚动到下一期
                    arriving_qty_apply_to_add = arriving_qty_apply_to_add + new_arriving_qty_apply
                    new_arriving_qty_apply = 0
                forecast.write({
                    "arriving_qty_apply": new_arriving_qty_apply,
                    "arriving_qty_apply_changed": True,
                })

        # 重新计算相关数据
        self._compute_forecast_values()
        return True

    def set_arriving_qty_verify(self, date_index, quantity, force_set=True):
        """ Save the forecast quantity:
        params date_index: The manufacturing period
        params quantity: The new total forecasted quantity
        """
        # Get the last date of current period
        self.ensure_one()
        date_start, date_stop = self.company_id._get_date_range()[date_index]
        existing_forecasts = self.forecast_ids.filtered(lambda f:
                                                        f.date >= date_start and f.date <= date_stop)

        arriving_qty_verify = float_round(float(quantity), precision_rounding=self.product_uom_id.rounding)
        arriving_qty_verify_to_add = arriving_qty_verify - sum(existing_forecasts.mapped('arriving_qty_verify'))

        for forecast in existing_forecasts:
            if arriving_qty_verify_to_add > 0:
                # 比原来数据大
                new_arriving_qty_verify = forecast.arriving_qty_verify + arriving_qty_verify_to_add
                arriving_qty_verify_to_add = 0
                forecast.write({
                    "arriving_qty_verify": new_arriving_qty_verify,
                    "arriving_qty_verify_changed": True,
                })
            elif arriving_qty_verify_to_add < 0:
                # 比原来数据小，需要做减法
                new_arriving_qty_verify = forecast.arriving_qty_verify + arriving_qty_verify_to_add
                if new_arriving_qty_verify < 0:
                    # 如果当期数量不够减，需要滚动到下一期
                    arriving_qty_verify_to_add = arriving_qty_verify_to_add + new_arriving_qty_verify
                    new_arriving_qty_verify = 0
                forecast.write({
                    "arriving_qty_verify": new_arriving_qty_verify,
                    "arriving_qty_verify_changed": True,
                })

        # 重新计算相关数据
        self._compute_forecast_values()
        return True

    def set_safety_inventory_qty(self, date_index, quantity, force_set=True):
        """ Save the forecast quantity:
        params date_index: The manufacturing period
        params quantity: The new total forecasted quantity
        """
        # Get the last date of current period
        self.ensure_one()
        date_start, date_stop = self.company_id._get_date_range()[date_index]
        existing_forecasts = self.forecast_ids.filtered(lambda f:
                                                        f.date >= date_start and f.date <= date_stop)

        safety_inventory_qty = float_round(float(quantity), precision_rounding=self.product_uom_id.rounding)
        existing_forecasts.write({
            "safety_inventory_qty": safety_inventory_qty,
            "safety_inventory_qty_changed": True,
        })

        # 重新计算相关数据
        self._compute_forecast_values()
        return True

    def _get_factory_available_qty(self, date_start, date_stop):
        """
            shipping_schedule的工厂可用库存算法：
            产品的 virtual_available - (从当前计划开始日期之后所有的forcast_arriving_qty-不是cancel和draft状态的出库)

            注意，由于无法确定退回的产品是那个期间的产品，对于发出后，又退回来的出库单。请直接修改完成的数量，不要创建反向调拨。
            否则会造成计划不准的情况。
        :param date_start:
        :param date_stop:
        :return: {”product_id“: available_qty}
        """

        rtn_value = {}
        for shipping_schedule in self:
            product = shipping_schedule.product_id
            available_qty = product.virtual_available

            #
            # 有其他店铺相同产品的计划，需要一起统计上。
            shipping_forecast_obj = self.env["web.sale.shipping.forecast"]
            search_domain = [("shipping_schedule_id.company_id", "=", shipping_schedule.company_id.id),
                             ("shipping_schedule_id.product_id", "=", product.id),
                             ("date", ">=", date_start), ]
            shipping_forecasts = shipping_forecast_obj.search(search_domain)
            arriving_qty_confirmed = sum(shipping_forecasts.mapped("arriving_qty_confirmed"))

            # 从当前计划开始日期之后，不是cancel和draft状态的出库
            stock_move_obj = self.env["stock.move"]
            search_domain = [("company_id", "=", shipping_schedule.company_id.id),
                             ("partner_id.is_web_shop", "=", True),
                             ("product_id", "=", product.id),
                             # ("date", ">=", date_start),
                             ('state', 'not in', ['cancel', 'draft']),
                             ('location_dest_id.usage', '=', 'customer'),
                             ('location_id.usage', '!=', 'inventory'),
                             ('picking_id.estimate_arriving_date', '>=', date_start),
                             ]
            outgoing_moves = stock_move_obj.search(search_domain)
            outgoing_move_qty = sum(outgoing_moves.mapped("product_uom_qty"))

            available_qty = available_qty - (arriving_qty_confirmed - outgoing_move_qty)

            rtn_value[product.id] = available_qty

        return rtn_value

    def _get_qty_with_mpq(self, product, quantity):
        mpq = product.minimum_package_qty
        mpq = mpq if mpq else 1
        if quantity % mpq > 0:
            quantity = quantity + (mpq - quantity % mpq)
        return quantity

    def _save_shipping_forecast(self):
        """
            根据Shipping schedule 创建shipping_forcast
        :return:
        """
        self.ensure_one()
        company_id = self.env.company
        date_range = company_id._get_date_range()

        date_start = date_range[0][0]
        date_stop = date_range[-1][1]

        # 可以用于发货的可用库存
        factory_available_qty = self._get_factory_available_qty(date_start, date_stop)[self.product_id.id]

        factory_available_qty_tmp = factory_available_qty

        previous_forecast = None

        for index, (date_start, date_stop) in enumerate(date_range):
            existing_forecasts = self.forecast_ids.filtered(
                lambda p: p.date >= date_start and p.date <= date_stop)

            if index == 0:
                # 如果是第一期，则使用当前店铺库存的可用库存
                starting_inventory_qty = self.qty_available
                # 预计到货库存，使用schedule的在途库存(临时，待后面和领星接口搞好，可以取实际在途)
                arriving_qty_existing = self.qty_shipped
            else:
                starting_inventory_qty = previous_forecast.ending_inventory_qty
                arriving_qty_existing = 0

            if existing_forecasts:
                if any(existing_forecasts.mapped('forecast_sale_qty_changed')):
                    # 如果已经有发货预测，并且预计销量只要有一个进行了人工修改，则forecast_sale_qty取现有数据
                    forecast_sale_qty = sum(existing_forecasts.mapped('forecast_sale_qty'))
                    forecast_sale_qty_changed = True
                else:
                    forecast_sale_qty = self.advised_monthly_sale_qty
                    forecast_sale_qty_changed = False

                if any(existing_forecasts.mapped('safety_inventory_qty_changed')):
                    # safety_inventory_qty如果发生了人工修改，则取期间内的最大值
                    safety_inventory_qty = max(existing_forecasts.mapped('safety_inventory_qty'))
                    safety_inventory_qty_changed = True
                else:
                    # 重置safety_inventory_qty为根据设置的可销售天数计算出来的安全库存量
                    safety_inventory_qty = forecast_sale_qty / 30 * self.safety_available_days
                    safety_inventory_qty_changed = False

                if any(existing_forecasts.mapped('arriving_qty_apply_changed')):
                    arriving_qty_apply = sum(existing_forecasts.mapped('arriving_qty_apply'))
                    arriving_qty_apply_changed = True
                else:
                    arriving_qty_apply = forecast_sale_qty + safety_inventory_qty - starting_inventory_qty
                    arriving_qty_apply = arriving_qty_apply if arriving_qty_apply > 0 else 0
                    arriving_qty_apply_changed = False

                arriving_qty_apply = self._get_qty_with_mpq(self.product_id, arriving_qty_apply)

                if any(existing_forecasts.mapped('arriving_qty_verify_changed')):
                    arriving_qty_verify = existing_forecasts.mapped('arriving_qty_verify')
                    arriving_qty_verify_changed = True
                else:
                    arriving_qty_verify = arriving_qty_apply
                    arriving_qty_verify_changed = False

                arriving_qty_verify = self._get_qty_with_mpq(self.product_id, arriving_qty_verify)

                # 几个数据的差额，用于回写到forecast中去。
                forecast_sale_qty_to_add = forecast_sale_qty - \
                                           sum(existing_forecasts.mapped('forecast_sale_qty'))
                arriving_qty_apply_to_add = arriving_qty_apply - \
                                            sum(existing_forecasts.mapped('arriving_qty_apply'))
                arriving_qty_verify_to_add = arriving_qty_verify - \
                                             sum(existing_forecasts.mapped('arriving_qty_verify'))

                offset = 0
                for forecast in existing_forecasts:
                    forecast_value = {}

                    if offset > 0:
                        arriving_qty_existing = 0

                    if forecast_sale_qty_to_add == 0:
                        forecast_value["forecast_sale_qty"] = forecast.forecast_sale_qty
                    elif forecast_sale_qty_to_add > 0:
                        # 预测销售比原来计划大
                        new_forecast_sale_qty = forecast.forecast_sale_qty + forecast_sale_qty_to_add
                        forecast_sale_qty_to_add = 0
                        forecast_value["forecast_sale_qty"] = new_forecast_sale_qty
                    elif forecast_sale_qty_to_add < 0:
                        # 预测销售比原来计划小，需要做减法
                        new_forecast_sale_qty = forecast.forecast_sale_qty + forecast_sale_qty_to_add
                        if new_forecast_sale_qty < 0:
                            # 如果当期数量不够减，需要滚动到下一期
                            forecast_sale_qty_to_add = forecast_sale_qty_to_add + new_forecast_sale_qty
                            new_forecast_sale_qty = 0
                        forecast_value["forecast_sale_qty"] = new_forecast_sale_qty

                    if arriving_qty_apply_to_add == 0:
                        forecast_value["arriving_qty_apply"] = forecast.arriving_qty_apply
                    elif arriving_qty_apply_to_add > 0:
                        # 预测销售比原来计划大
                        new_arriving_qty_apply = forecast.arriving_qty_apply + arriving_qty_apply_to_add
                        arriving_qty_apply_to_add = 0
                        forecast_value["arriving_qty_apply"] = new_arriving_qty_apply
                    elif arriving_qty_apply_to_add < 0:
                        # 预测销售比原来计划小，需要做减法
                        new_arriving_qty_apply = forecast.arriving_qty_apply + arriving_qty_apply_to_add
                        if new_arriving_qty_apply < 0:
                            # 如果当期数量不够减，需要滚动到下一期
                            arriving_qty_apply_to_add = arriving_qty_apply_to_add + new_arriving_qty_apply
                            new_arriving_qty_apply = 0
                        forecast_value["arriving_qty_apply"] = new_arriving_qty_apply

                    if arriving_qty_verify_to_add == 0:
                        forecast_value["arriving_qty_verify"] = forecast.arriving_qty_verify
                    elif arriving_qty_verify_to_add > 0:
                        # 预测销售比原来计划大
                        new_arriving_qty_verify = forecast.arriving_qty_verify + arriving_qty_verify_to_add
                        arriving_qty_verify_to_add = 0
                        forecast_value["arriving_qty_verify"] = new_arriving_qty_verify
                    elif arriving_qty_verify_to_add < 0:
                        # 预测销售比原来计划小，需要做减法
                        new_arriving_qty_verify = forecast.arriving_qty_verify + arriving_qty_verify_to_add
                        if new_arriving_qty_verify < 0:
                            # 如果当期数量不够减，需要滚动到下一期
                            arriving_qty_verify_to_add = arriving_qty_verify_to_add + new_arriving_qty_verify
                            new_arriving_qty_verify = 0
                        forecast_value["arriving_qty_verify"] = new_arriving_qty_verify

                    forecast_value["arriving_qty_increase"] = forecast_value[
                                                                  "arriving_qty_verify"] - forecast.arriving_qty_confirmed
                    forecast_value["safety_inventory_qty"] = safety_inventory_qty
                    forecast_value["forecast_sale_qty_changed"] = forecast_sale_qty_changed
                    forecast_value["arriving_qty_apply_changed"] = arriving_qty_apply_changed
                    forecast_value["arriving_qty_verify_changed"] = arriving_qty_verify_changed
                    forecast_value["safety_inventory_qty_changed"] = safety_inventory_qty_changed
                    forecast_value["arriving_qty_existing"] = arriving_qty_existing
                    forecast_value["starting_inventory_qty"] = starting_inventory_qty

                    # 写回forecast
                    forecast.write(forecast_value)

                # 设置上一个期间的计划为existing_forecasts中最后一个
                previous_forecast = existing_forecasts[-1]
            else:
                # 需要新建一个forecast
                forecast_value = {}

                # forecast_sale_qty使用建议的advised_monthly_sale_qty
                forecast_sale_qty = self.advised_monthly_sale_qty
                forecast_sale_qty_changed = False

                # 重置safety_inventory_qty为根据设置的可销售天数计算出来的安全库存量
                safety_inventory_qty = forecast_sale_qty / 30 * self.safety_available_days
                safety_inventory_qty_changed = False

                # arriving_qty_apply 根据计算设置默认值
                arriving_qty_apply = forecast_sale_qty + safety_inventory_qty - starting_inventory_qty
                arriving_qty_apply = arriving_qty_apply if arriving_qty_apply > 0 else 0

                arriving_qty_apply = self._get_qty_with_mpq(self.product_id, arriving_qty_apply)

                arriving_qty_verify = arriving_qty_apply
                arriving_qty_confirmed = 0

                arriving_qty_increase = arriving_qty_verify - arriving_qty_confirmed

                # 初始默认为0, 只有在计划confirm的时候才需要设置
                replenish_qty_required = 0
                procurement_launched = False
                replenished_qty = 0

                forecast_value['date'] = date_stop

                forecast_value["forecast_sale_qty"] = forecast_sale_qty
                forecast_value["forecast_sale_qty_changed"] = forecast_sale_qty_changed
                forecast_value["safety_inventory_qty"] = safety_inventory_qty
                forecast_value["safety_inventory_qty_changed"] = safety_inventory_qty_changed
                forecast_value["arriving_qty_existing"] = arriving_qty_existing
                forecast_value["arriving_qty_confirmed"] = arriving_qty_confirmed
                forecast_value["arriving_qty_apply"] = arriving_qty_apply
                forecast_value["arriving_qty_verify"] = arriving_qty_verify
                forecast_value["arriving_qty_increase"] = arriving_qty_increase
                forecast_value["starting_inventory_qty"] = starting_inventory_qty
                forecast_value["procurement_launched"] = procurement_launched
                forecast_value["replenished_qty"] = replenished_qty
                forecast_value["replenish_qty_required"] = replenish_qty_required
                forecast_value["shipping_schedule_id"] = self.id
                forecast = self.env["web.sale.shipping.forecast"].create(forecast_value)

                previous_forecast = forecast

    @api.model
    def run_scheduler(self, use_new_cursor=False, company_id=False):
        """ Call the scheduler. This function is intended to be run for all the companies at the same time, so
        we run functions as SUPERUSER to avoid intercompanies and access rights issues. """
        try:
            if use_new_cursor:
                cr = registry(self._cr.dbname).cursor()
                self = self.with_env(self.env(cr=cr))  # TDE FIXME

            self._create_shipping_schedule(use_new_cursor=use_new_cursor, company_id=company_id)

            if use_new_cursor:
                self._cr.commit()
                self._cr.close()
        finally:
            if use_new_cursor:
                try:
                    self._cr.close()
                except Exception:
                    pass
        return {}

    def _get_lead_times(self):
        """ Get the lead time for each product in self. The lead times are
        based on rules lead times + produce delay or supplier info delay.
        """
        lead_times = []
        for shipping_schedule in self:
            if shipping_schedule.shop_id and shipping_schedule.shop_id.partner_id \
                    and shipping_schedule.shop_id.partner_id.default_shipping_method_id:
                estimate_ship_days = shipping_schedule.shop_id.partner_id.default_shipping_method_id.estimate_ship_days
            else:
                estimate_ship_days = 30
            lead_times.append(estimate_ship_days)
        return lead_times

    def _get_arriving_qty_existing(self, date_start, date_stop):
        self.ensure_one()

        shipping_schedule = self

        stock_move_obj = self.env["stock.move"]
        search_domain = [("company_id", "=", shipping_schedule.company_id.id),
                         ("partner_id", "=", shipping_schedule.shop_id.partner_id.id),
                         ("product_id", "=", shipping_schedule.product_id.id),
                         ('state', 'not in', ['cancel', 'draft']),
                         ('location_dest_id.usage', '=', 'customer'),
                         ('location_id.usage', '!=', 'inventory'),
                         ('picking_id.estimate_arriving_date', '>=', date_start),
                         ('picking_id.estimate_arriving_date', '<=', date_stop),
                         # ('shop_product_id', '=', shipping_schedule.shop_product_id.id),
                         ]
        outgoing_moves = stock_move_obj.search(search_domain)
        outgoing_move_qty = sum(outgoing_moves.mapped("product_uom_qty"))
        return outgoing_move_qty

    def get_shipping_schedule_view_state(self):
        """ 获取shipping_schedule页面需要用到的数据。
        每一格预测包括的数据：
        - apply_qty: 运营申请的数量
        - schedule_qty: 物流确认的数量
        - order_qty: 已安排采购的数量
        - ship_qty: 已发出的数量
        :return:
        """
        company_id = self.env.company
        date_range = company_id._get_date_range()
        # 去年同比，前年同比
        date_range_year_minus_1 = company_id._get_date_range(years=1)
        date_range_year_minus_2 = company_id._get_date_range(years=2)

        read_fields = [
            'shop_product_id',
            'product_id',
            'shop_id',
            'seller_sku',
            'product_default_code',
            'product_name',
            'sale_qty_7',
            'sale_qty_14',
            'sale_qty_28',
            'advised_monthly_sale_qty',
            'qty_available',
            'qty_shipped',
            'warehouse_id',
        ]

        shipping_schedule_states = []
        for shipping_schedule in self:
            # 先检查最后日期范围的forecast是否已经生成，如果没有生成，则报错。
            date_start = date_range[-1][0]
            date_stop = date_range[-1][1]
            existing_forecasts = shipping_schedule.forecast_ids.filtered(
                lambda p: date_start <= p.date <= date_stop)
            if not existing_forecasts:
                raise UserError(
                    "The latest forecast does not exist, please wait shipping schedule auto generating task complete or regenerate shipping schedule manually.")

            shipping_schedule_state = shipping_schedule.read(read_fields)[0]
            # 可以用于发货的可用库存
            date_start = date_range[0][0]
            factory_available_qty = shipping_schedule._get_factory_available_qty(date_start, date_stop).get(
                shipping_schedule.product_id.id)
            shipping_schedule_state["factory_available_qty"] = factory_available_qty

            rounding = shipping_schedule.product_id.uom_id.rounding
            lead_time = sum(shipping_schedule._get_lead_times())
            precision_digits = max(0, int(-(log10(rounding))))
            shipping_schedule_state['precision_digits'] = precision_digits
            shipping_schedule_state['forecast_ids'] = []

            shipping_schedule_state['state'] = shipping_schedule.state

            if self.env.user.has_group("web_sale.group_web_sale_manager"):
                shipping_schedule_state['is_web_sale_manager'] = True
            else:
                shipping_schedule_state['is_web_sale_manager'] = False

            for index, (date_start, date_stop) in enumerate(date_range):
                forecast_values = {}
                key = ((date_start, date_stop), shipping_schedule.product_id, shipping_schedule.warehouse_id)
                key_y_1 = (date_range_year_minus_1[index], *key[1:])
                key_y_2 = (date_range_year_minus_2[index], *key[1:])
                existing_forecasts = shipping_schedule.forecast_ids.filtered(
                    lambda p: p.date >= date_start and p.date <= date_stop)

                forecast_values['date_start'] = date_start
                forecast_values['date_stop'] = date_stop

                forecast_values['arriving_qty_existing'] = shipping_schedule._get_arriving_qty_existing(date_start, date_stop)

                forecast_values['starting_inventory_qty'] = existing_forecasts[0].starting_inventory_qty
                forecast_values['ending_inventory_qty'] = existing_forecasts[-1].ending_inventory_qty
                forecast_values['forecast_sale_qty'] = sum(existing_forecasts.mapped('forecast_sale_qty'))
                forecast_values['arriving_qty_apply'] = sum(existing_forecasts.mapped('arriving_qty_apply'))
                forecast_values['arriving_qty_verify'] = sum(existing_forecasts.mapped('arriving_qty_verify'))
                forecast_values['arriving_qty_confirmed'] = sum(existing_forecasts.mapped('arriving_qty_confirmed'))
                forecast_values['arriving_qty_increase'] = sum(existing_forecasts.mapped('arriving_qty_increase'))
                forecast_values['safety_inventory_qty'] = max(existing_forecasts.mapped('safety_inventory_qty'))
                forecast_values['forecast_sale_qty_changed'] = any(
                    existing_forecasts.mapped('forecast_sale_qty_changed'))
                forecast_values['safety_inventory_qty_changed'] = any(
                    existing_forecasts.mapped('safety_inventory_qty_changed'))
                forecast_values['arriving_qty_apply_changed'] = any(
                    existing_forecasts.mapped('arriving_qty_apply_changed'))
                forecast_values['arriving_qty_verify_changed'] = any(
                    existing_forecasts.mapped('arriving_qty_verify_changed'))
                forecast_values['replenished_qty'] = sum(existing_forecasts.mapped('replenished_qty'))
                forecast_values['replenish_qty_required'] = sum(existing_forecasts.mapped('replenish_qty_required'))
                forecast_values['procurement_launched'] = all(
                    existing_forecasts.mapped('procurement_launched'))
                if forecast_values['procurement_launched']:
                    forecast_values['state'] = "launched"
                    forecast_values['forced_replenish'] = False
                    forecast_values['to_replenish'] = False
                else:
                    forecast_values['state'] = "to_launch"
                    forecast_values['forced_replenish'] = True
                    forecast_values['to_replenish'] = True

                shipping_schedule_state['forecast_ids'].append(forecast_values)
            shipping_schedule_states.append(shipping_schedule_state)
        return [p for p in shipping_schedule_states if p['id'] in self.ids]

    @api.model
    def get_shipping_schedule_main_view_state(self, domain=False):
        """ Return the global information about shipping schedule and a list of shipping
        schedules values with the domain.

        :param domain: domain for web.sale.shipping.schedule
        :return: values used by the client action in order to render the shipping schedule.
            - dates: list of period name
            - shipping_schedule_ids: list of shipping schedules values
            - manufacturing_period: list of periods (days, months or years)
            - company_id: user current company
        :rtype: dict
        """
        domain = domain or []

        shipping_schedules = self.env['web.sale.shipping.schedule'].search(domain or [])
        shipping_schedule_view_states = shipping_schedules.get_shipping_schedule_view_state()
        if not shipping_schedule_view_states:
            shipping_schedule_view_states = []

        return {
            'dates': self.env.company._date_range_to_str(),
            'shipping_schedule_ids': shipping_schedule_view_states,
            'manufacturing_period': self.env.company.manufacturing_period,
            'company_id': self.env.company.id,
        }

    def reset_safety_inventory_qty(self, date_index):
        date_start, date_stop = self.company_id._get_date_range()[date_index]
        forecast_ids = self.forecast_ids.filtered(lambda f:
                                                  f.date >= date_start and f.date <= date_stop)

        forecast_ids.write({
            'safety_inventory_qty_changed': False,
        })

        self._compute_forecast_values()
        return True

    def reset_forecast_sale_qty(self, date_index):
        date_start, date_stop = self.company_id._get_date_range()[date_index]
        forecast_ids = self.forecast_ids.filtered(lambda f:
                                                  f.date >= date_start and f.date <= date_stop)

        forecast_sale_qty = self.advised_monthly_sale_qty
        forecast_sale_qty_to_add = forecast_sale_qty - sum(forecast_ids.mapped('forecast_sale_qty'))

        for forecast in forecast_ids:
            if forecast_sale_qty_to_add == 0:
                forecast.write({
                    "forecast_sale_qty": forecast.forecast_sale_qty,
                    "forecast_sale_qty_changed": False,
                })
            elif forecast_sale_qty_to_add > 0:
                # 预测销售比原来计划大
                new_forecast_sale_qty = forecast.forecast_sale_qty + forecast_sale_qty_to_add
                forecast_sale_qty_to_add = 0
                forecast.write({
                    "forecast_sale_qty": new_forecast_sale_qty,
                    "forecast_sale_qty_changed": False,
                })
            elif forecast_sale_qty_to_add < 0:
                # 预测销售比原来计划小，需要做减法
                new_forecast_sale_qty = forecast.forecast_sale_qty + forecast_sale_qty_to_add
                if new_forecast_sale_qty < 0:
                    # 如果当期数量不够减，需要滚动到下一期
                    forecast_sale_qty_to_add = forecast_sale_qty_to_add + new_forecast_sale_qty
                    new_forecast_sale_qty = 0
                forecast.write({
                    "forecast_sale_qty": new_forecast_sale_qty,
                    "forecast_sale_qty_changed": False,
                })

        self._compute_forecast_values()
        return True

    def reset_arriving_qty_apply(self, date_index):
        date_start, date_stop = self.company_id._get_date_range()[date_index]
        forecast_ids = self.forecast_ids.filtered(lambda f:
                                                  f.date >= date_start and f.date <= date_stop)

        forecast_ids.write({
            'arriving_qty_apply_changed': False,
        })

        self._compute_forecast_values()
        return True

    def reset_arriving_qty_verify(self, date_index):
        date_start, date_stop = self.company_id._get_date_range()[date_index]
        forecast_ids = self.forecast_ids.filtered(lambda f:
                                                  f.date >= date_start and f.date <= date_stop)

        forecast_ids.write({
            'arriving_qty_verify_changed': False,
        })

        self._compute_forecast_values()
        return True

    def _get_procurement_extra_values(self, forecast_values):
        """ Extra values that could be added in the vals for procurement.

        return values pass to the procurement run method.
        rtype dict
        """

        if self.shop_id and self.shop_id.partner_id and self.shop_id.partner_id.default_shipping_method_id:
            estimate_ship_days = self.shop_id.partner_id.default_shipping_method_id.estimate_ship_days
        else:
            estimate_ship_days = 30

        date_planned = subtract(forecast_values['date_start'], days=estimate_ship_days)

        return {
            'date_planned': date_planned,
            'warehouse_id': self.warehouse_id,
        }

    def _compute_replenish_qty(self):
        company_id = self.env.company
        date_range = company_id._get_date_range()

        date_start = date_range[0][0]
        date_stop = date_range[-1][1]

        for shipping_schedule in self:

            if shipping_schedule.state != "logistics_confirmed":
                raise UserError(
                    "Only logistics confirmed schedule can be computed replenish quantity.")

            forecasts = shipping_schedule.forecast_ids.filtered(lambda p: date_start <= p.date <= date_stop)

            positive_forecasts = forecasts.filtered(lambda p: p.arriving_qty_increase > 0)
            positive_arriving_qty_increase = sum(positive_forecasts.mapped("arriving_qty_increase"))

            factory_available_qty = shipping_schedule._get_factory_available_qty(date_start, date_stop)[
                shipping_schedule.product_id.id]

            # 由于此时读取的可用库存已经使用了最新的confirm qty
            # 包括需要增加或扣减的到货数量。
            # 因此在计算补货的时候，对于减少的到货数量不需要补货，对于增加的到货数量，需要先全部补回去，然后再重算。
            factory_available_qty += positive_arriving_qty_increase

            for forecast in forecasts:
                if forecast.arriving_qty_increase == 0:
                    forecast.replenish_qty_required = 0
                    forecast.procurement_launched = True
                elif forecast.arriving_qty_increase < 0:
                    forecast.replenish_qty_required = 0
                    # 虽然不用发生实际补货，但是需要在补货操作中把arriving_qty_increase等数据置0
                    forecast.procurement_launched = False
                else:
                    # factory_available_qty = self._get_factory_available_qty(date_start, date_stop)[
                    #     self.product_id.id]
                    if float_compare(forecast.arriving_qty_increase, factory_available_qty,
                                     precision_rounding=shipping_schedule.product_uom_id.rounding) > 0:
                        forecast.replenish_qty_required = forecast.arriving_qty_increase - factory_available_qty
                        factory_available_qty = 0
                        forecast.procurement_launched = False
                    else:
                        forecast.replenish_qty_required = 0
                        factory_available_qty -= forecast.arriving_qty_increase
                        # 虽然不用发生实际补货，但是需要在补货操作中把arriving_qty_increase等数据置0
                        forecast.procurement_launched = False

    def action_sales_confirm(self):
        for shipping_schedule in self:
            if shipping_schedule.state == "draft":
                shipping_schedule.state = "sales_confirmed"

    def action_logistics_confirm(self):
        company_id = self.env.company
        date_range = company_id._get_date_range()

        date_start = date_range[0][0]
        date_stop = date_range[-1][1]

        for shipping_schedule in self:
            if shipping_schedule.state == "sales_confirmed":
                shipping_schedule.state = "logistics_confirmed"

                forecasts = shipping_schedule.forecast_ids.filtered(lambda p: date_start <= p.date <= date_stop)

                previous_forecast = None
                for forecast in forecasts:
                    if previous_forecast:
                        forecast.starting_inventory_qty = previous_forecast.ending_inventory_qty
                    forecast.arriving_qty_confirmed = forecast.arriving_qty_verify

                    previous_forecast = forecast

                # 在确认以后，计算补货数量。
                # 注意，这只是模拟计算，供参考使用。在真正补货时，由于其他店铺相同产品的计划确认后，会导致可用数量的变化，因此需要重算。
                shipping_schedule._compute_replenish_qty()

    def action_cancel_confirm(self):
        company_id = self.env.company
        date_range = company_id._get_date_range()

        date_start = date_range[0][0]
        date_stop = date_range[-1][1]

        for shipping_schedule in self:
            if shipping_schedule.state in ["sales_confirmed", "logistics_confirmed", "done"]:
                shipping_schedule.state = "draft"

                forecasts = shipping_schedule.forecast_ids.filtered(lambda p:
                                                                    date_start <= p.date <= date_stop
                                                                    )
                for forecast in forecasts:
                    forecast.arriving_qty_confirmed = forecast.arriving_qty_confirmed - forecast.arriving_qty_increase
                    forecast.replenish_qty_required = 0
                    if forecast.arriving_qty_increase == 0:
                        forecast.procurement_launched = True
                    else:
                        forecast.procurement_launched = False

    def action_replenish(self, based_on_lead_time=False):
        """ Run the procurement for production schedule in self. Once the
        procurements are launched, mark the forecast as launched (only used
        for state 'to_relaunch')

        :param based_on_lead_time: 2 replenishment options exists in MPS.
        based_on_lead_time means that the procurement for self will be launched
        based on lead times.
        e.g. period are daily and the product have a manufacturing period
        of 5 days, then it will try to run the procurements for the 5 first
        period of the schedule.
        If based_on_lead_time is False then it will run the procurement for the
        first period that need a replenishment
        """

        # 重新计算一次补货数量
        self._compute_replenish_qty()

        shipping_schedule_states = self.get_shipping_schedule_view_state()
        shipping_schedule_states = {mps['id']: mps for mps in shipping_schedule_states}
        procurements = []
        forecasts_values = []
        forecasts_to_set_as_launched = self.env['web.sale.shipping.forecast']

        shipping_schedule_to_replenish = self.filtered(lambda r: r.state == 'logistics_confirmed')

        for shipping_schedule in shipping_schedule_to_replenish:
            shipping_schedule_state = shipping_schedule_states[shipping_schedule.id]

            # 如果是套件，则直接对套件中的物料进行补货操作
            # Check for kit. If a kit and its component are both in the MPS we want to skip the
            # the kit procurement but instead only refill the components not in MPS
            bom = self.env['mrp.bom']._bom_find(
                shipping_schedule.product_id,
                company_id=shipping_schedule.company_id.id,
                bom_type='phantom')[shipping_schedule.product_id]
            product_ratio = []
            if bom:
                dummy, bom_lines = bom.explode(shipping_schedule.product_id, 1)
                product_ids = [l[0].product_id.id for l in bom_lines]
                product_ids_with_forecast = self.env['web.sale.shipping.schedule'].search([
                    ('company_id', '=', shipping_schedule.company_id.id),
                    ('warehouse_id', '=', shipping_schedule.warehouse_id.id),
                    ('product_id', 'in', product_ids)
                ]).product_id.ids
                product_ratio += [
                    (l[0], l[0].product_qty * l[1]['qty'])
                    for l in bom_lines if l[0].product_id.id not in product_ids_with_forecast
                ]

            # Cells with values 'to_replenish' means that they are based on
            # lead times. There is at maximum one forecast by schedule with
            # 'forced_replenish', it's the cell that need a modification with
            #  the smallest start date.
            # replenishment_field = based_on_lead_time and 'to_replenish' or 'forced_replenish'
            # forecasts_to_replenish = filter(lambda f: f[replenishment_field], shipping_schedule_state['forecast_ids'])

            forecasts_to_replenish = filter(lambda f: f["procurement_launched"] is False,
                                            shipping_schedule_state['forecast_ids'])
            for forecast in forecasts_to_replenish:
                existing_forecasts = shipping_schedule.forecast_ids.filtered(lambda p:
                                                                             forecast['date_start'] <= p.date <=
                                                                             forecast['date_stop'])
                extra_values = shipping_schedule._get_procurement_extra_values(forecast)
                quantity = forecast['replenish_qty_required']

                if quantity > 0:
                    if not bom:
                        procurements.append(self.env['procurement.group'].Procurement(
                            shipping_schedule.product_id,
                            quantity,
                            shipping_schedule.product_uom_id,
                            shipping_schedule.warehouse_id.lot_stock_id,
                            shipping_schedule.product_id.name,
                            '%s/%s/%s' % (shipping_schedule.shop_id.name,
                                          shipping_schedule.seller_sku,
                                          forecast["date_start"]),
                            shipping_schedule.company_id, extra_values
                        ))
                    else:
                        for bom_line, qty_ratio in product_ratio:
                            procurements.append(self.env['procurement.group'].Procurement(
                                bom_line.product_id,
                                quantity * qty_ratio,
                                bom_line.product_uom_id,
                                shipping_schedule.warehouse_id.lot_stock_id,
                                bom_line.product_id.name,
                                '%s/%s/%s' % (shipping_schedule.shop_id,
                                              shipping_schedule.seller_sku,
                                              forecast["date_start"]),
                                shipping_schedule.company_id, extra_values
                            ))

                forecasts_to_set_as_launched |= existing_forecasts

        if procurements:
            self.env['procurement.group'].with_context(skip_lead_time=True).run(procurements)

        for forecast in forecasts_to_set_as_launched:
            forecast.replenished_qty += forecast.replenish_qty_required

        forecasts_to_set_as_launched.write({
            'arriving_qty_increase': 0,
            'replenish_qty_required': 0,
            'procurement_launched': True,
        })
        shipping_schedule_to_replenish.write(
            {
                'state': 'done',
            }
        )

    def do_add_shipping_schedule_to_schedule_group(self):
        """
        导入选中的行到报关单中
        :return:
        """
        shipping_schedule_group_id = self.env.context.get('shipping_schedule_group_id')
        self.write({
            "shipping_schedule_group_id": shipping_schedule_group_id
        })
        shipping_schedule_group = self.env['web.sale.shipping.schedule.group'].browse([shipping_schedule_group_id])
        shipping_schedule_group.refresh_group_data()
        return
