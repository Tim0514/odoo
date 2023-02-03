# Copyright 2018-2019 ForgeFlow, S.L.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression

_STATES = [
    ("new", "New"),
    ("normal", "Normal Sale"),
    ("clearance", "Clearance"),
    ("stop", "Stop Sale"),
]


class ShopProduct(models.Model):
    _inherit = "web.sale.shop.product"

    lingxing_shop_id = fields.Integer(related="shop_id.lingxing_shop_id")
    lingxing_shop_name = fields.Char(related="shop_id.lingxing_shop_name")

