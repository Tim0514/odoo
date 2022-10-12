# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models
from odoo.addons.base.models.res_partner import WARNING_MESSAGE, WARNING_HELP

class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Partner是否为网上商店
    is_web_shop = fields.Boolean(string='Is Web Shop', default=False)

    # 网店平台
    marketplace_id = fields.Many2one(comodel_name="web.sale.marketplace", string='Marketplace')

    merchant_code = fields.Char(string='Merchant Code')

    default_warehouse_id = fields.Many2one(comodel_name="stock.warehouse", string='Web Shop Default Warehouse')

    auth_token = fields.Char(string='Authorization Token')

    access_key = fields.Char(string='Access Key')

    secret_key = fields.Char(string="Secret Key")

