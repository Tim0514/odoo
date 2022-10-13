# -*- coding: utf-8 -*-
from odoo import api, fields, models, SUPERUSER_ID, _
from collections import namedtuple, OrderedDict, defaultdict
from odoo import SUPERUSER_ID, models, api, fields
from odoo.tools import float_compare, float_round

from odoo.addons.stock.models.stock_rule import ProcurementException

import logging
_logger = logging.getLogger(__name__)


class StockRule(models.Model):
    _inherit = 'stock.rule'

    """
    增加传播组的设置
    """
    def _prepare_mo_vals(self, product_id, product_qty, product_uom, location_id, name, origin, company_id, values, bom):
        mo_vals = super(StockRule, self)._prepare_mo_vals(product_id, product_qty, product_uom, location_id, name, origin, company_id, values, bom)

        gpo = self.group_propagation_option
        group_id = (gpo == 'fixed' and self.group_id.id) or \
                (gpo == 'propagate' and values.get('group_id') and values['group_id'].id) or False

        mo_vals.update({
            'procurement_group_id':group_id,
        })
        return mo_vals

    """
        Modified by timwang on 2021/8/19
        Override mrp/stock_rule中运行MRP的方法

        运行MPS时，如果仅仅是新增了产品，其他都一样，则不创建新的生产单，而是直接在原生产单据中增加相关数量。
        TODO:暂未使用
    """
    @api.model
    def _run_manufacture_1(self, procurements):
        productions_values_by_company = defaultdict(list)
        errors = []
        for procurement, rule in procurements:
            bom = rule._get_matching_bom(procurement.product_id, procurement.company_id, procurement.values)
            if not bom:
                msg = _('There is no Bill of Material of type manufacture or kit found for the product %s. Please define a Bill of Material for this product.') % (procurement.product_id.display_name,)
                errors.append((procurement, msg))

            productions_values_by_company[procurement.company_id.id].append(rule._prepare_mo_vals(*procurement, bom))

        if errors:
            raise ProcurementException(errors)

        for company_id, productions_values in productions_values_by_company.items():

            for production_values in productions_values:

                # 查找是否有已经生成的条件相同的制造订单
                existing_production = self.env["mrp.production"].get_existing_production(production_values)

                if existing_production:
                    # 获取增量的领料和完工入库单
                    moves_raw_values = existing_production._get_moves_raw_values_new(production_values["product_qty"])
                    moves_finished_values = existing_production._get_moves_finished_values_new(production_values["product_qty"])

                    # 设置成品入库move_dest_ids用新补货中的move_dest_ids
                    for move_values in moves_finished_values:
                        move_values['move_dest_ids'] = production_values['move_dest_ids']

                    move_raw = self.env['stock.move'].sudo().create(moves_raw_values)
                    move_finished = self.env['stock.move'].sudo().create(moves_finished_values)

                    # 修改生产订单数量
                    existing_production.product_qty += production_values["product_qty"]

                    # 将dest补货单ID写入existing_production中
                    move_dest_ids = move_finished.move_dest_ids
                    existing_production.write({'move_dest_ids': [(4, m.id) for m in move_dest_ids]})

                    existing_production.filtered(lambda p: p.move_raw_ids).action_confirm()

                    origin_production = existing_production.move_dest_ids and existing_production.move_dest_ids[0].raw_material_production_id or False
                    orderpoint = existing_production.orderpoint_id
                    if orderpoint:
                        existing_production.message_post_with_view('mail.message_origin_link',
                                                          values={'self': existing_production, 'origin': orderpoint},
                                                          subtype_id=self.env.ref('mail.mt_note').id)
                    if origin_production:
                        existing_production.message_post_with_view('mail.message_origin_link',
                                                          values={'self': existing_production, 'origin': origin_production},
                                                          subtype_id=self.env.ref('mail.mt_note').id)

                else:
                    # create the MO as SUPERUSER because the current user may not have the rights to do it (mto product launched by a sale for example)
                    production = self.env['mrp.production'].with_user(SUPERUSER_ID).sudo().with_company(
                        company_id).create(production_values)
                    move_raw_values = production._get_moves_raw_values()
                    move_finished_values = production._get_moves_finished_values()
                    self.env['stock.move'].sudo().create(move_raw_values)
                    self.env['stock.move'].sudo().create(move_finished_values)
                    production._create_workorder()
                    production.filtered(lambda p: p.move_raw_ids).action_confirm()

                    origin_production = production.move_dest_ids and production.move_dest_ids[0].raw_material_production_id or False
                    orderpoint = production.orderpoint_id
                    if orderpoint:
                        production.message_post_with_view('mail.message_origin_link',
                                                          values={'self': production, 'origin': orderpoint},
                                                          subtype_id=self.env.ref('mail.mt_note').id)
                    if origin_production:
                        production.message_post_with_view('mail.message_origin_link',
                                                          values={'self': production, 'origin': origin_production},
                                                          subtype_id=self.env.ref('mail.mt_note').id)
        return True

