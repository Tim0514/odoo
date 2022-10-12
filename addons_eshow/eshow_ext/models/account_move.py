# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.model_create_multi
    def create(self, vals_list):
        # OVERRIDE
        moves = super(AccountMove, self).create(vals_list)
        for move in moves:
            if move.reversed_entry_id:
                continue
            stock_picking = move.line_ids.mapped('stock_picking_id')
            if not stock_picking:
                continue
            refs = ["<a href=# data-oe-model=stock.picking data-oe-id=%s>%s</a>" % tuple(name_get) for name_get in stock_picking.name_get()]
            message = _("This vendor bill has been created from: %s") % ','.join(refs)
            move.message_post(body=message)
        return moves

    def write(self, vals):
        # OVERRIDE
        old_stock_picking = [move.mapped('line_ids.stock_picking_id') for move in self]
        res = super(AccountMove, self).write(vals)
        for i, move in enumerate(self):
            new_stock_picking = move.mapped('line_ids.stock_picking_id')
            if not new_stock_picking:
                continue
            diff_picking = new_stock_picking - old_stock_picking[i]
            if diff_picking:
                refs = ["<a href=# data-oe-model=stock.picking data-oe-id=%s>%s</a>" % tuple(name_get) for name_get in diff_picking.name_get()]
                message = _("This vendor bill has been modified from: %s") % ','.join(refs)
                move.message_post(body=message)
        return res


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    stock_move_id = fields.Many2one('stock.move', 'Stock Move', ondelete='set null', index=True)

    stock_picking_id = fields.Many2one('stock.picking', 'Stock Picking', related='stock_move_id.picking_id', readonly=True)

    def _copy_data_extend_business_fields(self, values):
        # OVERRIDE to copy the 'purchase_line_id' field as well.
        super(AccountMoveLine, self)._copy_data_extend_business_fields(values)
        values['stock_move_id'] = self.stock_move_id.id
        values['stock_picking_id'] = self.stock_picking_id.id
