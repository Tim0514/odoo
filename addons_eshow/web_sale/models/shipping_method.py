# Copyright 2018-2019 ForgeFlow, S.L.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)

from odoo import _, api, fields, models

_BillingType = [
    ('volume_weight', 'Volume Weight'),
    ('volume', 'Volume'),
    ('weight', 'Weight'),
]


class ShippingMethod(models.Model):
    _name = "web.sale.shipping.method"
    _description = "Delivery Method"
    _order = "name"

    name = fields.Char(string="Name", index=True,)

    code = fields.Char(string="Code", index=True,)

    billing_type = fields.Selection(selection=_BillingType, string="Billing Type")

    zip_code = fields.Char(string="Zip Code",)

    volume_calc_param = fields.Integer(string="Volume Calculating Params")

    estimate_ship_days = fields.Integer(string="Estimate Ship Days")

    description = fields.Text(string="Description")
