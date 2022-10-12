# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from collections import defaultdict
from datetime import datetime, time
from dateutil import relativedelta
from itertools import groupby
from psycopg2 import OperationalError

from odoo import SUPERUSER_ID, _, api, fields, models, registry
from odoo.exceptions import RedirectWarning, UserError, ValidationError
from odoo.osv import expression
from odoo.tools import add, float_compare, frozendict, split_every

_logger = logging.getLogger(__name__)

class StockWarehouseOrderpoint(models.Model):
    _inherit = "stock.warehouse.orderpoint"

    manuf_procure_delay = fields.Integer('产成品补货提前期', store=True, copy=True, default=0)
    lead_days_date = fields.Date('计划完成日期', compute='_compute_lead_days', store=True, readonly=False)


    @api.depends('route_id', 'product_id', 'location_id', 'company_id', 'warehouse_id', 'product_id.route_ids')
    def _compute_rules(self):
        for orderpoint in self:
            if not orderpoint.product_id or not orderpoint.location_id:
                orderpoint.rule_ids = False
                orderpoint.manuf_procure_delay = 0
                continue
            orderpoint.rule_ids = orderpoint.product_id._get_rules_from_location(orderpoint.location_id, route_ids=orderpoint.route_id)

            # # 制造产品需要补货的提前期
            # manufacture_rule = orderpoint.rule_ids.filtered(lambda r: r.action == 'manufacture')
            # if manufacture_rule:
            #     orderpoint.manuf_procure_delay = orderpoint.product_id.manuf_procure_delay

    @api.depends('rule_ids', 'product_id.seller_ids', 'product_id.seller_ids.delay')
    def _compute_lead_days(self):
        '''
        Timwang modified on 2022/3/12
        进行人工补货操作时，需要制造的产品，系统仅考虑了制造提前期，未考虑原材料采购需要的时间。
        因此，增加此字段，用于人工设定一个合理的产品制造的补货提前期。
        在执行手动立即补货的操作时，生成的制造订单完工日期为  当前日期+bom_material_delay
        :return:
        '''
        for orderpoint in self.with_context(bypass_delay_description=True):

            if not orderpoint.product_id or not orderpoint.location_id:
                orderpoint.lead_days_date = False
                continue
            values = orderpoint._get_lead_days_values()
            lead_days, dummy = orderpoint.rule_ids._get_lead_days(orderpoint.product_id, **values)

            # 在原有的Lead_days基础上，再加上制造产品补货需要的提前期。
            lead_days = lead_days + orderpoint.manuf_procure_delay

            lead_days_date = fields.Date.today() + relativedelta.relativedelta(days=lead_days)
            orderpoint.lead_days_date = lead_days_date

    @api.onchange('product_id', 'location_id')
    def onchange_product_id_location_id(self):
        # 当新建补货规则，或者'product_id', 'location_id'发生变化时，读取产品默认的最低补货数量，最高补货数量，制造产品的补货提前期
        for orderpoint in self:
            if (not orderpoint.product_id) or (not orderpoint.location_id):
                orderpoint.product_min_qty = 0
                orderpoint.product_max_qty = 0
                orderpoint.qty_multiple = 0
                orderpoint.qty_to_order = 0
                # orderpoint.qty_on_hand = 0
                # orderpoint.qty_forecast = 0
                orderpoint.manuf_procure_delay = 0
                continue

            orderpoint.product_min_qty = 0
            orderpoint.product_max_qty = 0
            orderpoint.qty_multiple = orderpoint.product_id.minimum_package_qty
            orderpoint.manuf_procure_delay = orderpoint.product_id.manuf_procure_delay
