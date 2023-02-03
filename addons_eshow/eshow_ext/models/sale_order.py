# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.


from odoo import api, fields, models, SUPERUSER_ID, _


class SaleOrder(models.Model):
    _inherit = "sale.order"

    _sql_constraints = [
        ('name_uniq2', 'unique(name)', 'Sale Order No. must be unique'),
    ]