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

FBA_SHIPMENT_STATES = [
    ("working", "Working"),
    ("shipped", "Shipped"),
    ("in_transit", "In Transit"),
    ("delivered", "Delivered"),
    ("check_in", "Check In"),
    ("receiving", "Receiving"),
    ("closed", "Closed"),
    ("cancelled", "Cancelled"),
    ("delete", "Delete"),
    ("error", "Error"),
]

class StockMove(models.Model):
    _inherit = 'stock.move'

    @api.model
    def _get_shop_product_id(self):
        return self.shop_product_id.id

    shop_product_id = fields.Many2one(comodel_name="web.sale.shop.product", string="Shop Product", readonly=True, )

    lx_shipment_line_id = fields.Integer("LX Shipment Line ID", index=True, readonly=True)

    lx_stock_move_ids = fields.One2many("web.sale.lx.stock.move", "stock_move_id", string="LX Stock Moves", readonly=True)

    fba_shipment_id = fields.Char("FBA Shipment ID")

    fba_shipment_state = fields.Selection(FBA_SHIPMENT_STATES, "FBA Shipment Status")

    quantity_received = fields.Integer("Quantity Received", default=0)

    shipping_forecast_id = fields.Many2one("web.sale.shipping.forecast", "Shipping Forecast Id")

    shipping_method = fields.Many2one("web.sale.shipping.method", related="picking_id.shipping_method", string="Shipping Method")

    seller_sku = fields.Char(related="shop_product_id.seller_sku")

    estimate_arriving_date = fields.Date("Estimate Arriving Date", related="picking_id.estimate_arriving_date")
