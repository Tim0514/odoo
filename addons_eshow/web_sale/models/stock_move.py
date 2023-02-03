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


class StockMove(models.Model):
    _inherit = 'stock.move'

    shop_product_id = fields.Many2one(comodel_name="web.sale.shop.product", string="Shop Product", readonly=True, )
