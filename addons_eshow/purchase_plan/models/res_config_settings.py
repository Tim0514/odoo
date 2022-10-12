# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    use_purchase_plan = fields.Boolean(
        "Use Purchase Plan",
        default=True,
        help="Use Purchase Plan instead of Purchase Order while running procurement.",
        config_parameter='purchase.use_purchase_plan',
    )
