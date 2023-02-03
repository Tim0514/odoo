# Copyright 2018-2019 ForgeFlow, S.L.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_STATES = [
    ("new", "New"),
    ("error", "Error"),
    ("ok", "OK"),
    ("no_data", "No Sale Data"),
]

_RETURN_STATES = [
    (0, "No Return"),
    (1, "Returning"),
    (2, "Done"),
]


class WebSaleOrder(models.Model):
    _name = "web.sale.order"
    _description = "Web Sale Order"
    _order = "date_ordered, shop_id"

    shop_id = fields.Many2one(comodel_name="web.sale.shop", string="Shop", readonly=True, index=True, )

    company_id = fields.Many2one(
        comodel_name="res.company",
        related="shop_id.company_id",
        string='Company', store=True, readonly=True)

    order_ref = fields.Char("Order Id", readonly=True, index=True, )
    date_ordered = fields.Datetime("Order Date", readonly=True,)
    date_modified = fields.Datetime("Modify Date", readonly=True,)
    state = fields.Char(string="Status", readonly=True, index=True,)
    currency_id = fields.Many2one("res.currency", string="Currency", readonly=True,)
    amount_total = fields.Monetary("Total", readonly=True,)
    amount_refund = fields.Char(string="Refund Amount", readonly=True, )
    buyer_email = fields.Char(string="Buyer Email", readonly=True, )
    is_return = fields.Selection(_RETURN_STATES, string="Is Return", readonly=True,)
    fulfillment_channel_type = fields.Char("Fulfillment Channel", readonly=True,)
    is_mcf_order = fields.Boolean("Is MCF Order", readonly=True,)
    is_assessed = fields.Boolean("Is Assessed Order", readonly=True,)
    earliest_ship_date = fields.Datetime("Earliest Shipment Date", readonly=True,)
    shipment_date = fields.Datetime("Shipment Date", readonly=True,)
    shipment_date_local = fields.Datetime("Shipment Date(Local)", readonly=True,)
    last_update_date = fields.Datetime("Last Update Date", readonly=True,)
    seller_name = fields.Char(string="Seller Name", readonly=True, )
    tracking_number = fields.Char(string="Tracking No.", readonly=True, )
    postal_code = fields.Char(string="Postal Code", readonly=True, )
    phone = fields.Char(string="Phone", readonly=True, )
    posted_date = fields.Datetime("Payment Date", readonly=True,)


class WebSaleOrderLine(models.Model):
    _name = "web.sale.order.line"
    _description = "Web Sale Order Line"
    _order = "product_default_code"

    shop_product_id = fields.Many2one(comodel_name="web.sale.shop.product", string="Shop Product", readonly=True, index=True, )
# asin
# quantity_ordered
# seller_sku
# local_sku
# local_name