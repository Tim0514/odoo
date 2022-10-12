# -*- coding: utf-8 -*-

from collections import namedtuple, OrderedDict, defaultdict
from odoo import models, api, fields
from odoo.tools import float_compare, float_round

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _prepare_subcontract_mo_vals(self, subcontract_move, bom):
        subcontract_move.ensure_one()
        group = self.env['procurement.group'].search([('name', '=' , self.name), ('partner_id','=', self.partner_id.id)])
        if group:
            group = group[0]
        else:
            group = self.env['procurement.group'].create({
                'name': self.name,
                'partner_id': self.partner_id.id,
            })
        product = subcontract_move.product_id
        warehouse = self._get_warehouse(subcontract_move)
        vals = {
            'company_id': subcontract_move.company_id.id,
            'procurement_group_id': group.id,
            'product_id': product.id,
            'product_uom_id': subcontract_move.product_uom.id,
            'bom_id': bom.id,
            'location_src_id': subcontract_move.picking_id.partner_id.with_company(subcontract_move.company_id).property_stock_subcontractor.id,
            'location_dest_id': subcontract_move.picking_id.partner_id.with_company(subcontract_move.company_id).property_stock_subcontractor.id,
            'product_qty': subcontract_move.product_uom_qty,
            'picking_type_id': warehouse.subcontracting_type_id.id
        }
        return vals
