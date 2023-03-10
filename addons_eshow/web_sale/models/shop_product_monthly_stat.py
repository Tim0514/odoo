# Copyright 2018-2019 ForgeFlow, S.L.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ShopProductMonthlyStat(models.Model):
    _name = "web.sale.shop.product.monthly.stat"
    _description = "Shop Product Monthly Statics"
    _order = "shop_name, product_asin"
    _check_company_auto = True

    shop_id = fields.Many2one(comodel_name="web.sale.shop", string="Shop", store=True, index=True, check_company=True)

    company_id = fields.Many2one(
        comodel_name="res.company", string="Company", related="shop_id.company_id", store=True, index=True,
    )

    shop_name = fields.Char(related="shop_id.name", string="Web Shop Name", store=True, index=True,)

    product_asin_id = fields.Many2one("web.sale.shop.product.asin", string="ASIN", store=True, index=True, check_company=True)

    product_asin = fields.Char(related="product_asin_id.product_asin", string="ASIN", store=True, index=True,)

    currency_id = fields.Many2one(related="product_asin_id.currency_id", string="Currency")

    stat_month = fields.Datetime("Statistic Month", readonly=True,)

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

