# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    maxshare_price_rate = fields.Float(
        "Max Share Price Rate",
        default=1.4,
        help="Invoice Price of EShow to Max Share = Product Cost * Max Share Price Rate.",
        config_parameter='eshow_ext.maxshare_price_rate',
    )

    export_declare_price_rate = fields.Float(
        "Export Declare Price Rate",
        default=1.2,
        help="Export Invoice Price = Invoice Price of EShow to Max Share * Export Declare Price Rate * Currency Exchange Rate.",
        config_parameter='eshow_ext.export_declare_price_rate',
    )

    destination_declare_price_rate = fields.Float(
        "Destination Declare Price Rate",
        default=0.5,
        help="Destination country custom clearance price = Product Cost * Destination Declare Price Rate * Currency Exchange Rate.",
        config_parameter='eshow_ext.destination_declare_price_rate',
    )

    def update_product_prices(self):
        product_template = self.env["product.template"]
        product_template_ids = product_template.search([])
        product_template_ids._compute_list_price()

        return True

        # return {
        #     'type': 'ir.actions.act_url',
        #     'url': '/',
        #     'target': 'self',
        # }