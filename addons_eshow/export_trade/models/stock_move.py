
from collections import defaultdict
from datetime import timedelta
from itertools import groupby
from odoo.tools import groupby as groupbyelem
from operator import itemgetter

from odoo import _, api, Command, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression
from odoo.tools.float_utils import float_compare, float_is_zero, float_round
from odoo.tools.misc import clean_context, OrderedSet


class StockMove(models.Model):
    _inherit = "stock.move"

    customs_declaration_stock_move_ids = fields.One2many(
        'sale.customs.declaration.stock.move', inverse_name='stock_move_id',
        string='Stock Move Declared', check_company=True)

    # 未报关数量
    undeclared_qty = fields.Float(
        string='Quantity Undeclared To Customs', digits='Product Unit of Measure', store=True, compute='_compute_undeclared_qty')

    @api.depends('customs_declaration_stock_move_ids', 'customs_declaration_stock_move_ids.product_qty')
    def _compute_undeclared_qty(self):
        for move in self:
            undeclared_qty = move.product_uom_qty
            for customs_declaration_stock_move in move.customs_declaration_stock_move_ids:
                undeclared_qty -= customs_declaration_stock_move.product_qty
            move.undeclared_qty = undeclared_qty

    @api.model
    def _prepare_customs_declaration_line(
            self, customs_declaration, stock_move):
        data = {
                "customs_declaration_id": customs_declaration.id,
                "product_id": stock_move.product_id.id,
                "unit_cost": stock_move.product_id.standard_price,
                "unit_declare_price": stock_move.product_id.export_declare_price,
            }
        return data

    @api.model
    def _prepare_customs_declaration_stock_move(
            self, customs_declaration, customs_declaration_line_id, stock_move):
        data = {
            "customs_declaration_id": customs_declaration.id,
            "stock_move_id": stock_move.id,
            "customs_declaration_line_id": customs_declaration_line_id,
            "product_qty": stock_move.undeclared_qty,
            "undeclared_qty": stock_move.undeclared_qty,
        }
        return data

    def do_recompute_undeclared_qty(self):
        model = self.env["stock.move"]
        stock_moves = model.search([("undeclared_qty", "=", "0")])
        for move in stock_moves:
            move._compute_undeclared_qty()

    def do_import_stock_moves_to_declaration(self):
        """
        导入选中的行到报关单中
        :return:
        """
        customs_declaration_id = self.env.context.get('customs_declaration_id')
        customs_declaration = self.env['sale.customs.declaration'].browse([customs_declaration_id])
        if customs_declaration:
            customs_declaration = customs_declaration[0]

            # 先将customs_declaration_line中的产品保存成字典，方便加速检索
            customs_declaration_products = {}
            for customs_declaration_line in customs_declaration.customs_declaration_line_ids:
                customs_declaration_products[str(customs_declaration_line.product_id.id)] = customs_declaration_line.id

            customs_declaration_line_obj = customs_declaration.customs_declaration_line_ids
            # 判断新加入的stock_move的产品，在字典中是否存在，如果没有，则需要在customs_declaration_line中新增一条数据
            for stock_move in self:
                if not customs_declaration_products.get(str(stock_move.product_id.id)):
                    customs_declaration_lines = customs_declaration_line_obj.create(
                        self._prepare_customs_declaration_line(customs_declaration, stock_move))
                    customs_declaration_products[str(stock_move.product_id.id)] = customs_declaration_lines[0].id

            # 将customs_declaration_stock_move中的stock_move_id保存成字典，方便加速检索
            customs_declaration_stock_moves = {}
            for customs_declaration_stock_move in customs_declaration.customs_declaration_stock_move_ids:
                customs_declaration_stock_moves[str(customs_declaration_stock_move.stock_move_id.id)] \
                    = customs_declaration_stock_move.id

            customs_declaration_stock_move_obj = customs_declaration.customs_declaration_stock_move_ids
            new_customs_declaration_stock_move_data = []
            for stock_move in self:
                if not customs_declaration_stock_moves.get(str(stock_move.id)):
                    new_customs_declaration_stock_move_data.append(self._prepare_customs_declaration_stock_move(
                        customs_declaration, customs_declaration_products[str(stock_move.product_id.id)], stock_move
                    ))

            customs_declaration_stock_move_obj.create(new_customs_declaration_stock_move_data)

        return
