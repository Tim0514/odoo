# -*- coding: utf-8 -*-
# (C) 2018 Smile (<http://www.smile.fr>)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    property_account_payable_advance_id = fields.Many2one(
        'account.account', "预付账款",  
        domain=[
            ('internal_type', '=', 'payable'),
            ('deprecated', '=', False),
        ], company_dependent=True)
    property_account_receivable_advance_id = fields.Many2one(
        'account.account', "预收账款",
        domain=[
            ('internal_type', '=', 'receivable'),
            ('deprecated', '=', False),
        ], company_dependent=True)
