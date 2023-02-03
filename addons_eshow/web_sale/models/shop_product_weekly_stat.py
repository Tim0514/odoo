# Copyright 2018-2019 ForgeFlow, S.L.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.date_utils import start_of, end_of, add, subtract


class ShopProductWeeklyStat(models.Model):
    _name = "web.sale.shop.product.weekly.stat"
    _description = "Shop Product Weekly Statics"
    _order = "shop_name, product_asin"

    @api.model
    def _company_get(self):
        return self.env["res.company"].browse(self.env.company.id)

    company_id = fields.Many2one(
        comodel_name="res.company", string="Company", required=True, default=_company_get, index=True,
    )

    shop_id = fields.Many2one(comodel_name="web.sale.shop", string="Shop", store=True, index=True,)

    shop_name = fields.Char(related="shop_id.name", string="Web Shop Name", store=True, index=True,)

    product_asin_id = fields.Many2one("web.sale.shop.product.asin", string="ASIN", store=True, index=True,)

    product_asin = fields.Char(related="product_asin_id.product_asin", string="ASIN", store=True, index=True,)

    shop_product_ids = fields.One2many("web.sale.shop.product", related="product_asin_id.shop_product_ids", string="Shop Product SKUs")

    seller_skus = fields.Char(related="product_asin_id.seller_skus", string="Seller SKUs", store=True)

    currency_id = fields.Many2one(related="product_asin_id.currency_id", string="Currency")

    start_date = fields.Datetime("Statistic Start Date", readonly=True,)

    end_date = fields.Datetime("Statistic End Date", readonly=True,)

    stat_year = fields.Integer("Statistic Year", readonly=True,)

    stat_week = fields.Integer("Statistic Week", readonly=True,)

    date_modified_gmt = fields.Datetime("Modify Date", readonly=True,)

    order_volume = fields.Integer("Order Volume")

    product_volume = fields.Integer("Product Volume")

    amount_total = fields.Monetary("Amount Total")

    session_browser = fields.Integer("Browser Sessions")

    session_mobile = fields.Integer("Mobile Sessions")

    session_total = fields.Integer("Total Sessions")

    page_view_browser = fields.Integer("Browser Page Views")

    page_view_mobile = fields.Integer("Mobile Page Views")

    page_view_total = fields.Integer("Total Page Views")

    ads_clicks = fields.Integer("Ads Clicks")

    ads_impressions = fields.Integer("Ads Impressions")

    ads_total_spend = fields.Monetary("Ads Total Spend")

    ads_click_rate = fields.Float("Ads Click Rate")

    ads_avg_cpc = fields.Monetary("Average CPC")

    ads_order_volume = fields.Integer("Ads Order Volume")

    ads_order_rate = fields.Float("Ads Order Rate")   #广告订单量占比

    ads_amount_total = fields.Monetary("Ads Amount Total")

    ads_cvr = fields.Monetary("Ads CVR")

    acos = fields.Float("ACOS")

    acoas = fields.Float("ACOAS")

    asoas = fields.Float("ASOAS")

    ads_convention_rate = fields.Float("Ads Convention Rate")

    total_convention_rate = fields.Float("Total Convention Rate")

    seller_rank = fields.Integer("Seller Rank")

    seller_rank_sub1 = fields.Integer("Sub Category Rank 1")

    seller_rank_sub1_name = fields.Char("Sub Category Name 1")

    seller_rank_sub2 = fields.Integer("Sub Category Rank 2")

    seller_rank_sub2_name = fields.Char("Sub Category Name 2")

    seller_rank_sub3 = fields.Integer("Sub Category Rank 3")

    seller_rank_sub3_name = fields.Char("Sub Category Name 3")

    review_num = fields.Integer("Number of reviews")

    review_star = fields.Float("Stars")

    remark = fields.Text("Remarks")

    _sql_constraints = [
        ('shop_product_weekly_stat_uniq1', 'unique(shop_id, product_asin_id, stat_year, stat_month)', 'Product Asin in one shop in same week must be unique'),
    ]

    # def get_product_sale_data(self, shop_product, shop_warehouse, first_day):
    #     week_date_1 = subtract(start_of(first_day, 'week'), days=7)
    #     week_date_2 = subtract(start_of(first_day, 'week'), days=14)
    #     week_date_4 = subtract(start_of(first_day, 'week'), days=28)
    #
    #     sale_qty_7 = 0
    #     sale_qty_14 = 0
    #     sale_qty_28 = 0
    #
    #     product_asin_id = shop_product.product_asin_id.id
    #     shop_ids = shop_warehouse.shop_ids.mapped("id")
    #
    #     domain = [
    #         ("shop_id", "in", shop_ids),
    #         ("product_asin_id", "=", product_asin_id),
    #         ("start_date", ">=", week_date_1),
    #         ("start_date", "<", start_of(first_day, 'week')),
    #     ]
    #     result_list = self.read_group(domain, ["shop_id", "product_asin_id", "product_volume:sum"],
    #                                   groupby=["shop_id", "product_asin_id"])
    #
    #     if result_list:
    #         sale_qty_7 = result_list[0]["product_volume"]
    #
    #     domain = [
    #         ("shop_id", "in", shop_ids),
    #         ("product_asin_id", "=", product_asin_id),
    #         ("start_date", ">=", week_date_2),
    #         ("start_date", "<", start_of(first_day, 'week')),
    #     ]
    #     result_list = self.read_group(domain, ["shop_id", "product_asin_id", "product_volume:sum"],
    #                                   groupby=["shop_id", "product_asin_id"])
    #
    #     if result_list:
    #         sale_qty_14 = result_list[0]["product_volume"]
    #
    #     domain = [
    #         ("shop_id", "in", shop_ids),
    #         ("product_asin_id", "=", product_asin_id),
    #         ("start_date", ">=", week_date_4),
    #         ("start_date", "<", start_of(first_day, 'week')),
    #     ]
    #     result_list = self.read_group(domain, ["shop_id", "product_asin_id", "product_volume:sum"],
    #                                   groupby=["shop_id", "product_asin_id"])
    #
    #     if result_list:
    #         sale_qty_28 = result_list[0]["product_volume"]
    #
    #     return sale_qty_7, sale_qty_14, sale_qty_28

    def get_product_sale_data(self, shop_product, first_day):
        week_date_1 = subtract(start_of(first_day, 'week'), days=7)
        week_date_2 = subtract(start_of(first_day, 'week'), days=14)
        week_date_4 = subtract(start_of(first_day, 'week'), days=28)

        product_asin_id = shop_product.product_asin_id.id

        shop_ids = shop_product.shop_id.shop_warehouse_ids.shop_ids.mapped("id")

        # shop_ids = shop_warehouse.shop_ids.mapped("id")

        domain = [
            ("shop_id", "in", shop_ids),
            ("product_asin_id", "=", product_asin_id),
            ("start_date", ">=", week_date_4),
            ("start_date", "<", start_of(first_day, 'week')),
        ]
        result_list = self.search(domain)
        result_list_filtered = result_list.filtered(lambda r: r.start_date >= week_date_1)
        sale_qty_7 = sum(result_list_filtered.mapped("product_volume"))

        result_list_filtered = result_list.filtered(lambda r: r.start_date >= week_date_2)
        sale_qty_14 = sum(result_list_filtered.mapped("product_volume"))

        sale_qty_28 = sum(result_list.mapped("product_volume"))

        return sale_qty_7, sale_qty_14, sale_qty_28

