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

class LXStockMove(models.Model):
    _name = 'web.sale.lx.stock.move'
    _description = "Lingxing Stock Move"
    _check_company_auto = True

    company_id = fields.Many2one(comodel_name="res.company", string="Company", index=True)

    product_id = fields.Many2one(comodel_name="product.product", string="Product", index=True)

    default_code = fields.Char(related="product_id.default_code", index=True, store=True)

    product_name = fields.Char(related="product_id.name", index=True, store=True)

    shop_product_id = fields.Many2one(comodel_name="web.sale.shop.product", string="Shop Product", index=True, check_company=True)

    shop_product_seller_sku = fields.Char(related="shop_product_id.seller_sku", index=True, store=True)

    stock_move_id = fields.Many2one(comodel_name="stock.move", string="Stock Move", index=True, ondelete="cascade", check_company=True)

    lx_stock_picking_id = fields.Many2one(comodel_name="web.sale.lx.stock.picking", string="Stock Picking",
                                          index=True, ondelete="cascade", check_company=True)

    product_qty = fields.Integer("Product Qty")

    price_unit = fields.Float("Unit Price")

    is_synchronized = fields.Boolean(related="lx_stock_picking_id.is_synchronized", store=True, index=True)

    sync_time = fields.Datetime(related="lx_stock_picking_id.sync_time", store=True)

    remark = fields.Char("Remark")



