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

class LXStockPicking(models.Model):
    _name = 'web.sale.lx.stock.picking'
    _description = "Lingxing Stock Move"
    _order = "company_id, name desc, create_date"
    _check_company_auto = True

    company_id = fields.Many2one(comodel_name="res.company", string="Company", index=True)

    name = fields.Char("LX Stock Picking SN", index=True)

    related_shipment_sn = fields.Char("Related Shipment SN")

    lx_warehouse_id = fields.Integer("LX Warehouse ID", readonly=True)

    lx_picking_type = fields.Selection([
        ("1", "Manual In"), ("2", "Purchase In"), ("11", "Manual Out"), ("12", "FBA Out"),
        ("14", "Return Out"), ("26", "Return In"), ])

    lx_supplier_id = fields.Integer("LX Supplier ID", default=3831)

    stock_picking_id = fields.Many2one(comodel_name="stock.picking", string="Stock Picking",
                                       index=True, ondelete="cascade", check_company=True)

    is_synchronized = fields.Boolean("Is Synchronized", default=False, index=True)

    sync_time = fields.Datetime("Sync Time")

    remark = fields.Char("Remark")

    lx_stock_move_ids = fields.One2many(comodel_name="web.sale.lx.stock.move",
                                        inverse_name="lx_stock_picking_id", index=True, check_company=True)

    @api.depends("lx_stock_move_ids", "lx_stock_move_ids.is_synchronized")
    def _compute_is_synchronized(self):
        for rec in self:
            if len(rec.lx_stock_move_ids) > 0:
                rec.is_synchronized = all(rec.lx_stock_move_ids.mapped("is_synchronized"))
                rec.sync_time = max(rec.lx_stock_move_ids.mapped("sync_time"))
            else:
                rec.is_synchronized = False
                rec.sync_time = None

