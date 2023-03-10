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

    """
        timwang add at 2022/10/13
        修改stock/stock_move.py中的同名方法

        free_qty是产品的当前真实可用库存
        virtual_available 是考虑了未完成的入出库后计算的可用库存
        由于我们在实际使用中，在作业类型中的出库类作业（交货单，制造单，内部调拨，外包）设置了预约方式为”人工“。
        因此，不会自动锁定库存，这会造成产品的free_qty不变。
        原_adjust_procure_method方法中，读取可用库存使用的是product.free_qty字段。如果相同原材料需要多次被领用，则无法产生相关的采购。
        这样就不对了。因此此将之改为product.virtual_available。
    """
    def _adjust_procure_method(self):
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

    def _do_unreverse_completely(self):
        """
        通过路线补货的stock_move, 如果设置为MTO或者是MTSO, 则procure_method有可能为make_to_order，并且会保存上游的入库单ID。
        odoo系统中原有的取消保留功能（_do_unreverse），对于此种情况，并不能真正释放库存，而仅仅是将库存释放给上游入库单ID相同的其他出库类单据

        因此增加本方法，对状态为confirmed, waiting, partially_available, assigned这几种类型的stock_move做如下操作：
        1. procure_method 改为make_to_order，
        2. 删除与上游单据的关联。
        3. 删除对应的stock_move_line数据(同时会更新stock_quant中的相关库存数据)
        :return: Boolean
        """
        moves_to_unreserve = OrderedSet()
        for move in self:
            if move.state == 'cancel' or (move.state == 'done' and move.scrapped):
                # We may have cancelled move in an open picking in a "propagate_cancel" scenario.
                # We may have done move in an open picking in a scrap scenario.
                continue
            elif move.state == 'done':
                raise UserError(_("You cannot unreserve a stock move that has been set to 'Done'."))
            moves_to_unreserve.add(move.id)
        moves_to_unreserve = self.env['stock.move'].browse(moves_to_unreserve)

        ml_to_update, ml_to_unlink = OrderedSet(), OrderedSet()
        moves_not_to_recompute = OrderedSet()
        for ml in moves_to_unreserve.move_line_ids:
            if ml.qty_done:
                ml_to_update.add(ml.id)
            else:
                ml_to_unlink.add(ml.id)
                moves_not_to_recompute.add(ml.move_id.id)
        ml_to_update, ml_to_unlink = self.env['stock.move.line'].browse(ml_to_update), self.env['stock.move.line'].browse(ml_to_unlink)
        moves_not_to_recompute = self.env['stock.move'].browse(moves_not_to_recompute)

        ml_to_update.write({'product_uom_qty': 0})
        ml_to_unlink.unlink()

        # for move in moves_to_unreserve:
        #     if move.move_orig_ids:
        #         move.move_orig_ids

        moves_to_unreserve.write({'procure_method': 'make_to_stock', "move_orig_ids": [(5, 0, 0)]})

        # `write` on `stock.move.line` doesn't call `_recompute_state` (unlike to `unlink`),
        # so it must be called for each move where no move line has been deleted.
        (moves_to_unreserve - moves_not_to_recompute)._recompute_state()
        return True
