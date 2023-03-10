# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, tools


class StockValuationLayer(models.Model):
    _inherit = 'stock.valuation.layer'

    company_id = fields.Many2one('res.company', 'Company', readonly=True, required=True, index=True)
