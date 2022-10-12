
from collections import defaultdict, namedtuple
from math import log10

from odoo import api, fields, models, _
from odoo.tools.date_utils import add, subtract
from odoo.tools.float_utils import float_round
from odoo.osv.expression import OR, AND
from collections import OrderedDict
import time

class MrpProductionSchedule(models.Model):
    _inherit = 'mrp.production.schedule'

    def _get_procurement_extra_values(self, forecast_values):
        """
            Timwang modified at 2021/8/24
            根据补货日期分组
        """
        """ Extra values that could be added in the vals for procurement.

        return values pass to the procurement run method.
        rtype dict
        """

        # 取得计划时间
        plan_date = fields.Date.to_string(forecast_values['date_start'])

        group_name = "MPS/" + plan_date
        # 取得对应计划时间的Group Id
        procurement_group = self.env['procurement.group'].search([("name", "=", group_name),])

        # 如果没有，则新增一个
        if not procurement_group:
            values = [{"name": group_name, "move_type": "direct"}]
            procurement_group = self.env['procurement.group'].create(values)
        else:
            procurement_group = procurement_group[0]

        return {
            'date_planned': forecast_values['date_start'],
            'warehouse_id': self.warehouse_id,
            'group_id': procurement_group,
        }

    """
        Timwang modified at 2021/9/24
        原来的方法不能通过BOM得到采购物料的提前期，所以这里使用
        
        修改原计划lead_time为 规则里面设置的时间+产成品补货提前期。
    """
    def _get_lead_times(self):
        """ Get the lead time for each product in self. The lead times are
        based on rules lead times + produce delay or supplier info delay.
        """
        rules = self.product_id._get_rules_from_location(self.warehouse_id.lot_stock_id)

        value = rules._get_lead_days(self.product_id)[0] + self.product_id.manuf_procure_delay

        return value
