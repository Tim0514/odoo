# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import time
from ast import literal_eval
from datetime import date, timedelta
from itertools import groupby
from operator import attrgetter, itemgetter
from collections import defaultdict

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.tools import date_utils


class Picking(models.Model):
    _inherit = "stock.picking"

    shipping_method = fields.Many2one("web.sale.shipping.method", string="Shipping Method")

    estimate_ship_days = fields.Integer("Estimate Ship Days")

    estimate_arriving_date = fields.Date("Estimate Arriving Date", compute="_compute_estimate_arriving_date", store=True)

    @api.depends("state", "partner_id", "shipping_method", "estimate_ship_days")
    def _compute_estimate_arriving_date(self):
        for picking in self:
            estimate_ship_days = 30
            if picking.state == "done":
                ship_date = picking.date_done
            else:
                ship_date = picking.scheduled_date

            if picking.shipping_method:
                estimate_ship_days = picking.shipping_method.estimate_ship_days
            elif picking.partner_id.default_shipping_method_id:
                estimate_ship_days = picking.partner_id.default_shipping_method_id.estimate_ship_days

            if ship_date:
                picking.estimate_arriving_date = date_utils.add(ship_date, days=estimate_ship_days)