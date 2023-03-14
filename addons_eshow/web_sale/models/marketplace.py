# Copyright 2018-2019 ForgeFlow, S.L.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)

from odoo import _, api, fields, models

_MarketplaceType = [
    ('aliexpress', 'Ali Express'),
    ('amazon', 'Amazon'),
    ('coupang', 'Coupang'),
    ('ebay', 'Ebay'),
    ('lazada', 'Lazada'),
    ('newegg', 'New Egg'),
    ('shopee', 'Shopee'),
    ('shopify', 'Shopify'),
    ('tiktok', 'Tiktok'),
    ('walmart', 'Walmart'),
    ('wayfair', 'Wayfair'),
    ('wish', 'Wish'),
    ('other', 'Other'),
]

class Marketplace(models.Model):
    _name = "web.sale.marketplace"
    _description = "Marketplace"
    _order = "name"

    name = fields.Char(
        string="Marketplace Name",
        index=True,
    )

    country_id = fields.Many2one(comodel_name="res.country", string='Country')

    type = fields.Selection(selection=_MarketplaceType, string="Marketplace Type")

    code = fields.Char(
        string="Marketplace Code",
    )

    endpoint = fields.Char(string="Web Service Endpoint",)

    description = fields.Text(string="Description")

    timezone = fields.Char(string="Time Zone")