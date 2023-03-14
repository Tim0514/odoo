# Copyright 2018-2019 ForgeFlow, S.L.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import start_of, subtract

_STATES = [
    ("new", "New"),
    ("error", "Error"),
    ("ok", "OK"),
    ("no_data", "No Sale Data"),
]

_RETURN_STATES = [
    ("0", "No Return"),
    ("1", "Returning"),
    ("2", "Done"),
]


class WebSaleOrder(models.Model):
    _name = "web.sale.order"
    _description = "Web Sale Order"
    _order = "date_ordered, shop_id"
    _rec_name = "order_ref"

    shop_id = fields.Many2one(comodel_name="web.sale.shop", string="Shop", index=True, )

    company_id = fields.Many2one(
        comodel_name="res.company",
        related="shop_id.company_id",
        string='Company', store=True, index=True)

    order_ref = fields.Char("Order Id", index=True, )
    system_order_ref = fields.Char("System Order Id", index=True, )
    date_ordered = fields.Datetime("Order Date", index=True)
    date_ordered_local = fields.Char("Order Date(Local)", index=True)
    date_modified = fields.Datetime("Modify Date", index=True)
    state = fields.Char(string="Status", index=True, )
    currency_id = fields.Many2one("res.currency", string="Currency",)
    amount_total = fields.Monetary("Total",)
    amount_refund = fields.Char(string="Refund Amount", )
    buyer_name = fields.Char(string="Buyer Name", )
    buyer_email = fields.Char(string="Buyer Email", )
    is_return = fields.Selection(_RETURN_STATES, string="Is Return", index=True)
    fulfillment_channel_type = fields.Char("Fulfillment Channel", index=True)
    is_mcf_order = fields.Boolean("Is MCF Order", index=True)
    is_assessed = fields.Boolean("Is Assessed Order", index=True)
    earliest_ship_date = fields.Datetime("Earliest Shipment Date",)
    shipment_date = fields.Datetime("Shipment Date",)
    shipment_date_local = fields.Char("Shipment Date(Local)",)
    last_update_date = fields.Datetime("Last Update Date", index=True)
    last_update_date_local = fields.Char("Last Update Date(Local)",)
    tracking_number = fields.Char(string="Tracking No.", )
    postal_code = fields.Char(string="Postal Code", )
    phone = fields.Char(string="Phone", )
    posted_date = fields.Datetime("Payment Date",)
    receiver_name = fields.Char(string="Receiver Name", )
    receiver_country_code = fields.Char(string="Country Code", )
    receiver_city = fields.Char(string="City", )
    receiver_state_or_region = fields.Char(string="State Or Region", )
    receiver_address_1 = fields.Char(string="Address", )
    receiver_address_2 = fields.Char(string="Address 2", )
    receiver_address_3 = fields.Char(string="Address 3", )

    order_lines = fields.One2many("web.sale.order.line", inverse_name="order_id")


class WebSaleOrderLine(models.Model):
    _name = "web.sale.order.line"
    _description = "Web Sale Order Line"
    _order = "product_default_code"

    shop_product_id = fields.Many2one(comodel_name="web.sale.shop.product", string="Shop Product", index=True,)
    product_default_code = fields.Char(related="shop_product_id.product_default_code", store=True, index=True)
    seller_sku = fields.Char(related="shop_product_id.seller_sku", store=True, index=True)
    product_name = fields.Char(related="shop_product_id.product_name", store=True, index=True)
    quantity_ordered = fields.Integer("Quantity")
    order_id = fields.Many2one(comodel_name="web.sale.order", index=True, ondelete="cascade")
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="order_id.company_id",
        string='Company', store=True, index=True)

    def get_product_sale_data(self, shop_product, last_day):
        """
        返回产品 在 指定日期之前，7，14，30天的销量
        :param shop_product:
        :param last_day:
        :return:
        """
        # week_date_1 = subtract(start_of(first_day, 'week'), days=7)
        # week_date_2 = subtract(start_of(first_day, 'week'), days=14)
        # week_date_4 = subtract(start_of(first_day, 'week'), days=30)
        week_date_1 = subtract(last_day, days=7)
        week_date_2 = subtract(last_day, days=14)
        week_date_3 = subtract(last_day, days=28)
        week_date_4 = subtract(last_day, days=30)

        product_asin_id = shop_product.product_asin_id.id

        shop_ids = shop_product.shop_id.shop_warehouse_ids.shop_ids.mapped("id")

        # shop_ids = shop_warehouse.shop_ids.mapped("id")

        domain = [
            ("order_id.shop_id", "in", shop_ids),
            ("shop_product_id.product_asin_id", "=", product_asin_id),
            ("order_id.date_ordered", ">=", week_date_4),
            ("order_id.date_ordered", "<", last_day),
            ("order_id.is_mcf_order", "=", False),
            ("order_id.is_assessed", "=", False),
            # ("order_id.is_return", "=", "0"),
            ("order_id.state", "!=", "Canceled"),
            # ("order_id.date_ordered", "<", start_of(first_day, 'week')),
        ]
        result_list = self.search(domain)
        result_list_filtered = result_list.filtered(lambda r: r.order_id.date_ordered >= week_date_1)
        sale_qty_7 = sum(result_list_filtered.mapped("quantity_ordered"))

        result_list_filtered = result_list.filtered(lambda r: r.order_id.date_ordered >= week_date_2)
        sale_qty_14 = sum(result_list_filtered.mapped("quantity_ordered"))

        result_list_filtered = result_list.filtered(lambda r: r.order_id.date_ordered >= week_date_3)
        sale_qty_28 = sum(result_list_filtered.mapped("quantity_ordered"))

        sale_qty_30 = sum(result_list.mapped("quantity_ordered"))

        last_day_y1 = subtract(last_day, years=1)
        domain = [
            ("order_id.shop_id", "in", shop_ids),
            ("shop_product_id.product_asin_id", "=", product_asin_id),
            ("order_id.date_ordered", ">=", subtract(last_day_y1, days=30)),
            ("order_id.date_ordered", "<", last_day_y1),
            ("order_id.is_mcf_order", "=", False),
            ("order_id.is_assessed", "=", False),
            # ("order_id.is_return", "=", "0"),
            ("order_id.state", "!=", "Canceled"),
            # ("order_id.date_ordered", "<", start_of(first_day, 'week')),
        ]
        result_list = self.search(domain)
        sale_qty_30_y_1 = sum(result_list.mapped("quantity_ordered"))


        rtn_dict = {
            "7": sale_qty_7,
            "14": sale_qty_14,
            "28": sale_qty_28,
            "30": sale_qty_30,
            "30_y_1": sale_qty_30_y_1,
        }

        return rtn_dict


