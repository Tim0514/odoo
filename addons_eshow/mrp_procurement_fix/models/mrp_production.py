# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import datetime
import math
import operator as py_operator
import re

from collections import defaultdict
from dateutil.relativedelta import relativedelta
from itertools import groupby

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_compare, float_round, float_is_zero, format_datetime
from odoo.tools.misc import format_date

from odoo.addons.stock.models.stock_move import PROCUREMENT_PRIORITIES

SIZE_BACK_ORDER_NUMERING = 3


class MrpProduction(models.Model):
    _inherit = ['mrp.production']

    @api.model
    def create(self, values):
        """
            Override 原有 mrp.production 中的create方法,
            阻止原方法中强制生成Groupid, 改为按规则设置GroupId, 相关代码在stock_rule中。

            原方法中，是强制生成一个group_id, 并且每次都生成新的生产订单
            如果Rule设置了GroupId留空，则不创建GroupId, 同时有相同生产日期的生产订单，则合并交货期相同，产品相同的行。
        """
        # Remove from `move_finished_ids` the by-product moves and then move `move_byproduct_ids`
        # into `move_finished_ids` to avoid duplicate and inconsistency.
        if values.get('move_finished_ids', False):
            values['move_finished_ids'] = list(filter(lambda move: move[2]['byproduct_id'] is False, values['move_finished_ids']))
        if values.get('move_byproduct_ids', False):
            values['move_finished_ids'] = values.get('move_finished_ids', []) + values['move_byproduct_ids']
            del values['move_byproduct_ids']

        if not values.get('name', False) or values['name'] == _('New'):
            picking_type_id = values.get('picking_type_id') or self._get_default_picking_type()
            picking_type_id = self.env['stock.picking.type'].browse(picking_type_id)
            if picking_type_id:
                values['name'] = picking_type_id.sequence_id.next_by_id()
            else:
                values['name'] = self.env['ir.sequence'].next_by_code('mrp.production') or _('New')

        production = super(models.Model, self).create(values)
        (production.move_raw_ids | production.move_finished_ids).write({
            'group_id': production.procurement_group_id.id,
            'origin': production.name
        })

        production.move_raw_ids.write({'date': production.date_planned_start})

        production.move_finished_ids.write({'date': production.date_planned_finished})

        # Trigger move_raw creation when importing a file
        if 'import_file' in self.env.context:
            production._onchange_move_raw()
            production._onchange_move_finished()
        return production

    """
        Added by timwang on 2012/8/19
        根据输入条件查询是否已经存在相关的生产订单。
        TODO:暂未使用
    """
    def get_existing_production_1(self, new_production_values):
        domain = (
            ("state", "=", "confirmed"),
            ("company_id", "=", new_production_values["company_id"]),
            ("product_id", "=", new_production_values["product_id"]),
            ("date_planned_start", "=", new_production_values["date_planned_start"]),
        )
        if self.procurement_group_id:
            domain += (("procurement_group_id", "=", self.procurement_group_id.id),)

        existing_production = self.search([dom for dom in domain])
        existing_production = existing_production[0] if existing_production else False
        return existing_production

    """
        Added by timwang on 2012/8/19
        根据输入的数量，生成一个新的原材料领料数据
        TODO:暂未使用
    """
    def _get_moves_raw_values_new_1(self, new_product_qty):
        moves = []

        for production in self:
            factor = production.product_uom_id._compute_quantity(new_product_qty, production.bom_id.product_uom_id) / production.bom_id.product_qty
            boms, lines = production.bom_id.explode(production.product_id, factor, picking_type=production.bom_id.picking_type_id)
            for bom_line, line_data in lines:
                if bom_line.child_bom_id and bom_line.child_bom_id.type == 'phantom' or\
                        bom_line.product_id.type not in ['product', 'consu']:
                    continue
                operation = bom_line.operation_id.id or line_data['parent_line'] and line_data['parent_line'].operation_id.id
                moves.append(production._get_move_raw_values(
                    bom_line.product_id,
                    line_data['qty'],
                    bom_line.product_uom_id,
                    operation,
                    bom_line
                ))
        return moves

    """
        Added by timwang on 2012/8/19
        根据输入的数量，生成一个新的完工入库数据
        TODO:暂未使用
    """
    def _get_moves_finished_values_new_1(self, new_product_qty):
        moves = []
        for production in self:
            if production.product_id in production.bom_id.byproduct_ids.mapped('product_id'):
                raise UserError(_("You cannot have %s  as the finished product and in the Byproducts", self.product_id.name))
            moves.append(production._get_move_finished_values(production.product_id.id, new_product_qty, production.product_uom_id.id))
            for byproduct in production.bom_id.byproduct_ids:
                product_uom_factor = production.product_uom_id._compute_quantity(new_product_qty, production.bom_id.product_uom_id)
                qty = byproduct.product_qty * (product_uom_factor / production.bom_id.product_qty)
                moves.append(production._get_move_finished_values(
                    byproduct.product_id.id, qty, byproduct.product_uom_id.id,
                    byproduct.operation_id.id, byproduct.id))
        return moves


    # def action_confirm(self):
    #     """
    #         timwang modified at 2021/8/21
    #
    #         运行MPS的时候，会生成新的MOVE,需要合并, 因此在确认MO的时候，仅对新加入的MOVE进行确认
    #     """
    #     self._check_company()
    #     for production in self:
    #         if production.bom_id:
    #             production.consumption = production.bom_id.consumption
    #         if not production.move_raw_ids:
    #             raise UserError(_("Add some materials to consume before marking this MO as to do."))
    #         # In case of Serial number tracking, force the UoM to the UoM of product
    #         if production.product_tracking == 'serial' and production.product_uom_id != production.product_id.uom_id:
    #             production.write({
    #                 'product_qty': production.product_uom_id._compute_quantity(production.product_qty, production.product_id.uom_id),
    #                 'product_uom_id': production.product_id.uom_id
    #             })
    #             for move_finish in production.move_finished_ids.filtered(lambda m: m.product_id == production.product_id):
    #                 move_finish.write({
    #                     'product_uom_qty': move_finish.product_uom._compute_quantity(move_finish.product_uom_qty, move_finish.product_id.uom_id),
    #                     'product_uom': move_finish.product_id.uom_id
    #                 })
    #         production.move_raw_ids.filtered(lambda r: r.state == "draft")._adjust_procure_method()
    #         (production.move_raw_ids.filtered(lambda r: r.state == "draft") | production.move_finished_ids.filtered(lambda r: r.state == "draft"))._action_confirm()
    #         production.workorder_ids.filtered(lambda r: r.state == "draft")._action_confirm()
    #
    #     # run scheduler for moves forecasted to not have enough in stock
    #     self.move_raw_ids._trigger_scheduler()
    #     return True