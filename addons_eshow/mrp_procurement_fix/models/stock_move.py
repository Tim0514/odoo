# -*- coding: utf-8 -*-

import json
from collections import defaultdict
from datetime import datetime
from itertools import groupby
from operator import itemgetter
from re import findall as regex_findall
from re import split as regex_split
from dateutil import relativedelta

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression
from odoo.tools.float_utils import float_compare, float_is_zero, float_repr, float_round
from odoo.tools.misc import format_date, OrderedSet

import logging
_logger = logging.getLogger(__name__)

class StockMove(models.Model):
    _inherit = 'stock.move'


    """
        timwang add at 2019/8/19
        price_unit 设置为可复制。
    """
    price_unit = fields.Float(
        'Unit Price', help="Technical field used to record the product cost set by the user during a picking confirmation (when costing "
                           "method used is 'average price' or 'real'). Value given in company currency and in product uom.", copy=True)  # as it's a technical field, we intentionally don't provide the digits attribute

    def _adjust_procure_method(self):
        """
            timwang add at 2022/10/13
            修改stock/stock_move.py中的同名方法
            原方法中，读取可用库存使用的是product.free_qty字段，但是该字段没有考虑已有采购订单未到货的情况，因此将之改为product.virtual_available
        """
        """ This method will try to apply the procure method MTO on some moves if
        a compatible MTO route is found. Else the procure method will be set to MTS
        """
        # Prepare the MTSO variables. They are needed since MTSO moves are handled separately.
        # We need 2 dicts:
        # - needed quantity per location per product
        # - forecasted quantity per location per product
        mtso_products_by_locations = defaultdict(list)
        mtso_needed_qties_by_loc = defaultdict(dict)
        mtso_free_qties_by_loc = {}
        mtso_moves = self.env['stock.move']

        for move in self:
            product_id = move.product_id
            domain = [
                ('location_src_id', '=', move.location_id.id),
                ('location_id', '=', move.location_dest_id.id),
                ('action', '!=', 'push')
            ]
            rules = self.env['procurement.group']._search_rule(False, move.product_packaging_id, product_id, move.warehouse_id, domain)
            if rules:
                if rules.procure_method in ['make_to_order', 'make_to_stock']:
                    move.procure_method = rules.procure_method
                else:
                    # Get the needed quantity for the `mts_else_mto` moves.
                    mtso_needed_qties_by_loc[rules.location_src_id].setdefault(product_id.id, 0)
                    mtso_needed_qties_by_loc[rules.location_src_id][product_id.id] += move.product_qty

                    # This allow us to get the forecasted quantity in batch later on
                    mtso_products_by_locations[rules.location_src_id].append(product_id.id)
                    mtso_moves |= move
            else:
                move.procure_method = 'make_to_stock'

        # Get the forecasted quantity for the `mts_else_mto` moves.
        for location, product_ids in mtso_products_by_locations.items():
            products = self.env['product.product'].browse(product_ids).with_context(location=location.id)
            """
            新代码
            """
            mtso_free_qties_by_loc[location] = {product.id: product.virtual_available for product in products}
            """
            旧代码
            mtso_free_qties_by_loc[location] = {product.id: product.free_qty for product in products}
            """

        # Now that we have the needed and forecasted quantity per location and per product, we can
        # choose whether the mtso_moves need to be MTO or MTS.
        for move in mtso_moves:
            needed_qty = move.product_qty
            forecasted_qty = mtso_free_qties_by_loc[move.location_id][move.product_id.id]
            if float_compare(needed_qty, forecasted_qty, precision_rounding=move.product_uom.rounding) <= 0:
                move.procure_method = 'make_to_stock'
                mtso_free_qties_by_loc[move.location_id][move.product_id.id] -= needed_qty
            else:
                move.procure_method = 'make_to_order'



    """
        timwang add at 2019/8/19
        重载mrp/stock_move中方法，原方法中，如果是生产订单，就强制不允许设置picking
        但是这样会造成生产领料和完工单，中可以合并的数据无法合并。
    """
    def _should_be_assigned_1(self):
        self.ensure_one()
        return bool(not self.picking_id and self.picking_type_id)

    """
        重载mrp/stock_move中的方法
        考虑mrp合并领料单和完工入库单的需要，允许对应生产订单状态为confirmed，以及自身状态为waiting的move删除
    """
    def unlink_1(self):
        # Avoid deleting move related to active MO
        # timwang modified on 2021/8/19
        for move in self:
            if move.production_id and move.production_id.state not in ('draft', 'cancel', 'confirmed'):
                raise UserError(_('Please cancel the Manufacture Order first.'))

        # return super(StockMove, self).super(StockMove, self).unlink()

        # timwang modified on 2021/9/24
        # 对网络导入订单的入出库，允许删除
        # for move in self:
        #     if move.name.find("Web") != 0 and move.state not in ('draft', 'cancel', 'waiting'):
        #         raise UserError(_('You can only delete draft moves.'))

        if any(move.state not in ('draft', 'cancel', 'waiting') for move in self):
            raise UserError(_('You can only delete draft moves.'))

        # With the non plannified picking, draft moves could have some move lines.
        self.with_context(prefetch_fields=False).mapped('move_line_ids').unlink()

        return super(models.Model, self).unlink()