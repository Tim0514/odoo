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
import logging
_logger = logging.getLogger(__name__)


_STATES = [
    ("draft", "Draft"),
    ("sales_confirmed", "Sales Confirmed"),
    ("logistics_confirmed", "Logistics Confirmed"),
    ("done", "Done"),
    ("canceled", "Canceled"),
]


class ShippingForecast(models.Model):
    _name = "web.sale.shipping.forecast"
    _order = 'date desc'
    _description = 'Product Shipping Forecast at Date'
    _check_company_auto = True
    _rec_name = "date"

    shipping_schedule_id = fields.Many2one('web.sale.shipping.schedule', required=True, ondelete='cascade', index=True, check_company=True)

    company_id = fields.Many2one(
        comodel_name="res.company", related="shipping_schedule_id.company_id", string="Company", store=True, index=True)

    shop_product_id = fields.Many2one("web.sale.shop.product", related="shipping_schedule_id.shop_product_id", index=True)

    date = fields.Date('Date', required=True, index=True)

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
    arriving_qty_shipped = fields.Integer(string="Shipped Arriving Qty", default=0)

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

    def name_get(self):
        result = []
        context = self.env.context
        if 'shop_product_id' in context.keys():
            shop_product_id = context['shop_product_id']
            domain = [("shop_product_id", "=", shop_product_id)]
            records = self.search(domain, order="date desc")
            # records = self.filtered(lambda r: r["shop_product_id"].id == shop_product_id)
            for record in records:
                name = record.date.strftime('%Y-%m')
                result.append((record.id, name))
            return result
        else:
            for record in self:
                name = "{} ({})".format(record.date.strftime('%Y-%m'), record.shop_product_id.seller_sku)  # 实现修改显示值名字
                result.append((record.id, name))
            return result
            # return super(ShippingForecast, self).name_get()

    def search(self, args, offset=0, limit=None, order=None, count=False):
        # 重写函数,返回指定记录
        args = args or []
        domain = []
        if self.env.context.get('shop_product_id', False):
            shop_product_id = self.env.context['shop_product_id']
            domain.extend([('shop_product_id', '=', shop_product_id)])
        args += domain
        return super(ShippingForecast, self).search(args, offset, limit, order, count)

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
    _order = "shop_id, seller_sku"

    # shop_warehouse_id = fields.Many2one("web.sale.warehouse", string='Web Shop Warehouse', readonly=True, )
    # shop_warehouse_name = fields.Char(
    #     string='Web Shop Warehouse', related="shop_warehouse_id.name",
    #     readonly=True, store=True, index=True, )

    shop_product_id = fields.Many2one(comodel_name="web.sale.shop.product", string="Shop Product",
                                      readonly=True, index=True, check_company=True)

    shop_id = fields.Many2one("web.sale.shop", string="Default Shop", store=True, index=True,
                                      related="shop_product_id.shop_id", check_company=True)

    company_id = fields.Many2one(
        comodel_name="res.company", related="shop_id.company_id", string="Company", store=True, index=True)

    warehouse_id = fields.Many2one(
        comodel_name="stock.warehouse", related="company_id.warehouse_id", string="Warehouse",
        store=True, index=True, check_company=True)

    product_id = fields.Many2one(
        comodel_name="product.product", related="shop_product_id.product_id", string="Product",
        store=True, readonly=True, index=True, check_company=True)
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

    sale_qty_7 = fields.Integer(string='7 Days Sale')
    sale_qty_14 = fields.Integer(string='14 Days Sale')
    sale_qty_28 = fields.Integer(string='28 Days Sale')
    sale_qty_30 = fields.Integer(string='30 Days Sale')
    sale_qty_30_y_1 = fields.Integer(string='30 Days Sale Last Year')

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

    need_focus = fields.Boolean(string="Need Focus", default=False, index=True)

    salesperson_id = fields.Many2one(
        comodel_name='res.users', related="shop_product_id.salesperson_id", string='Salesperson', index=True,
    )

    forecast_ids = fields.One2many('web.sale.shipping.forecast', 'shipping_schedule_id',
                                   'Forecasted quantity at date')

    shipping_schedule_group_id = fields.Many2one(comodel_name='web.sale.shipping.schedule.group',
        string='Shipping Schedule Group', ondelete="set null", index=True, check_company=True)

    sale_weight_factor = fields.Integer("Sale Weight Factor", default=100,
                                        help="Sale weight factor in group for allocating sale quantity.")

    safety_available_days = fields.Integer(string="Safety Available Days", required=True, default=45)

    available_days = fields.Integer(string="Available Days", compute="_compute_available_days")

    # 过去30天中，如果可售数量, 待调仓数量, 调仓中, 入库中 四个数据加起来，出现过0 则为True
    is_out_of_stock_occurred = fields.Boolean(string="Is out of stock occurred", default=False,
                                              help="Is out of stock occurred in last 30 days")

    is_too_much_inventory = fields.Boolean(string="Too much inventory", default=False,
                                        help="Current stock quantity can be sold more then 90 days.",
                                        compute="_compute_available_days")


    is_too_little_inventory = fields.Boolean(string="Too little inventory", default=False,
                                        help="Current stock quantity can be sold less then 30 days.",
                                        compute="_compute_available_days")

    replenish_increase_ignore_rate = fields.Float("Replenish Increase Ignore Rate", default=0.1,
        help="Replenish will be ignored if qty_increase/qty_confirmed <= this rate")

    @api.depends("qty_available", "advised_monthly_sale_qty")
    def _compute_available_days(self):
        for schedule in self:
            if schedule.advised_monthly_sale_qty > 0:
                schedule.available_days = schedule.qty_available / (schedule.advised_monthly_sale_qty / 30)
            else:
                schedule.available_days = -1
            if schedule.available_days > 90:
                schedule.is_too_much_inventory = True
                schedule.is_too_little_inventory = False
            elif 0 <= schedule.available_days < 30:
                schedule.is_too_much_inventory = False
                schedule.is_too_little_inventory = True
            else:
                schedule.is_too_much_inventory = False
                schedule.is_too_little_inventory = False


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

    def _refresh_sale_data(self, company_ids=False):
        """
        仅更新销量数据
        :param company_ids:
        :return:
        """
        if not company_ids:
            company_ids = self.env["res.company"].sudo().search([]).ids
            self = self.with_user(SUPERUSER_ID).with_context(allowed_company_ids=company_ids)

        first_day = start_of(fields.Date.today(), self.env.company.manufacturing_period)
        # 去掉时分秒
        first_day = datetime.strptime(first_day.strftime('%Y-%m-%d'), '%Y-%m-%d')

        web_sale_order_line_obj = self.env["web.sale.order.line"]

        domain = []
        shipping_schedules = self.search(domain)
        for shipping_schedule in shipping_schedules:
            sale_data_dict = web_sale_order_line_obj.get_product_sale_data(shipping_schedule.shop_product_id, first_day)
            sale_qty_7 = sale_data_dict.get("7")
            sale_qty_14 = sale_data_dict.get("14")
            sale_qty_28 = sale_data_dict.get("28")
            sale_qty_30 = sale_data_dict.get("30")
            sale_qty_30_y_1 = sale_data_dict.get("30_y_1")

            estimate_monthly_sale_qty_1, estimate_monthly_sale_qty_2, advised_monthly_sale_qty = \
                self._compute_estimate_monthly_sale(sale_qty_7, sale_qty_14, sale_qty_30)

            shipping_schedule_vals = {
                "sale_qty_7": sale_qty_7,
                "sale_qty_14": sale_qty_14,
                "sale_qty_28": sale_qty_28,
                "sale_qty_30": sale_qty_30,
                "sale_qty_30_y_1": sale_qty_30_y_1,
                "estimate_monthly_sale_qty_1": estimate_monthly_sale_qty_1,
                "estimate_monthly_sale_qty_2": estimate_monthly_sale_qty_2,
                "advised_monthly_sale_qty": advised_monthly_sale_qty,
            }
            shipping_schedule.write(shipping_schedule_vals)

        related_groups = shipping_schedules.shipping_schedule_group_id
        related_groups.refresh_group_data()
        return True

    def _create_shipping_schedule(self, company_ids=False, only_new_products=False):
        """
        :param use_new_cursor:
        :param company_ids: 如果不传入company_ids, 则只生成当前公司的发货计划
        :param only_new_products: 等于True时，只新建shipping_schedule中不存在的 产品的计划
        :return:
        """

        if not company_ids:
            company_ids = [self.env.company.id]

        first_day = start_of(fields.Date.today(), self.env.company.manufacturing_period)
        # 去掉时分秒
        first_day = datetime.strptime(first_day.strftime('%Y-%m-%d'), '%Y-%m-%d')
        schedule_year = first_day.year
        schedule_month = first_day.month

        shop_product_obj = self.env["web.sale.shop.product"]
        shop_inventory_obj = self.env["web.sale.shop.inventory"]
        product_weekly_stat_obj = self.env["web.sale.shop.product.weekly.stat"]
        web_sale_order_line_obj = self.env["web.sale.order.line"]

        shop_inventories_by_product = shop_inventory_obj.get_closest_inventories(company_ids, first_day)
        # domain = [
        #     ("company_id", "in", company_ids),
        #     ("product_id", "!=", False),
        #     ("is_latest_inventory", "=", True),
        # ]
        # shop_inventories = shop_inventory_obj.search(domain)
        # shop_inventories_by_product = {}
        # for shop_inventory in shop_inventories:
        #     shop_inventories_by_product.setdefault(shop_inventory.shop_product_id.id, shop_inventory)

        domain = []
        shipping_schedules = self.search(domain)
        shipping_schedules_by_product = {}
        for shipping_schedule in shipping_schedules:
            shipping_schedules_by_product.setdefault(shipping_schedule.shop_product_id.id, shipping_schedule)

        # 仅对 开启了发货计划管理的店铺中，已配对并且在售的产品 生成发货计划
        domain = [
            ("company_id", "in", company_ids),
            ("shop_id.enable_shipping_schedule", "=", True),
            ("product_id", "!=", False),
            ("state", "in", ["new", "normal"]),
        ]
        shop_products = shop_product_obj.search(domain)

        if only_new_products:
            new_shop_products = []
            for shop_product in shop_products:
                shipping_schedule = shipping_schedules_by_product.get(shop_product.id)
                if not shipping_schedule or shipping_schedule.state == "canceled":
                    new_shop_products.append(shop_product)
            shop_products = new_shop_products

        shipping_schedules_refreshed = []

        for shop_product in shop_products:
            shop_inventory = shop_inventories_by_product.get(shop_product.id)
            if shop_inventory:

                sale_data_dict = web_sale_order_line_obj.get_product_sale_data(shop_product, first_day)
                sale_qty_7 = sale_data_dict.get("7")
                sale_qty_14 = sale_data_dict.get("14")
                sale_qty_28 = sale_data_dict.get("28")
                sale_qty_30 = sale_data_dict.get("30")
                sale_qty_30_y_1 = sale_data_dict.get("30_y_1")

                estimate_monthly_sale_qty_1, estimate_monthly_sale_qty_2, advised_monthly_sale_qty = \
                    self._compute_estimate_monthly_sale(sale_qty_7, sale_qty_14, sale_qty_30)

                shipping_schedule_vals = {
                    "shop_product_id": shop_inventory.shop_product_id.id,
                    "schedule_year": schedule_year,
                    "schedule_month": schedule_month,
                    "qty_available": shop_inventory.sellable_quantity,
                    "qty_shipped": shop_inventory.get_shipped_quantity(),
                    "sale_qty_7": sale_qty_7,
                    "sale_qty_14": sale_qty_14,
                    "sale_qty_28": sale_qty_28,
                    "sale_qty_30": sale_qty_30,
                    "sale_qty_30_y_1": sale_qty_30_y_1,
                    "estimate_monthly_sale_qty_1": estimate_monthly_sale_qty_1,
                    "estimate_monthly_sale_qty_2": estimate_monthly_sale_qty_2,
                    "advised_monthly_sale_qty": advised_monthly_sale_qty,
                    "is_out_of_stock_occurred": shop_inventory.is_out_of_stock_occurred,
                    "state": "draft",
                }
            else:
                shipping_schedule_vals = {
                    "shop_product_id": shop_product.id,
                    "schedule_year": schedule_year,
                    "schedule_month": schedule_month,
                    "qty_available": 0,
                    "qty_shipped": 0,
                    "sale_qty_7": 0,
                    "sale_qty_14": 0,
                    "sale_qty_28": 0,
                    "sale_qty_30": 0,
                    "sale_qty_30_y_1": 0,
                    "estimate_monthly_sale_qty_1": 0,
                    "estimate_monthly_sale_qty_2": 0,
                    "advised_monthly_sale_qty": 0,
                    "is_out_of_stock_occurred": True,
                    "state": "draft",
                }

            shipping_schedule = shipping_schedules_by_product.get(shop_product.id)
            if shipping_schedule:
                shipping_schedule.write(shipping_schedule_vals)
            else:
                shipping_schedule = self.create(shipping_schedule_vals)

            shipping_schedules_refreshed.append(shipping_schedule)

        shipping_schedules_refreshed = self.env["web.sale.shipping.schedule"].concat(*shipping_schedules_refreshed)

        # 把所有shipping_schedules中产品状态为停售，或清仓的产品的计划状态改为canceled
        domain = [
            ("company_id", "in", company_ids),
            ("state", "!=", "canceled"),
            "|",
                ("shop_id.enable_shipping_schedule", "!=", True),
                "|",
                    ("product_id", "=", False),
                    ("shop_product_id.state", "not in", ["new", "normal"]),
        ]
        shipping_schedules_to_cancel = self.search(domain)
        shipping_schedules_to_cancel.write({"state": "canceled"})

        # 给所有未设置shipping_schedule_group的计划设置为默认group
        domain = [
            ("company_id", "in", company_ids),
            ("shipping_schedule_group_id", "=", False),
        ]
        shipping_schedules_without_group = self.search(domain)
        # shipping_schedules_without_group = filter(lambda r: not r.shipping_schedule_group_id, shipping_schedules_refreshed)
        for shipping_schedule in shipping_schedules_without_group:
            shop_id = shipping_schedule.shop_id
            shipping_schedule_group_id = shop_id.default_shipping_schedule_group_id
            if not shipping_schedule_group_id:
                # 如果shop没有默认的 计划组，则新建一个。
                shop_id._create_default_shipping_schedule_group_id()
                shipping_schedule_group_id = shop_id.default_shipping_schedule_group_id
            shipping_schedule.shipping_schedule_group_id = shipping_schedule_group_id

        # 重新计算受到影响的shipping_schedule_group的相关数据, 只有计算方法不是"by_product"的组才会受到影响
        related_groups = (shipping_schedules_refreshed + shipping_schedules_to_cancel + shipping_schedules_without_group).shipping_schedule_group_id
        related_groups.refresh_group_data()

        # 对受到影响的发货计划重新生成forecast
        related_groups = related_groups.filtered(lambda r: r.sale_qty_compute_method != "by_product")
        for shipping_schedule in (shipping_schedules_refreshed + related_groups.shipping_schedule_ids):
            shipping_schedule._save_shipping_forecast()

        return True

    def _compute_forecast_values(self):
        self.ensure_one()
        company_id = self.env.company
        date_range = self._get_max_date_range()

        date_start = date_range[0][0]
        date_stop = date_range[-1][1]

        factory_available_qty = self._get_factory_available_qty(date_start)[self.product_id.id]
        factory_available_qty_tmp = factory_available_qty

        previous_forecast = None
        for index, (date_start, date_stop) in enumerate(date_range):
            if index == 0:
                is_first_period = True
            else:
                is_first_period = False

            existing_forecasts = self.forecast_ids.filtered(
                lambda p: p.date >= date_start and p.date <= date_stop)

            if is_first_period:
                # 为防止编制计划时有提前到货的情况，第一期计划作如下处理
                # 使用当前店铺库存 - 本月到货数量中已到货的数量 为期初库存
                # 并且除了预测销售数量可以修改以外，其他数据都不允许修改。
                #
                arrived_qty = self._get_arriving_qty_arrived(date_start, date_stop)
                starting_inventory_qty = self.qty_available - arrived_qty

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
                    if self.env.company.manufacturing_period == "month":
                        safety_inventory_qty = forecast_sale_qty / 30 * self.safety_available_days
                    elif self.env.company.manufacturing_period == "week":
                        safety_inventory_qty = forecast_sale_qty / 7 * self.safety_available_days
                    else:
                        # day
                        safety_inventory_qty = forecast_sale_qty * self.safety_available_days
                    safety_inventory_qty_changed = False


                forecast_sale_qty_to_add = forecast_sale_qty - \
                                           sum(existing_forecasts.mapped('forecast_sale_qty'))

                offset = 0
                for forecast in existing_forecasts:
                    forecast_value = {}

                    if not previous_forecast:
                        forecast_value["starting_inventory_qty"] = starting_inventory_qty

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

                    forecast_value["forecast_sale_qty_changed"] = forecast_sale_qty_changed
                    forecast_value["safety_inventory_qty"] = safety_inventory_qty
                    forecast_value["safety_inventory_qty_changed"] = safety_inventory_qty_changed
                    forecast_value["arriving_qty_verify"] = forecast.arriving_qty_confirmed
                    forecast_value["arriving_qty_verify_changed"] = True
                    forecast_value["arriving_qty_increase"] = 0
                    forecast_value["procurement_launched"] = False

                    # 写回forecast
                    forecast.write(forecast_value)

                    previous_forecast = forecast
            else:
                starting_inventory_qty = previous_forecast.ending_inventory_qty

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
                    if self.env.company.manufacturing_period == "month":
                        safety_inventory_qty = forecast_sale_qty / 30 * self.safety_available_days
                    elif self.env.company.manufacturing_period == "week":
                        safety_inventory_qty = forecast_sale_qty / 7 * self.safety_available_days
                    else:
                        # day
                        safety_inventory_qty = forecast_sale_qty * self.safety_available_days
                    safety_inventory_qty_changed = False

                if any(existing_forecasts.mapped('arriving_qty_apply_changed')):
                    arriving_qty_apply = sum(existing_forecasts.mapped('arriving_qty_apply'))
                    arriving_qty_apply = self._get_qty_with_mpq(self.product_id, arriving_qty_apply)
                    arriving_qty_apply_changed = True
                else:
                    arriving_qty_apply = forecast_sale_qty + safety_inventory_qty - starting_inventory_qty
                    arriving_qty_apply = arriving_qty_apply if arriving_qty_apply > 0 else 0
                    arriving_qty_apply = self._get_qty_with_mpq(self.product_id, arriving_qty_apply)

                    # 如果本次预测增加的数量小于补货比例，则保持原有数量，不补货
                    arriving_qty_confirmed = sum(existing_forecasts.mapped('arriving_qty_confirmed'))
                    if arriving_qty_confirmed > 0 and arriving_qty_apply > arriving_qty_confirmed \
                            and (
                            arriving_qty_apply - arriving_qty_confirmed) / arriving_qty_confirmed < self.replenish_increase_ignore_rate:
                        arriving_qty_apply = sum(existing_forecasts.mapped('arriving_qty_apply'))
                    arriving_qty_apply_changed = False

                if any(existing_forecasts.mapped('arriving_qty_verify_changed')):
                    arriving_qty_verify = sum(existing_forecasts.mapped('arriving_qty_verify'))
                    arriving_qty_verify = self._get_qty_with_mpq(self.product_id, arriving_qty_verify)
                    arriving_qty_verify_changed = True
                else:
                    arriving_qty_verify = arriving_qty_apply
                    arriving_qty_verify = self._get_qty_with_mpq(self.product_id, arriving_qty_verify)
                    arriving_qty_verify_changed = False

                # 几个数据的差额，用于回写到forecast中去
                forecast_sale_qty_to_add = forecast_sale_qty - \
                                           sum(existing_forecasts.mapped('forecast_sale_qty'))
                arriving_qty_apply_to_add = arriving_qty_apply - \
                                            sum(existing_forecasts.mapped('arriving_qty_apply'))
                arriving_qty_verify_to_add = arriving_qty_verify - \
                                             sum(existing_forecasts.mapped('arriving_qty_verify'))

                offset = 0
                for forecast in existing_forecasts:
                    forecast_value = {}

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

                    forecast_value["arriving_qty_increase"] = forecast_value["arriving_qty_verify"] \
                                                              - forecast.arriving_qty_confirmed
                    forecast_value["safety_inventory_qty"] = safety_inventory_qty
                    forecast_value["forecast_sale_qty_changed"] = forecast_sale_qty_changed
                    forecast_value["arriving_qty_apply_changed"] = arriving_qty_apply_changed
                    forecast_value["arriving_qty_verify_changed"] = arriving_qty_verify_changed
                    forecast_value["safety_inventory_qty_changed"] = safety_inventory_qty_changed
                    forecast_value["starting_inventory_qty"] = starting_inventory_qty

                    # 写回forecast
                    forecast.write(forecast_value)
                    previous_forecast = forecast
        return True

    def set_forecast_sale_qty(self, date_index, quantity, force_set=True):
        """ Save the forecast quantity:
        params date_index: The manufacturing period
        params quantity: The new total forecasted quantity
        """
        # Get the last date of current period
        self.ensure_one()
        date_start, date_stop = self._get_max_date_range()[date_index]
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
        date_start, date_stop = self._get_max_date_range()[date_index]
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
        date_start, date_stop = self._get_max_date_range()[date_index]
        existing_forecasts = self.forecast_ids.filtered(lambda f:
                                                        f.date >= date_start and f.date <= date_stop)

        arriving_qty_verify = float_round(float(quantity), precision_rounding=self.product_uom_id.rounding)

        # # 如果设置的数量小于已发货数量，则报错。
        # if arriving_qty_verify < self._get_arriving_qty_shipped(date_start, date_stop):
        #     raise UserError("New quantity can't be smaller than shipped quantity.")

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
        date_start, date_stop = self._get_max_date_range()[date_index]
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


    def _check_arriving_qty_shipped(self, date_range):
        """
            由于已发货产品的到货日期不一定会落在相应的forecast期间，并且有可能会不按计划多发，
            因此在计算实际新增发货的数量时，是将全部已发货减去全部确认到货得到的差值，如果比新增发货多，则不会产生实际的新增发货。
            而不是在每一期上计算。

            如果已发货数量比计划的到货数量大，则强制将多出的数量应用于新增的计划到货数量，
            直到全部的新增计划到货数量扣减完毕，或者是多出的数量被分配完毕
        """
        # Get the last date of current period
        self.ensure_one()

        date_start = date_range[0][0]
        date_stop = date_range[-1][1]

        existing_forecasts = self.forecast_ids.filtered(lambda f:
                                                        f.date >= date_start and f.date <= date_stop)

        arriving_qty_shipped = self._get_arriving_qty_shipped(date_start, date_stop)
        arriving_qty_verify = sum(existing_forecasts.mapped('arriving_qty_verify'))
        arriving_qty_confirmed = sum(existing_forecasts.mapped('arriving_qty_confirmed'))

        arriving_qty_excess = arriving_qty_shipped - arriving_qty_confirmed

        if arriving_qty_excess <= 0:
            # 如果没有超出数量，则直接返回True
            return True

        for index, (date_start, date_stop) in enumerate(date_range):
            existing_forecasts = self.forecast_ids.filtered(lambda f:
                                                            f.date >= date_start and f.date <= date_stop)
            for forecast in existing_forecasts:
                if arriving_qty_excess > 0 and forecast.arriving_qty_increase >= arriving_qty_excess:
                    forecast.write({
                        # "arriving_qty_verify": forecast.arriving_qty_confirmed + arriving_qty_excess,
                        "arriving_qty_confirmed": forecast.arriving_qty_confirmed + arriving_qty_excess,
                        "arriving_qty_increase": forecast.arriving_qty_increase - arriving_qty_excess,
                        # "arriving_qty_verify_changed": True,
                    })
                    arriving_qty_excess = 0
                elif arriving_qty_excess > 0:
                    arriving_qty_excess = arriving_qty_excess - forecast.arriving_qty_increase
                    forecast.write({
                        # "arriving_qty_verify": arriving_qty_verify,
                        "arriving_qty_confirmed": forecast.arriving_qty_confirmed + forecast.arriving_qty_increase,
                        "arriving_qty_increase": 0,
                        # "arriving_qty_verify_changed": True,
                    })


        # 如果多发的数量不够冲抵新增的发货数量。则写回到到货的计划月份。
        for index, (date_start, date_stop) in enumerate(date_range):
            existing_forecasts = self.forecast_ids.filtered(lambda f:
                                                            f.date >= date_start and f.date <= date_stop)
            arriving_qty_shipped = self._get_arriving_qty_shipped(date_start, date_stop)
            for forecast in existing_forecasts:
                if arriving_qty_excess > 0 and arriving_qty_shipped - forecast.arriving_qty_confirmed > 0:
                    if arriving_qty_excess >= arriving_qty_shipped - forecast.arriving_qty_confirmed:
                        arriving_qty_excess = arriving_qty_excess - (
                                    arriving_qty_shipped - forecast.arriving_qty_confirmed)
                        forecast.write({
                            "arriving_qty_verify": arriving_qty_shipped,
                            "arriving_qty_confirmed": arriving_qty_shipped,
                            # "arriving_qty_increase": forecast.arriving_qty_increase - arriving_qty_excess,
                            "arriving_qty_verify_changed": True,
                        })
                    else:
                        forecast.write({
                            "arriving_qty_verify": forecast.arriving_qty_confirmed + arriving_qty_excess,
                            "arriving_qty_confirmed": forecast.arriving_qty_confirmed + arriving_qty_excess,
                            # "arriving_qty_increase": forecast.arriving_qty_increase - arriving_qty_excess,
                            "arriving_qty_verify_changed": True,
                        })
                        arriving_qty_excess = 0

        # 重新计算相关数据
        self._compute_forecast_values()
        return True

    def _get_existing_qty_unallocated(self, date_start, date_stop):
        self.ensure_one()

        shipping_schedule = self

        # 从当前计划开始日期之后，不是cancel和draft状态的出库
        stock_move_obj = self.env["stock.move"]
        search_domain = [("company_id", "=", shipping_schedule.company_id.id),
                         ("partner_id", "=", shipping_schedule.shop_id.partner_id.id),
                         ('picking_id.move_document_type', '=', 'sale_out'),
                         ("shop_product_id", "=", shipping_schedule.shop_product_id.id),
                         ('state', 'not in', ['cancel', 'draft']),
                         ('shipping_forecast_id', '=', False),
                         ('picking_id.estimate_arriving_date', '>=', date_start)
                         ]
        moves = stock_move_obj.search(search_domain)
        qty = sum(moves.mapped("product_uom_qty"))

        return qty


    def _get_factory_available_qty(self, date_start):
        """
            shipping_schedule的工厂可用库存算法：
            产品的 virtual_available - (从当前计划开始日期之后所有的forcast_arriving_qty-不是cancel和draft状态的出库)

            注意，由于无法确定退回的产品是那个期间的产品，对于发出后，又退回来的出库单。请直接修改完成的数量，不要创建反向调拨。
            否则会造成计划不准的情况。
        :param date_start:
        :return: {”product_id“: available_qty}
        """

        rtn_value = {}
        for shipping_schedule in self:

            # 限定到本地库存位置
            # product = shipping_schedule.product_id.with_context(allowed_company_ids=[shipping_schedule.company_id.id])
            product = shipping_schedule.product_id.with_context(location=shipping_schedule.warehouse_id.lot_stock_id.id)
            available_qty = product.virtual_available

            # 有其他店铺相同产品的计划，需要一起统计上，因此使用product_id来汇总，而不是shop_product_id。
            shipping_forecast_obj = self.env["web.sale.shipping.forecast"]
            search_domain = [("shipping_schedule_id.company_id", "=", shipping_schedule.company_id.id),
                             ("shipping_schedule_id.product_id", "=", product.id),
                             ("date", ">=", date_start),
                             ]
            shipping_forecasts = shipping_forecast_obj.search(search_domain)
            arriving_qty_confirmed = sum(shipping_forecasts.mapped("arriving_qty_confirmed"))

            # 物流已确认的发货预测中，可释放的库存
            negative_arriving_qty_increase = sum(shipping_forecasts.filtered(lambda r: r.shipping_schedule_id.state=="logistics_confirmed" and r.arriving_qty_increase < 0).mapped("arriving_qty_increase"))
            negative_arriving_qty_increase = abs(negative_arriving_qty_increase)

            # 从当前计划开始日期之后，不是cancel, draft状态的出库
            stock_move_obj = self.env["stock.move"]
            search_domain = [("company_id", "=", shipping_schedule.company_id.id),
                             ("partner_id.is_web_shop", "=", True),
                             ("product_id", "=", product.id),
                             ('state', 'not in', ['cancel', 'draft']),
                             ('move_document_type', '=', 'sale_out'),
                             ('picking_id.estimate_arriving_date', '>=', date_start),
                             ]
            outgoing_done_moves = stock_move_obj.search(search_domain)
            outgoing_done_qty = sum(outgoing_done_moves.mapped("product_uom_qty"))

            # 从当前计划开始日期之后，draft状态的出库, 由领星同步下来的，也需要扣减可用库存
            stock_move_obj = self.env["stock.move"]
            search_domain = [("company_id", "=", shipping_schedule.company_id.id),
                             ("partner_id.is_web_shop", "=", True),
                             ("product_id", "=", product.id),
                             ('state', 'in', ['draft']),
                             ('picking_id.lx_shipment_id', "!=", False),
                             ('move_document_type', '=', 'sale_out'),
                             ('picking_id.estimate_arriving_date', '>=', date_start),
                             ]
            outgoing_draft_moves = stock_move_obj.search(search_domain)
            outgoing_draft_qty = sum(outgoing_draft_moves.mapped("product_uom_qty"))

            available_qty = available_qty - outgoing_draft_qty

            """
                实际可用于新增计划的库存 = virtual_available - 尚未发货的数量
                尚未发货的数量 = arriving_qty_confirmed - 已发货的数量（包括confirm, waiting, done等）
                由于已发货的数量有可能不在计划中，因此如果已发货的数量 > arriving_qty_confirmed 此时 尚未发货的数量 = 0
            """
            if arriving_qty_confirmed - outgoing_done_qty - outgoing_draft_qty > 0:
                # 计划内正常处理方式
                available_qty = available_qty - (arriving_qty_confirmed - outgoing_done_qty - outgoing_draft_qty) + negative_arriving_qty_increase
            else:
                # 计划外处理方式
                available_qty = available_qty + negative_arriving_qty_increase

            # if product.id == 5623:
            #     _logger.warning("---------------------------")
            #     _logger.warning("System Context: %s" % str(self.env.context))
            #     _logger.warning("Original Context: %s" % str(shipping_schedule.product_id._context))
            #     _logger.warning("New Context: %s" % str(product._context))
            #     _logger.warning(product.qty_available)
            #     _logger.warning("**************************")

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
        date_range = self._get_max_date_range()

        date_start = date_range[0][0]
        date_stop = date_range[-1][1]

        # 可以用于发货的可用库存
        # factory_available_qty = self._get_factory_available_qty(date_start, date_stop)[self.product_id.id]
        #
        # factory_available_qty_tmp = factory_available_qty

        previous_forecast = None

        for index, (date_start, date_stop) in enumerate(date_range):
            if index == 0:
                is_first_period = True
            else:
                is_first_period = False

            existing_forecasts = self.forecast_ids.filtered(
                lambda p: p.date >= date_start and p.date <= date_stop)

            if is_first_period:
                # 为防止编制计划时有提前到货的情况，第一期计划作如下处理
                # 使用当前店铺库存 - 本月到货数量中已到货的数量 为期初库存
                # 并且除了预测销售数量可以修改以外，其他数据都不允许修改。
                # 安全库存数量根据预测销售数量计算
                # arriving_qty_verify 设置为和arriving_qty_verify相同
                # arriving_qty_increase = 0

                arrived_qty = self._get_arriving_qty_arrived(date_start, date_stop)
                starting_inventory_qty = self.qty_available - arrived_qty

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
                        if self.env.company.manufacturing_period == "month":
                            safety_inventory_qty = forecast_sale_qty / 30 * self.safety_available_days
                        elif self.env.company.manufacturing_period == "week":
                            safety_inventory_qty = forecast_sale_qty / 7 * self.safety_available_days
                        else:
                            # day
                            safety_inventory_qty = forecast_sale_qty * self.safety_available_days
                        safety_inventory_qty_changed = False

                    forecast_sale_qty_to_add = forecast_sale_qty - \
                                               sum(existing_forecasts.mapped('forecast_sale_qty'))

                    offset = 0
                    for forecast in existing_forecasts:
                        forecast_value = {}

                        if not previous_forecast:
                            forecast_value["starting_inventory_qty"] = starting_inventory_qty

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

                        forecast_value["forecast_sale_qty_changed"] = forecast_sale_qty_changed
                        forecast_value["safety_inventory_qty"] = safety_inventory_qty
                        forecast_value["safety_inventory_qty_changed"] = safety_inventory_qty_changed
                        forecast_value["arriving_qty_verify"] = forecast.arriving_qty_confirmed
                        forecast_value["arriving_qty_verify_changed"] = True
                        forecast_value["arriving_qty_increase"] = 0
                        forecast_value["procurement_launched"] = False

                        # 写回forecast
                        forecast.write(forecast_value)

                        previous_forecast = forecast


                else:
                    # 需要新建一个forecast，但是只有预测销售数量，安全库存数据，其他全为0
                    forecast_value = {}

                    # forecast_sale_qty使用建议的advised_monthly_sale_qty
                    forecast_sale_qty = self.advised_monthly_sale_qty

                    # 重置safety_inventory_qty为根据设置的可销售天数计算出来的安全库存量
                    if self.env.company.manufacturing_period == "month":
                        safety_inventory_qty = forecast_sale_qty / 30 * self.safety_available_days
                    elif self.env.company.manufacturing_period == "week":
                        safety_inventory_qty = forecast_sale_qty / 7 * self.safety_available_days
                    else:
                        # day
                        safety_inventory_qty = forecast_sale_qty * self.safety_available_days

                    # arriving_qty_apply 根据计算设置默认值
                    arriving_qty_apply = 0
                    arriving_qty_verify = 0
                    arriving_qty_confirmed = 0
                    arriving_qty_increase = arriving_qty_verify - arriving_qty_confirmed

                    # 初始默认为0, 只有在计划confirm的时候才需要设置
                    replenish_qty_required = 0
                    replenished_qty = 0

                    forecast_value['date'] = date_stop
                    forecast_value["starting_inventory_qty"] = starting_inventory_qty
                    forecast_value["forecast_sale_qty"] = forecast_sale_qty
                    forecast_value["forecast_sale_qty_changed"] = False
                    forecast_value["safety_inventory_qty"] = safety_inventory_qty
                    forecast_value["safety_inventory_qty_changed"] = False
                    forecast_value["arriving_qty_apply"] = arriving_qty_apply
                    forecast_value["arriving_qty_apply_changed"] = False
                    forecast_value["arriving_qty_verify"] = arriving_qty_verify
                    forecast_value["arriving_qty_verify_changed"] = False
                    forecast_value["arriving_qty_increase"] = arriving_qty_increase
                    forecast_value["arriving_qty_confirmed"] = arriving_qty_confirmed
                    forecast_value["replenished_qty"] = replenished_qty
                    forecast_value["replenish_qty_required"] = replenish_qty_required
                    forecast_value["procurement_launched"] = False
                    forecast_value["shipping_schedule_id"] = self.id
                    forecast = self.env["web.sale.shipping.forecast"].create(forecast_value)
                    previous_forecast = forecast
            else:
                # 不是第一期预测
                starting_inventory_qty = previous_forecast.ending_inventory_qty
                arriving_qty_shipped = 0

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
                        if self.env.company.manufacturing_period == "month":
                            safety_inventory_qty = forecast_sale_qty / 30 * self.safety_available_days
                        elif self.env.company.manufacturing_period == "week":
                            safety_inventory_qty = forecast_sale_qty / 7 * self.safety_available_days
                        else:
                            # day
                            safety_inventory_qty = forecast_sale_qty * self.safety_available_days
                        safety_inventory_qty_changed = False

                    if any(existing_forecasts.mapped('arriving_qty_apply_changed')):
                        arriving_qty_apply = sum(existing_forecasts.mapped('arriving_qty_apply'))
                        arriving_qty_apply = self._get_qty_with_mpq(self.product_id, arriving_qty_apply)
                        arriving_qty_apply_changed = True
                    else:
                        arriving_qty_apply = forecast_sale_qty + safety_inventory_qty - starting_inventory_qty
                        arriving_qty_apply = arriving_qty_apply if arriving_qty_apply > 0 else 0
                        arriving_qty_apply = self._get_qty_with_mpq(self.product_id, arriving_qty_apply)

                        # 如果本次预测增加的数量小于补货比例，则保持原有数量，不补货
                        arriving_qty_confirmed = sum(existing_forecasts.mapped('arriving_qty_confirmed'))
                        if arriving_qty_confirmed > 0 and arriving_qty_apply > arriving_qty_confirmed \
                             and (arriving_qty_apply - arriving_qty_confirmed) / arriving_qty_confirmed < self.replenish_increase_ignore_rate:
                            arriving_qty_apply = sum(existing_forecasts.mapped('arriving_qty_apply'))
                        arriving_qty_apply_changed = False

                    if any(existing_forecasts.mapped('arriving_qty_verify_changed')):
                        arriving_qty_verify = sum(existing_forecasts.mapped('arriving_qty_verify'))
                        arriving_qty_verify = self._get_qty_with_mpq(self.product_id, arriving_qty_verify)
                        arriving_qty_verify_changed = True
                    else:
                        arriving_qty_verify = arriving_qty_apply
                        arriving_qty_verify = self._get_qty_with_mpq(self.product_id, arriving_qty_verify)
                        arriving_qty_verify_changed = False

                    # 几个数据的差额，用于回写到forecast中去
                    forecast_sale_qty_to_add = forecast_sale_qty - \
                                               sum(existing_forecasts.mapped('forecast_sale_qty'))
                    arriving_qty_apply_to_add = arriving_qty_apply - \
                                                sum(existing_forecasts.mapped('arriving_qty_apply'))
                    arriving_qty_verify_to_add = arriving_qty_verify - \
                                                 sum(existing_forecasts.mapped('arriving_qty_verify'))

                    offset = 0
                    for forecast in existing_forecasts:
                        forecast_value = {}

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

                        forecast_value["arriving_qty_increase"] = forecast_value["arriving_qty_verify"] \
                                                                  - forecast.arriving_qty_confirmed
                        forecast_value["safety_inventory_qty"] = safety_inventory_qty
                        forecast_value["forecast_sale_qty_changed"] = forecast_sale_qty_changed
                        forecast_value["arriving_qty_apply_changed"] = arriving_qty_apply_changed
                        forecast_value["arriving_qty_verify_changed"] = arriving_qty_verify_changed
                        forecast_value["safety_inventory_qty_changed"] = safety_inventory_qty_changed
                        forecast_value["starting_inventory_qty"] = starting_inventory_qty
                        forecast_value["procurement_launched"] = False

                        # 写回forecast
                        forecast.write(forecast_value)
                        previous_forecast = forecast

                else:
                    # 需要新建一个forecast
                    forecast_value = {}

                    # forecast_sale_qty使用建议的advised_monthly_sale_qty
                    forecast_sale_qty = self.advised_monthly_sale_qty

                    # 重置safety_inventory_qty为根据设置的可销售天数计算出来的安全库存量
                    if self.env.company.manufacturing_period == "month":
                        safety_inventory_qty = forecast_sale_qty / 30 * self.safety_available_days
                    elif self.env.company.manufacturing_period == "week":
                        safety_inventory_qty = forecast_sale_qty / 7 * self.safety_available_days
                    else:
                        # day
                        safety_inventory_qty = forecast_sale_qty * self.safety_available_days

                    # arriving_qty_apply 根据计算设置默认值
                    arriving_qty_apply = forecast_sale_qty + safety_inventory_qty - starting_inventory_qty
                    arriving_qty_apply = arriving_qty_apply if arriving_qty_apply > 0 else 0

                    arriving_qty_apply = self._get_qty_with_mpq(self.product_id, arriving_qty_apply)

                    arriving_qty_verify = arriving_qty_apply
                    arriving_qty_confirmed = 0

                    arriving_qty_increase = arriving_qty_verify - arriving_qty_confirmed

                    # 初始默认为0, 只有在计划confirm的时候才需要设置
                    replenish_qty_required = 0
                    replenished_qty = 0

                    forecast_value['date'] = date_stop
                    forecast_value["starting_inventory_qty"] = starting_inventory_qty
                    forecast_value["forecast_sale_qty"] = forecast_sale_qty
                    forecast_value["forecast_sale_qty_changed"] = False
                    forecast_value["safety_inventory_qty"] = safety_inventory_qty
                    forecast_value["safety_inventory_qty_changed"] = False
                    forecast_value["arriving_qty_apply"] = arriving_qty_apply
                    forecast_value["arriving_qty_apply_changed"] = False
                    forecast_value["arriving_qty_verify"] = arriving_qty_verify
                    forecast_value["arriving_qty_verify_changed"] = False
                    forecast_value["arriving_qty_increase"] = arriving_qty_increase
                    forecast_value["arriving_qty_confirmed"] = arriving_qty_confirmed
                    forecast_value["replenished_qty"] = replenished_qty
                    forecast_value["replenish_qty_required"] = replenish_qty_required
                    forecast_value["procurement_launched"] = False
                    forecast_value["shipping_schedule_id"] = self.id
                    forecast = self.env["web.sale.shipping.forecast"].create(forecast_value)
                    previous_forecast = forecast

    @api.model
    def run_scheduler(self, use_new_cursor=False, only_new_products=False):
        """ Call the scheduler. This function is intended to be run for all the companies at the same time, so
        we run functions as SUPERUSER to avoid intercompanies and access rights issues. """
        try:
            if use_new_cursor:
                cr = registry(self._cr.dbname).cursor()
                self = self.with_env(self.env(cr=cr))  # TDE FIXME

            company_ids = self.env["res.company"].sudo().search([]).ids
            self = self.with_user(SUPERUSER_ID).with_context(allowed_company_ids=company_ids)

            self.sudo()._create_shipping_schedule(company_ids=company_ids, only_new_products=only_new_products)

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

    def _get_lead_time(self):
        """ Get the lead time for each product in self. The lead times are
        based on rules lead times + produce delay or supplier info delay.
        """
        self.ensure_one()
        shipping_schedule = self
        if shipping_schedule.shop_id and shipping_schedule.shop_id.partner_id \
                and shipping_schedule.shop_id.partner_id.default_shipping_method_id:
            estimate_ship_days = shipping_schedule.shop_id.partner_id.default_shipping_method_id.estimate_ship_days
        else:
            estimate_ship_days = 30

        # 保留天数，用于制定计划等造成的延误。
        reverse_days = 10

        lead_time = estimate_ship_days + shipping_schedule.product_id.manuf_procure_delay + reverse_days
        return lead_time

    def _get_arriving_qty_delayed(self, schedule_date_start):
        """
        得到计划开始之前，应到货，却没有到货的数量
        :param schedule_date_start: 计划开始日期
        :return:
        """
        self.ensure_one()

        shipping_schedule = self

        stock_move_obj = self.env["stock.move"]
        search_domain = [("company_id", "=", shipping_schedule.company_id.id),
                         ("partner_id", "=", shipping_schedule.shop_id.partner_id.id),
                         ("product_id", "=", shipping_schedule.product_id.id),
                         ('state', 'not in', ['cancel', 'draft']),
                         ('location_dest_id.usage', '=', 'customer'),
                         ('location_id.usage', '!=', 'inventory'),
                         ('picking_id.estimate_arriving_date', '>=', (schedule_date_start - relativedelta(months=3))),
                         ('picking_id.estimate_arriving_date', '<=', schedule_date_start),
                         "|",
                         ('shop_product_id', '=', shipping_schedule.shop_product_id.id),
                         ('shop_product_id', '=', None),
                         ]
        outgoing_moves = stock_move_obj.search(search_domain)
        outgoing_move_qty = sum(outgoing_moves.mapped("product_uom_qty")) - sum(outgoing_moves.mapped("quantity_received"))
        return outgoing_move_qty

    def _get_arriving_qty_arrived(self, date_start, date_stop):
        """
        得到期间内已到货的数量

        :param date_start:
        :param date_stop:
        :return:
        """
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
                         "|",
                         ('shop_product_id', '=', shipping_schedule.shop_product_id.id),
                         ('shop_product_id', '=', None),
                         ]
        outgoing_moves = stock_move_obj.search(search_domain)
        outgoing_move_qty = sum(outgoing_moves.mapped("quantity_received"))
        return outgoing_move_qty

    def _get_arriving_qty_shipped(self, date_start, date_stop):
        """
        得到期间内已经发货的数量
        :param date_start:
        :param date_stop:
        :return:
        """
        self.ensure_one()

        shipping_schedule = self

        existing_forecasts = shipping_schedule.forecast_ids.filtered(
            lambda p: p.date >= date_start and p.date <= date_stop)

        stock_move_obj = self.env["stock.move"]
        search_domain = [("company_id", "=", shipping_schedule.company_id.id),
                         ("partner_id", "=", shipping_schedule.shop_id.partner_id.id),
                         ('picking_id.move_document_type', '=', 'sale_out'),
                         ('state', 'not in', ['cancel', 'draft']),
                         ('shipping_forecast_id', 'in', existing_forecasts.ids),
                         "|",
                         ('shop_product_id', '=', shipping_schedule.shop_product_id.id),
                         ('shop_product_id', '=', None),
                         ]

        # search_domain = [("company_id", "=", shipping_schedule.company_id.id),
        #                  ("partner_id", "=", shipping_schedule.shop_id.partner_id.id),
        #                  ("product_id", "=", shipping_schedule.product_id.id),
        #                  ('state', 'not in', ['cancel', 'draft']),
        #                  ('location_dest_id.usage', '=', 'customer'),
        #                  ('location_id.usage', '!=', 'inventory'),
        #                  ('picking_id.estimate_arriving_date', '>=', date_start),
        #                  ('picking_id.estimate_arriving_date', '<=', date_stop),
        #                  "|",
        #                  ('shop_product_id', '=', shipping_schedule.shop_product_id.id),
        #                  ('shop_product_id', '=', None),
        #                  ]

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
        date_range = self._get_max_date_range()
        # 去年同比，前年同比
        date_range_year_minus_1 = self._get_max_date_range(years=1)
        date_range_year_minus_2 = self._get_max_date_range(years=2)

        read_fields = [
            'shop_product_id',
            'product_id',
            'shop_id',
            'seller_sku',
            'product_default_code',
            'product_name',
            'schedule_year',
            'schedule_month',
            'sale_qty_7',
            'sale_qty_14',
            'sale_qty_30',
            'sale_qty_30_y_1',
            'advised_monthly_sale_qty',
            'qty_available',
            'qty_shipped',
            'warehouse_id',
            'available_days',
            'safety_available_days',
            'is_out_of_stock_occurred',
            'is_too_much_inventory',
            'is_too_little_inventory',
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

            # 可以用于新增发货的可用库存
            date_start = date_range[0][0]
            date_stop = date_range[-1][1]
            factory_available_qty = shipping_schedule._get_factory_available_qty(date_start).get(
                shipping_schedule.product_id.id)
            shipping_schedule_state["factory_available_qty"] = factory_available_qty
            shipping_schedule_state["arriving_qty_delayed"] = shipping_schedule._get_arriving_qty_delayed(date_start)
            shipping_schedule_state["existing_qty_unallocated"] = shipping_schedule._get_existing_qty_unallocated(date_start, date_stop)

            # 由于已发货产品的到货日期不一定会落在相应的forecast期间，并且有可能会不按计划多发，
            # 因此在计算实际新增发货的数量时，是将全部已发货减去全部确认到货得到的差值，如果比新增发货多，则不会产生实际的新增发货。
            # 而不是在每一期上计算。
            shipping_schedule._check_arriving_qty_shipped(date_range)

            rounding = shipping_schedule.product_id.uom_id.rounding

            # forecast开始时间大于procurement_date，不需要补货。
            lead_time = shipping_schedule._get_lead_time()
            procurement_date = add(date_start, days=lead_time)

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

                if index == 0:
                    forecast_values['is_first_period'] = True
                else:
                    forecast_values['is_first_period'] = False

                forecast_values['date_start'] = date_start
                forecast_values['date_stop'] = date_stop


                forecast_values['starting_inventory_qty'] = existing_forecasts[0].starting_inventory_qty
                forecast_values['ending_inventory_qty'] = existing_forecasts[-1].ending_inventory_qty
                forecast_values['forecast_sale_qty'] = sum(existing_forecasts.mapped('forecast_sale_qty'))
                forecast_values['forecast_sale_qty_changed'] = any(
                    existing_forecasts.mapped('forecast_sale_qty_changed'))
                forecast_values['safety_inventory_qty'] = max(existing_forecasts.mapped('safety_inventory_qty'))
                forecast_values['safety_inventory_qty_changed'] = any(
                    existing_forecasts.mapped('safety_inventory_qty_changed'))
                forecast_values['arriving_qty_apply'] = sum(existing_forecasts.mapped('arriving_qty_apply'))
                forecast_values['arriving_qty_apply_changed'] = any(
                    existing_forecasts.mapped('arriving_qty_apply_changed'))
                forecast_values['arriving_qty_verify'] = sum(existing_forecasts.mapped('arriving_qty_verify'))
                forecast_values['arriving_qty_verify_changed'] = any(
                    existing_forecasts.mapped('arriving_qty_verify_changed'))
                forecast_values['arriving_qty_confirmed'] = sum(existing_forecasts.mapped('arriving_qty_confirmed'))
                forecast_values['arriving_qty_increase'] = sum(existing_forecasts.mapped('arriving_qty_increase'))
                forecast_values['arriving_qty_shipped'] = shipping_schedule._get_arriving_qty_shipped(date_start, date_stop)
                forecast_values['replenished_qty'] = sum(existing_forecasts.mapped('replenished_qty'))
                forecast_values['replenish_qty_required'] = sum(existing_forecasts.mapped('replenish_qty_required'))
                forecast_values['procurement_launched'] = all(
                    existing_forecasts.mapped('procurement_launched'))

                if forecast_values['procurement_launched']:
                    forecast_values['to_replenish'] = False
                else:
                    if forecast_values['is_first_period']:
                        # 第一期不补货
                        forecast_values['to_replenish'] = False
                    elif forecast_values['arriving_qty_confirmed'] > 0 \
                        and forecast_values['arriving_qty_increase'] / forecast_values['arriving_qty_confirmed'] < shipping_schedule.replenish_increase_ignore_rate:
                        # 增加的数量小于补货比例，不补货
                        forecast_values['to_replenish'] = False
                    elif date_start <= procurement_date:
                        forecast_values['to_replenish'] = True
                    else:
                        # 超出补货提前期，不补货
                        forecast_values['to_replenish'] = False

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
        date_start, date_stop = self._get_max_date_range()[date_index]
        forecast_ids = self.forecast_ids.filtered(lambda f:
                                                  f.date >= date_start and f.date <= date_stop)

        forecast_ids.write({
            'safety_inventory_qty_changed': False,
        })

        self._compute_forecast_values()
        return True

    def reset_forecast_sale_qty(self, date_index):
        date_start, date_stop = self._get_max_date_range()[date_index]
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
        date_start, date_stop = self._get_max_date_range()[date_index]
        forecast_ids = self.forecast_ids.filtered(lambda f:
                                                  f.date >= date_start and f.date <= date_stop)

        forecast_ids.write({
            'arriving_qty_apply_changed': False,
        })

        self._compute_forecast_values()
        return True

    def reset_arriving_qty_verify(self, date_index):
        date_start, date_stop = self._get_max_date_range()[date_index]
        forecast_ids = self.forecast_ids.filtered(lambda f:
                                                  f.date >= date_start and f.date <= date_stop)

        # 如果设置的数量小于已发货数量，则报错。
        forecast_sale_qty = sum(forecast_ids.mapped("forecast_sale_qty"))
        starting_inventory_qty = forecast_ids[0].starting_inventory_qty
        safety_inventory_qty = forecast_ids[0].safety_inventory_qty
        arriving_qty_verify = forecast_sale_qty + safety_inventory_qty - starting_inventory_qty

        # arriving_qty_shipped = self._get_arriving_qty_shipped(date_start, date_stop)
        # # 如果设置的数量小于已发货数量，则报错。
        # if arriving_qty_verify < arriving_qty_shipped:
        #     raise UserError("Can not reset to default quantity as it can't be smaller than shipped quantity.")

        forecast_ids.write({
            'arriving_qty_verify': arriving_qty_verify,
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

        date_start = forecast_values['date_start']
        date_stop = forecast_values['date_stop']

        # 使用日期期间的中间一天为到货日期
        date_delta = int(((date_stop - date_start).days + 1) / 2)

        # 计算补货（采购单或制造单）完成的日期。
        date_planned = subtract(date_start, days=(estimate_ship_days - date_delta))

        group_name = "%s/%s/%s" % (date_planned, self.shop_id.name, self.seller_sku,)
        # 取得对应计划时间的Group Id
        procurement_group = self.env['procurement.group'].search([("name", "=", group_name), ])

        # 如果没有，则新增一个
        if not procurement_group:
            values = [{"name": group_name, "move_type": "direct"}]
            procurement_group = self.env['procurement.group'].create(values)
        else:
            procurement_group = procurement_group[0]

        return {
            'date_planned': date_planned,
            'warehouse_id': self.warehouse_id,
            'group_id': procurement_group.id,
        }

    def _compute_replenish_qty(self):
        """
        计算需要补货的数量
        :return:
        """
        company_id = self.env.company
        date_range = self._get_max_date_range()

        date_start = date_range[0][0]
        date_stop = date_range[-1][1]

        for shipping_schedule in self:

            if shipping_schedule.state != "logistics_confirmed":
                raise UserError(
                    _("Only logistics confirmed schedule can be computed replenish quantity."))

            # forecast开始时间大于procurement_date，不需要补货。
            lead_time = shipping_schedule._get_lead_time()
            procurement_date = add(date_start, days=lead_time)

            factory_available_qty = shipping_schedule._get_factory_available_qty(date_start)[
                shipping_schedule.product_id.id]

            for index, (date_start, date_stop) in enumerate(date_range):

                if index == 0:
                    # 第一期不计算补货数量
                    continue

                if procurement_date > date_start:
                    forecasts = shipping_schedule.forecast_ids.filtered(lambda p: date_start <= p.date <= date_stop)

                    for forecast in forecasts:
                        if forecast.arriving_qty_increase == 0:
                            forecast.replenish_qty_required = 0
                            forecast.procurement_launched = True
                        elif forecast.arriving_qty_increase < 0:
                            forecast.replenish_qty_required = 0
                            forecast.procurement_launched = False
                        else:
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

            # positive_forecasts = forecasts.filtered(lambda p: p.arriving_qty_increase > 0)
            # positive_arriving_qty_increase = sum(positive_forecasts.mapped("arriving_qty_increase"))
            #
            # factory_available_qty = shipping_schedule._get_factory_available_qty(date_start)[
            #     shipping_schedule.product_id.id]
            #
            # # 由于此时读取的可用库存已经使用了最新的confirm qty.
            # # 包括需要增加或扣减的到货数量。
            # # 因此在计算补货的时候，对于减少的到货数量不需要补货，对于增加的到货数量，需要先全部补回去，然后再重算。
            # factory_available_qty += positive_arriving_qty_increase
            #
            # for forecast in forecasts:
            #     if forecast.arriving_qty_increase == 0:
            #         forecast.replenish_qty_required = 0
            #         forecast.procurement_launched = True
            #     elif forecast.arriving_qty_increase < 0:
            #         forecast.replenish_qty_required = 0
            #         # 虽然不用发生实际补货，但是需要在补货操作中把arriving_qty_increase等数据置0
            #         forecast.procurement_launched = False
            #     else:
            #         # factory_available_qty = self._get_factory_available_qty(date_start, date_stop)[
            #         #     self.product_id.id]
            #         if float_compare(forecast.arriving_qty_increase, factory_available_qty,
            #                          precision_rounding=shipping_schedule.product_uom_id.rounding) > 0:
            #             forecast.replenish_qty_required = forecast.arriving_qty_increase - factory_available_qty
            #             factory_available_qty = 0
            #             forecast.procurement_launched = False
            #         else:
            #             forecast.replenish_qty_required = 0
            #             factory_available_qty -= forecast.arriving_qty_increase
            #             # 虽然不用发生实际补货，但是需要在补货操作中把arriving_qty_increase等数据置0
            #             forecast.procurement_launched = False

    def action_sales_confirm(self):
        company_id = self.env.company
        date_range = self._get_max_date_range()

        date_start = date_range[0][0]
        date_stop = date_range[-1][1]

        for shipping_schedule in self:
            if shipping_schedule.state == "draft":
                shipping_schedule.state = "sales_confirmed"

    def action_logistics_confirm(self):
        company_id = self.env.company
        date_range = self._get_max_date_range()

        date_start = date_range[0][0]
        date_stop = date_range[-1][1]

        shipping_schedule_states = self.get_shipping_schedule_view_state()
        shipping_schedule_states = {schedule['id']: schedule for schedule in shipping_schedule_states}
        procurements = []
        forecasts_values = []
        forecasts_to_set_as_launched = self.env['web.sale.shipping.forecast']

        shipping_schedule_to_replenish = self.filtered(lambda r: r.state == 'sales_confirmed')

        for shipping_schedule in self:
            if shipping_schedule._get_existing_qty_unallocated(date_start, date_stop) > 0:
                # 如果有未归类的发货，则不能做确认操作
                err_msg = _("Can not confirm the schedule %s %s, as there are shipments not mapped to forecasts.") \
                          % (shipping_schedule.shop_id.name, shipping_schedule.shop_product_id.seller_sku)
                raise UserError(err_msg)

            if shipping_schedule.state == "sales_confirmed":
                shipping_schedule.state = "logistics_confirmed"
                shipping_schedule._compute_replenish_qty()

        # for shipping_schedule in shipping_schedule_to_replenish:
        #     if shipping_schedule._get_existing_qty_unallocated(date_start, date_stop) > 0:
        #         # 如果有未归类的发货，则不能做确认操作
        #         err_msg = _("Can not confirm the schedule %s %s, as there are shipments not mapped to forecasts.") \
        #                   % (shipping_schedule.shop_id.name, shipping_schedule.shop_product_id.seller_sku)
        #         raise UserError(err_msg)
        #
        #     shipping_schedule_state = shipping_schedule_states[shipping_schedule.id]
        #
        #     forecast_list = shipping_schedule_state['forecast_ids']
        #
        #     previous_forecast = None
        #
        #     for forecast_dict in forecast_list:
        #         existing_forecasts = shipping_schedule.forecast_ids.filtered(lambda p:
        #                                                              forecast_dict['date_start'] <= p.date <=
        #                                                              forecast_dict['date_stop'])
        #         for forecast in existing_forecasts:
        #             if previous_forecast:
        #                 forecast.starting_inventory_qty = previous_forecast.ending_inventory_qty
        #             if forecast_dict["to_replenish"]:
        #                 forecast.arriving_qty_confirmed = forecast.arriving_qty_verify
        #
        #             previous_forecast = forecast
        #
        #     # 在确认以后，计算补货数量。
        #     # 注意，这只是模拟计算，供参考使用。在真正补货时，由于其他店铺相同产品的计划确认后，会导致可用数量的变化，因此需要重算。
        #     shipping_schedule._compute_replenish_qty()

    def action_cancel_confirm(self):
        company_id = self.env.company
        date_range = self._get_max_date_range()

        date_start = date_range[0][0]
        date_stop = date_range[-1][1]

        for shipping_schedule in self:
            if shipping_schedule.state in ["sales_confirmed"]:
                shipping_schedule.state = "draft"
            elif shipping_schedule.state in ["logistics_confirmed"]:
                shipping_schedule.state = "draft"
                forecasts = shipping_schedule.forecast_ids.filtered(lambda p:
                                                                    date_start <= p.date <= date_stop
                                                                    )
                forecasts.write({
                    'replenish_qty_required': 0,
                    'procurement_launched': False,
                })
            elif shipping_schedule.state in ["done"]:
                shipping_schedule.state = "draft"
                forecasts = shipping_schedule.forecast_ids.filtered(lambda p:
                                                                    date_start <= p.date <= date_stop
                                                                    )
                forecasts.write({
                    'replenish_qty_required': 0,
                    'procurement_launched': False,
                })

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

        # 重新计算一次补货数量，以免在确认操作前，数据发生了变化。
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

            forecasts_to_replenish = filter(lambda f: f['to_replenish'],
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

                            '%s/%s/%s' % (forecast["date_start"],
                                          shipping_schedule.shop_id.name,
                                          shipping_schedule.seller_sku,
                                          ),
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
                                '%s/%s/%s' % (forecast["date_start"],
                                              shipping_schedule.shop_id,
                                              shipping_schedule.seller_sku,
                                              ),
                                shipping_schedule.company_id, extra_values
                            ))

                forecasts_to_set_as_launched |= existing_forecasts

        if procurements:
            self.env['procurement.group'].with_context(skip_lead_time=True).run(procurements)

        for forecast in forecasts_to_set_as_launched:
            arriving_qty_confirmed = forecast.arriving_qty_verify
            replenished_qty = forecast.replenished_qty + forecast.replenish_qty_required
            forecast.write({
                'arriving_qty_increase': 0,
                'arriving_qty_confirmed': arriving_qty_confirmed,
                'replenish_qty_required': 0,
                'replenished_qty': replenished_qty,
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

    def action_open_existing_arriving_qty_details(self, date_str, date_start, date_stop):
        """ Open the related stock moves.

        :param date_str: period name for the forecast sellected
        :param date_start: select incoming moves and RFQ after this date
        :param date_stop: select incoming moves and RFQ before this date
        :return: action values that open the forecast details wizard
        :rtype: dict
        """
        date_start_str = date_start
        date_stop_str = date_stop
        date_start = fields.Date.from_string(date_start_str)
        date_stop = fields.Date.from_string(date_stop_str)

        stock_move_obj = self.env["stock.move"]
        search_domain = [("company_id", "=", self.company_id.id),
                         ("partner_id", "=", self.shop_id.partner_id.id),
                         ('move_document_type', '=', 'sale_out'),
                         ("shop_product_id", "=", self.shop_product_id.id),
                         ('state', 'not in', ['cancel', 'draft']),
                         ]

        if date_str == "delayed":
            search_domain = search_domain.extend([
                    ('picking_id.estimate_arriving_date', '>=', (schedule_date_start - relativedelta(months=3))),
                    ('picking_id.estimate_arriving_date', '<=', schedule_date_start),
                    ('product_uom_qty', '>', 'quantity_received'),
                ])
            name = _('Shipment not mapped to forecast: %s %s') % (self.shop_id.name, self.shop_product_id.seller_sku)
        elif date_str == "unallocated":
            search_domain = search_domain + [('shipping_forecast_id', '=', False), ('picking_id.estimate_arriving_date', '>=', date_start)]
            name = _('Shipment not mapped to forecast: %s %s') % (self.shop_id.name, self.shop_product_id.seller_sku)
        else:
            existing_forecasts = self.forecast_ids.filtered(lambda p: date_start <= p.date <= date_stop)
            search_domain = search_domain + [('shipping_forecast_id', 'in', existing_forecasts.ids),]
            name = _('Shipment in forecast %s: %s %s') % (date_str, self.shop_id.name, self.shop_product_id.seller_sku)

        move_ids = stock_move_obj.search(search_domain).ids

        context = {
            # 'search_default_id': move_ids,
            'action_name': name,
        }
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.move',
            'name': name,
            'search_view_id': [self.env.ref('web_sale.view_move_search_for_forecast').id, name],
            'view_mode': 'list',
            'views': [[self.env.ref('web_sale.view_move_tree_for_forecast').id, 'list']],
            'domain': [("id", "in", move_ids)],
            'target': 'new',
            'context': context
        }

    def _get_max_date_range(self, years=False):
        """
        由于多公司情况下，各个公司有可能计划期不一样。因此取最大的计划期间。
        :param years:
        :return:
        """
        company_id = self.env["res.company"].search([], order="manufacturing_period_to_display desc", limit=1)

        return company_id._get_date_range(years)