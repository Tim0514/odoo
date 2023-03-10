# -*- coding: utf-8 -*-

from collections import namedtuple, OrderedDict, defaultdict

from dateutil.relativedelta import relativedelta

from odoo import models, api, fields
from odoo.tools import float_compare, float_round

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    unreserve_completely_visible = fields.Boolean(
        'Allowed to Unreserve Production Completely', compute='_compute_unreserve_completely_visible',
        help='Technical field to check when we can unreserve completely')

    def _prepare_subcontract_mo_vals(self, subcontract_move, bom):
        """
            修正，mrp_subcontracting模块中stockpicking中的同名方法，改成根据父节点的group
        """
        vals = super(StockPicking, self)._prepare_subcontract_mo_vals(subcontract_move, bom)

        if self.group_id:
            vals["procurement_group_id"] = self.group_id.id
        else:
            del vals["procurement_group_id"]
        return vals

    @api.depends('move_lines', 'state', 'move_lines.product_uom_qty', 'move_lines.move_orig_ids')
    def _compute_unreserve_completely_visible(self):
        for picking in self:
            already_reserved = picking.state not in ('done', 'cancel') and picking.mapped('move_lines.move_line_ids')
            make_to_order = picking.state not in ('done', 'cancel') and picking.move_lines.filtered(lambda r: r.procure_method == "make_to_order")
            move_orig_ids = picking.state not in ('done', 'cancel') and picking.mapped('move_lines.move_orig_ids')
            any_quantity_done = any(m.quantity_done > 0 for m in picking.move_lines)
            picking.unreserve_completely_visible = not any_quantity_done and (already_reserved or make_to_order or move_orig_ids)

    def do_unreserve_completely(self):
        self.move_lines.filtered(lambda x: x.state not in ('done', 'cancel'))._do_unreverse_completely()

