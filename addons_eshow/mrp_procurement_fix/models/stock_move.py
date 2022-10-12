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