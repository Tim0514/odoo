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
from odoo.tools import groupby
from operator import itemgetter

class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    unreserve_completely_visible = fields.Boolean(
        'Allowed to Unreserve Production Completely', compute='_compute_unreserve_completely_visible',
        help='Technical field to check when we can unreserve completely')

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

        # 注释掉原代码中强制生成补货组的代码
        # if not values.get('procurement_group_id'):
        #     procurement_group_vals = self._prepare_procurement_group_vals(values)
        #     values['procurement_group_id'] = self.env["procurement.group"].create(procurement_group_vals).id

        try:
            production = super(models.Model, self).create(values)
        except Exception as error:
            pass
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
            production._onchange_workorder_ids()
        return production

    @api.depends('move_raw_ids', 'state', 'move_raw_ids.product_uom_qty', 'move_raw_ids.move_orig_ids')
    def _compute_unreserve_completely_visible(self):
        for order in self:
            already_reserved = order.state not in ('done', 'cancel') and order.mapped('move_raw_ids.move_line_ids')
            make_to_order = order.state not in ('done', 'cancel') and order.move_raw_ids.filtered(lambda r: r.procure_method == "make_to_order")
            move_orig_ids = order.state not in ('done', 'cancel') and order.mapped('move_raw_ids.move_orig_ids')
            any_quantity_done = any(m.quantity_done > 0 for m in order.move_raw_ids)

            order.unreserve_completely_visible = not any_quantity_done and (already_reserved or make_to_order or move_orig_ids)

    def do_unreserve_completely(self):
        self.move_raw_ids.filtered(lambda x: x.state not in ('done', 'cancel'))._do_unreverse_completely()

    """
        Added by timwang on 2023/2/4
        根据输入条件查询是否已经存在相关的生产订单。
    """
    def get_existing_productions(self, new_production_values):
        domain = [
            ("company_id", "=", new_production_values["company_id"]),
            ("product_id", "=", new_production_values["product_id"]),
            ("date_planned_start", "=", new_production_values["date_planned_start"]),
            ("state", "=", "confirmed"),
        ]
        if self.procurement_group_id:
            domain.append([("procurement_group_id", "=", self.procurement_group_id.id)])

        existing_productions = self.search([dom for dom in domain])
        return existing_productions

    """
        Added by timwang on 2012/8/19
        根据输入的数量，生成一个新的原材料领料数据
        TODO:暂未使用
    """
    def _get_moves_raw_values_new(self, new_product_qty):
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
    """
    def _get_moves_finished_values_new(self, new_product_qty):
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

    def _merge_productions_fields(self):
        """ This method will return a dict of production’s values that represent the values of all moves in `self` merged. """

        origin = '/'.join(set(self.filtered(lambda m: m.origin).mapped('origin')))
        product_description_variants = '/'.join(set(self.filtered(lambda m: m.product_description_variants).mapped('product_description_variants')))

        return {
            'product_qty': sum(self.mapped('product_qty')),
            'qty_producing': sum(self.mapped('qty_producing')),
            'move_raw_ids': [(4, m.id) for m in self.mapped('move_raw_ids')],
            'move_finished_ids': [(4, m.id) for m in self.mapped('move_finished_ids')],
            'move_byproduct_ids': [(4, m.id) for m in self.mapped('move_byproduct_ids')],
            'finished_move_line_ids': [(4, m.id) for m in self.mapped('finished_move_line_ids')],
            'workorder_ids': [(4, m.id) for m in self.mapped('workorder_ids')],
            'move_dest_ids': [(4, m.id) for m in self.mapped('move_dest_ids')],
            'scrap_ids': [(4, m.id) for m in self.mapped('scrap_ids')],
            'origin': origin,
            'product_description_variants': product_description_variants,
        }

    @api.model
    def _prepare_merge_productions_distinct_fields(self):
        fields = [
            'product_id', 'date_planned_start', 'date_planned_finished',
            'date_start', 'date_finished', 'bom_id',
            'user_id', 'company_id', 'procurement_group_id', 'orderpoint_id',
            'propagate_cancel', 'consumption',
        ]
        return fields

    def _clean_merged(self):
        """Cleanup hook used when merging moves"""
        self.write({'propagate_cancel': False})

    def _merge_productions(self, merge_into=False):
        distinct_fields = self._prepare_merge_productions_distinct_fields()

        productions_to_merge = self
        if merge_into:
            productions_to_merge = merge_into | productions_to_merge

        productions_to_unlink = self.env['mrp.production']
        merged_productions = self.env['mrp.production']

        for k, g in groupby(productions_to_merge, key=itemgetter(*distinct_fields)):
            productions = self.env['mrp.production'].concat(*g)
            if len(productions) > 0:
                productions.mapped('move_raw_ids').write({'production_id': productions[0].id})
                productions.mapped('move_finished_ids').write({'production_id': productions[0].id})
                productions.mapped('move_byproduct_ids').write({'production_id': productions[0].id})
                productions.mapped('finished_move_line_ids').write({'production_id': productions[0].id})
                productions.mapped('move_dest_ids').write({'production_id': productions[0].id})
                productions.mapped('scrap_ids').write({'production_id': productions[0].id})

                # todo: workorder暂时不能合并
                # productions.mapped('workorder_ids').write({'production_id': productions[0].id})

                productions[0].write(productions._merge_productions_fields())

                # update merged moves dicts
                productions_to_unlink |= productions[1:]
                merged_productions |= productions[0]

        merged_productions.mapped('move_raw_ids')._merge_moves(merged_productions.mapped('move_raw_ids'))
        merged_productions.mapped('move_finished_ids')._merge_moves(merged_productions.mapped('move_finished_ids'))
        merged_productions.mapped('move_byproduct_ids')._merge_moves(merged_productions.mapped('move_byproduct_ids'))

        if productions_to_unlink:
            # We are using propagate to False in order to not cancel destination moves merged in moves[0]
            productions_to_unlink._clean_merged()
            productions_to_unlink.action_cancel()
            productions_to_unlink.state = 'cancel'
            productions_to_unlink.sudo().unlink()

        return (self | merged_productions) - productions_to_unlink