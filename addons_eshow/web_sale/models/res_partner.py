# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models

class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Partner是否为网上商店
    is_web_shop = fields.Boolean(string='Is Web Shop', compute="_compute_is_web_shop", store=True)

    web_shop_id = fields.Many2one("web.sale.shop", string="Web Shop")

    # 默认的运输方式
    default_shipping_method_id = fields.Many2one("web.sale.shipping.method", string="Default Shipping Method")

    @api.depends("web_shop_id")
    def _compute_is_web_shop(self):
        for rec in self:
            if rec.web_shop_id:
                rec.is_web_shop = True
            else:
                rec.is_web_shop = False
