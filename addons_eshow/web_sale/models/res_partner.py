# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models
from odoo.addons.base.models.res_partner import WARNING_MESSAGE, WARNING_HELP

class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Partner是否为网上商店
    is_web_shop = fields.Boolean(string='Is Web Shop', default=False)

    # 默认的运输方式
    default_shipping_method_id = fields.Many2one("web.sale.shipping.method", string="Default Shipping Method")

