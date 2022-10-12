# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from collections import defaultdict
from datetime import datetime
from dateutil.relativedelta import relativedelta
from itertools import groupby
from odoo.tools import float_compare

from odoo import api, fields, models, SUPERUSER_ID, _
from odoo.addons.stock.models.stock_rule import ProcurementException


class StockRule(models.Model):
    _inherit = 'stock.rule'

    def _get_stock_move_values(self, product_id, product_qty, product_uom, location_id, name, origin, company_id, values):
        """
        当为公司间调拨时，
        产品成本原来逻辑是不传入产品成本，从而使用接收公司的产品成本。
        现改在收货单中加上调出公司产品的成本，从而使接收公司以发出公司的产品成本接收产品。

        本方法目前暂时只考虑了平均成本AVCO计价方式。
        对标准成本模式应该没有影响。
        对FIFO，应该会有错误。只能取到最新的产品成本。
        """

        # 调用父类相同方法
        move_values = super()._get_stock_move_values(product_id, product_qty, product_uom, location_id, name, origin, company_id, values)

        if location_id.usage == "transit" and not location_id.company_id:
            # 如果目的货位为公司间的中转货位 Inter-company transit
            # 则表示这是一个公司间的调拨
            # 找到该move的下游收货move,加上产品成本

            product_cost = product_id.with_company(self.location_src_id.company_id).standard_price
            for move_dest_id in values['move_dest_ids']:
                move_dest_id.price_unit = product_cost


        return move_values
