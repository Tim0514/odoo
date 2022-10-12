
from collections import defaultdict, namedtuple
from math import log10

from odoo import api, fields, models, _, SUPERUSER_ID, registry
from odoo.exceptions import ValidationError
from odoo.tools.date_utils import start_of, end_of, add, subtract
from odoo.tools.float_utils import float_round
from odoo.osv.expression import OR, AND
from collections import OrderedDict
import time
import math

_STATES = [
    ("draft", "Draft"),
    ("sales_confirmed", "Sales Confirmed"),
    ("logistics_confirmed", "Logistics Confirmed"),
]

class MrpProductionSchedule(models.Model):
    _inherit = 'mrp.production.schedule'

    schedule_master_id = fields.Many2one(
        comodel_name='mrp.production.schedule.master', string='Schedule Master', index=True, ondelete="cascade"
    )

    salesperson_id = fields.Many2one(
        comodel_name='res.users', string='Salesperson', index=True, default=lambda self: self.env.user,
    )

    sale_qty_7 = fields.Float(string='7 days sale')

    sale_qty_14 = fields.Float(string='14 days sale')

    sale_qty_28 = fields.Float(string='28 days sale')

    avg_week_sale_1 = fields.Float(string='Average Week Sale 1')

    avg_week_sale_2 = fields.Float(string='Average Week Sale 2')

    week_sale_same_period_last_year = fields.Float(string='Week Sale Last Year')

    avg_week_sale_adv = fields.Float(string='Advised Average Week Sale')

    def _get_procurement_extra_values(self, forecast_values):
        """
            Timwang modified at 2021/8/24
            根据补货日期分组
        """
        """ Extra values that could be added in the vals for procurement.

        return values pass to the procurement run method.
        rtype dict
        """

        # 取得计划时间
        plan_date = fields.Date.to_string(forecast_values['date_start'])

        group_name = "MPS/" + plan_date
        # 取得对应计划时间的Group Id
        procurement_group = self.env['procurement.group'].search([("name", "=", group_name),])

        # 如果没有，则新增一个
        if not procurement_group:
            values = [{"name": group_name, "move_type": "direct"}]
            procurement_group = self.env['procurement.group'].create(values)
        else:
            procurement_group = procurement_group[0]

        return {
            'date_planned': forecast_values['date_start'],
            'warehouse_id': self.warehouse_id,
            'group_id': procurement_group,
        }


class MrpProductionScheduleMaster(models.Model):
    _name = 'mrp.production.schedule.master'
    _order = 'warehouse_id'
    _description = 'Master Data of Mrp Production Schedule'

    name = fields.Char('Description', store=True, compute='_compute_name')

    warehouse_id = fields.Many2one(
        comodel_name="stock.warehouse",
        string="Warehouse",
        store=True,
        readonly=False,
    )

    salesperson_id = fields.Many2one(
        comodel_name='res.users', string='Salesperson', index=True, default=lambda self: self.env.user,
    )

    state = fields.Selection(
        selection=_STATES,
        string="Status",
        index=True,
        required=True,
        copy=True,
        default="draft",
    )

    start_date = fields.Date(
        string="Start Date",
    )

    end_date = fields.Date(
        string="End Date",
    )

    schedule_year = fields.Integer(
        string="Schedule Year",
    )

    schedule_week = fields.Integer(
        string="Schedule Week",
    )

    mrp_production_schedule_ids = fields.One2many('mrp.production.schedule', 'schedule_master_id', 'Production Schedule Lines')

    @api.depends('warehouse_id', 'salesperson_id')
    def _compute_name(self):
        for master in self:
            master.name = "%s - %s" % (master.warehouse_id.name, master.salesperson_id.name)

    @api.model
    def run_scheduler(self, use_new_cursor=False, company_id=False):
        """ Call the scheduler. This function is intended to be run for all the companies at the same time, so
        we run functions as SUPERUSER to avoid intercompanies and access rights issues. """
        try:
            if use_new_cursor:
                cr = registry(self._cr.dbname).cursor()
                self = self.with_env(self.env(cr=cr))  # TDE FIXME

            self._update_schedule_products(use_new_cursor=use_new_cursor, company_id=company_id)

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

    @api.model
    def _update_schedule_products(self, use_new_cursor=False, company_id=False):

        #同步计划表中的产品数据
        shop_products = self.env["web.sale.shop.product"].search(
            [("state", "in", ["new", "normal"])],
        )
        # 遍历店铺产品列表，同步
        for shop_product in shop_products:
            if shop_product.mrp_production_schedule_id:
                # 如果产品有计划，则判断salesperson是否发生变化，如果有，则更新计划中产品的salesperson
                if shop_product.salesperson_id != shop_product.mrp_production_schedule_id.salesperson_id:
                    shop_product.mrp_production_schedule_id.salesperson_id = shop_product.salesperson_id
            else:
                if shop_product.shop_id.default_warehouse_id:
                    # 如果店铺有设置对应的默认仓库。理论上，此处必须要设置，否则没法生成相应的计划。

                    # 如果没有找到对应的产品计划，则到计划表中直接查找相同仓库和产品的计划，如果有，则写回店铺产品表。
                    production_schedule = self.env["mrp.production.schedule"].search(
                        [("warehouse_id", "=", shop_product.shop_id.default_warehouse_id.id),
                         ("product_id", "=", shop_product.product_id.id)],)

                    if not production_schedule:
                        # 如果仍然没有找到，则新建一条schedule
                        values = [
                            {"product_id": shop_product.product_id.id,
                             "warehouse_id": shop_product.shop_id.default_warehouse_id.id,
                             }
                        ]
                        production_schedule = self.env["mrp.production.schedule"].create(values)

                    # 设置shop_product对应的production_schedule
                    shop_product.mrp_production_schedule_id = production_schedule

        # 删除停售和清仓的产品计划
        shop_products = self.env["web.sale.shop.product"].search(
            [("state", "in", ["clearance", "stop"])],
        )
        for shop_product in shop_products:
            if shop_product.mrp_production_schedule_id:
                mrp_production_schedule = shop_product.mrp_production_schedule_id
                shop_product.mrp_production_schedule_id = False
                mrp_production_schedule.unlink()

        # 设置mrp_production_schedule对应的production_schedule_master

        warehouse_ids = self.env["res.partner"].search([("is_web_shop", "=", True)]).mapped("default_warehouse_id.id")

        # 读取店铺商品的 店铺和销售员信息
        warehouse_and_salespersons = self.env["mrp.production.schedule"].read_group(
            domain=[("warehouse_id", "in", warehouse_ids)],
            fields=["warehouse_id", "salesperson_id"],
            groupby=["warehouse_id", "salesperson_id"],
            lazy=False
        )

        for warehouse_and_salesperson in warehouse_and_salespersons:
            warehouse_id = warehouse_and_salesperson["warehouse_id"]
            salesperson_id = warehouse_and_salesperson["salesperson_id"]

            warehouse_id = warehouse_id[0]
            salesperson_id = salesperson_id[0]

            # 查找该店铺和销售员的schedule_master
            schedule_master = self.env["mrp.production.schedule.master"].search(
                [("warehouse_id", "=", warehouse_id), ("salesperson_id", "=", salesperson_id)]
            )
            if not schedule_master:
                # 创建schedule_master
                values = [
                    {"warehouse_id": warehouse_id, "salesperson_id": salesperson_id},
                ]
                schedule_master = self.env["mrp.production.schedule.master"].create(values)

            schedule_master = schedule_master[0]

            production_schedule = self.env["mrp.production.schedule"].search(
                [("warehouse_id", "=", warehouse_id), ("salesperson_id", "=", salesperson_id)]
            )
            if production_schedule:
                production_schedule.schedule_master_id = schedule_master

        return True

    def _get_sale_qty_7_14_28(self):

        customers_location_id = self.env.ref('stock.stock_location_customers')
        scrap_location_id = self.env['stock.scrap']._get_default_scrap_location_id()

        first_day = start_of(fields.Date.today(), self.env.company.manufacturing_period)
        end_day = subtract(first_day, days=1)
        day_7 = subtract(first_day, days=7)
        day_14 = subtract(first_day, days=14)
        day_28 = subtract(first_day, days=28)

        first_day_same_period = subtract(first_day, year=1)
        first_day_same_period = start_of(first_day_same_period, self.env.company.manufacturing_period)
        end_day_same_period = subtract(first_day_same_period, days=1)
        day_7_same_period = subtract(first_day_same_period, days=7)

        product_sale_qtys_7 = defaultdict(int)
        product_sale_qtys_14 = defaultdict(int)
        product_sale_qtys_28 = defaultdict(int)
        product_sale_qtys_7_same_period = defaultdict(int)

        for schedule_master in self:
            products = schedule_master.mrp_production_schedule_ids.mapped('product_id')
            product_ids = products.mapped("id")

            sale_qtys = self.env["web.sale.shop.sale.data"].read_group(
                domain=[("warehouse_id", "=", schedule_master.warehouse_id.id),
                        ("product_id", "in", product_ids),
                        ("order_date", ">=", day_7),
                        ("order_date", "<=", end_day),
                        ("state", "=", "ok"),
                        ],
                fields=["product_id", "sale_qty:sum", "return_qty:sum"],
                groupby=["product_id"],
                orderby="product_id"
            )
            for sale_qty in sale_qtys:
                product_sale_qtys_7.setdefault(sale_qty["product_id"][0], sale_qty["sale_qty"]-sale_qty["return_qty"])

            sale_qtys = self.env["web.sale.shop.sale.data"].read_group(
                domain=[("warehouse_id", "=", schedule_master.warehouse_id.id),
                        ("product_id", "in", product_ids),
                        ("order_date", ">=", day_14),
                        ("order_date", "<=", end_day),
                        ("state", "=", "ok"),
                        ],
                fields=["product_id", "sale_qty:sum", "return_qty:sum"],
                groupby=["product_id"],
                orderby="product_id"
            )
            for sale_qty in sale_qtys:
                product_sale_qtys_14.setdefault(sale_qty["product_id"][0], sale_qty["sale_qty"]-sale_qty["return_qty"])

            sale_qtys = self.env["web.sale.shop.sale.data"].read_group(
                domain=[("warehouse_id", "=", schedule_master.warehouse_id.id),
                        ("product_id", "in", product_ids),
                        ("order_date", ">=", day_28),
                        ("order_date", "<=", end_day),
                        ("state", "=", "ok"),
                        ],
                fields=["product_id", "sale_qty:sum", "return_qty:sum"],
                groupby=["product_id"],
                orderby="product_id"
            )
            for sale_qty in sale_qtys:
                product_sale_qtys_28.setdefault(sale_qty["product_id"][0], sale_qty["sale_qty"]-sale_qty["return_qty"])

            sale_qtys = self.env["web.sale.shop.sale.data"].read_group(
                domain=[("warehouse_id", "=", schedule_master.warehouse_id.id),
                        ("product_id", "in", product_ids),
                        ("order_date", ">=", day_7_same_period),
                        ("order_date", "<=", end_day_same_period),
                        ("state", "=", "ok"),
                        ],
                fields=["product_id", "sale_qty:sum", "return_qty:sum"],
                groupby=["product_id"],
                orderby="product_id"
            )
            for sale_qty in sale_qtys:
                product_sale_qtys_7_same_period.setdefault(sale_qty["product_id"][0], sale_qty["sale_qty"]-sale_qty["return_qty"])

        return product_sale_qtys_7, product_sale_qtys_14, product_sale_qtys_28, product_sale_qtys_7_same_period

    def _get_sale_qty_7_14_28_bak(self):

        customers_location_id = self.env.ref('stock.stock_location_customers')
        scrap_location_id = self.env['stock.scrap']._get_default_scrap_location_id()

        first_day = start_of(fields.Date.today(), self.env.company.manufacturing_period)
        end_day = subtract(first_day, days=1)
        day_7 = subtract(first_day, days=7)
        day_14 = subtract(first_day, days=14)
        day_28 = subtract(first_day, days=28)

        first_day_same_period = subtract(first_day, year=1)
        first_day_same_period = start_of(first_day_same_period, self.env.company.manufacturing_period)
        end_day_same_period = subtract(first_day_same_period, days=1)
        day_7_same_period = subtract(first_day_same_period, days=7)

        product_sale_qtys_7 = defaultdict(int)
        product_sale_qtys_14 = defaultdict(int)
        product_sale_qtys_28 = defaultdict(int)
        product_sale_qtys_7_same_period = defaultdict(int)

        for schedule_master in self:
            products = schedule_master.mrp_production_schedule_ids.mapped('product_id')
            product_ids = products.mapped("id")
            sale_qtys = self.env["stock.move"].read_group(
                domain=[("location_id", "=", schedule_master.warehouse_id.lot_stock_id.id),
                        ("location_dest_id", "=", customers_location_id.id),
                        ("product_id", "in", product_ids),
                        ("date", ">=", day_7),
                        ("date", "<=", end_day),
                        ("state", "=", "done"),
                        ],
                fields=["product_id", "product_qty:sum"],
                groupby=["product_id"],
                orderby="product_id"
            )
            for sale_qty in sale_qtys:
                product_sale_qtys_7.setdefault(sale_qty["product_id"][0], sale_qty["product_qty"])

            sale_qtys = self.env["stock.move"].read_group(
                domain=[("location_id", "=", schedule_master.warehouse_id.lot_stock_id.id),
                        ("location_dest_id", "=", customers_location_id.id),
                        ("product_id", "in", product_ids),
                        ("date", ">=", day_14),
                        ("date", "<=", end_day),
                        ("state", "=", "done"),
                        ],
                fields=["product_id", "product_qty:sum"],
                groupby=["product_id"],
                orderby="product_id"
            )
            for sale_qty in sale_qtys:
                product_sale_qtys_14.setdefault(sale_qty["product_id"][0], sale_qty["product_qty"])

            sale_qtys = self.env["stock.move"].read_group(
                domain=[("location_id", "=", schedule_master.warehouse_id.lot_stock_id.id),
                        ("location_dest_id", "=", customers_location_id.id),
                        ("product_id", "in", product_ids),
                        ("date", ">=", day_28),
                        ("date", "<=", end_day),
                        ("state", "=", "done"),
                        ],
                fields=["product_id", "product_qty:sum"],
                groupby=["product_id"],
                orderby="product_id"
            )
            for sale_qty in sale_qtys:
                product_sale_qtys_28.setdefault(sale_qty["product_id"][0], sale_qty["product_qty"])

            sale_qtys = self.env["stock.move"].read_group(
                domain=[("location_id", "=", schedule_master.warehouse_id.lot_stock_id.id),
                        ("product_id", "in", product_ids),
                        ("date", ">=", day_7_same_period),
                        ("date", "<=", end_day_same_period),
                        ],
                fields=["product_id", "product_qty:sum"],
                groupby=["product_id"],
                orderby="product_id"
            )
            for sale_qty in sale_qtys:
                product_sale_qtys_7_same_period.setdefault(sale_qty["product_id"][0], sale_qty["product_qty"])

        return product_sale_qtys_7, product_sale_qtys_14, product_sale_qtys_28, product_sale_qtys_7_same_period

    def generate_schedule_sale_data(self):

        first_day = start_of(fields.Date.today(), self.env.company.manufacturing_period)
        new_year = int(first_day.strftime('%Y'))
        new_week = int(first_day.strftime('%W'))

        for schedule_master in self:
            if schedule_master.state != "draft" and schedule_master.schedule_week == new_week:
                raise ValidationError(_("计划已被审核，请先取消审核后再重新生成！"))
            else:
                # 重置计划为草稿，并设置新的计划年和周
                schedule_master.state = "draft"
                schedule_master.schedule_year = new_year
                schedule_master.schedule_week = new_week

            # 统计7，14，28天的销量
            product_sale_qtys_7, product_sale_qtys_14, product_sale_qtys_28, product_sale_qtys_7_same_period = self._get_sale_qty_7_14_28()

            for production_schedule in schedule_master.mrp_production_schedule_ids:
                production_schedule.sale_qty_7 = product_sale_qtys_7[production_schedule.product_id.id]
                production_schedule.sale_qty_14 = product_sale_qtys_14[production_schedule.product_id.id]
                production_schedule.sale_qty_28 = product_sale_qtys_28[production_schedule.product_id.id]
                production_schedule.week_sale_same_period_last_year = product_sale_qtys_7_same_period[production_schedule.product_id.id]

                self._compute_avg_week_sale(production_schedule)
        return

    def _compute_avg_week_sale(self, production_schedule):
        sale_qty_7 = production_schedule.sale_qty_7
        sale_qty_14 = production_schedule.sale_qty_14
        sale_qty_28 = production_schedule.sale_qty_28
        production_schedule.avg_week_sale_1 = round((sale_qty_7 / 7 * 0.5 + sale_qty_14 / 14 * 0.3 + sale_qty_28 / 28 * 0.2) * 7, 0)
        if production_schedule.avg_week_sale_1 < 0:
            production_schedule.avg_week_sale_1 = 0

        k1 = (sale_qty_7 / 7 - sale_qty_14 / 14) / 7
        k2 = (sale_qty_14 / 14 - sale_qty_28 / 28) / 14
        k3 = (k1 + k2) / 2
        production_schedule.avg_week_sale_2 = round((sale_qty_7 / 7 + k3 * 14)*7, 0)
        if production_schedule.avg_week_sale_2 < 0:
            production_schedule.avg_week_sale_2 = 0

        production_schedule.avg_week_sale_adv = max(production_schedule.avg_week_sale_1,
                                                    production_schedule.avg_week_sale_2)

    def _update_mrp_forcast(self):
        for schedule_master in self:
            for schedule in schedule_master.mrp_production_schedule_ids:
                lead_times = schedule._get_lead_times()
                weeks_to_forecast = math.ceil(lead_times/7)
                i = 0
                while i <= weeks_to_forecast:
                    schedule.set_forecast_qty(i, schedule.avg_week_sale_adv)
                    i += 1

    def button_draft(self):
        self.generate_schedule_sale_data()
        self.state = "draft"

    def button_sales_confirm(self):
        self.state = "sales_confirmed"

    def button_logistics_confirm(self):
        self.state = "logistics_confirmed"
        self._update_mrp_forcast()






