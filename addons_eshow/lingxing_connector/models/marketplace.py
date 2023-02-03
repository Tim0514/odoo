# Copyright 2018-2019 ForgeFlow, S.L.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)

from odoo import _, api, fields, models

class Marketplace(models.Model):
    _inherit = "web.sale.marketplace"

    lingxing_marketplace_id = fields.Integer(string="Ling Xing Marketplace ID",)
    lingxing_marketplace_name = fields.Char(string="Ling Xing Marketplace Name",)