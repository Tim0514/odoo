# Copyright 2018-2019 ForgeFlow, S.L.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_STATES = [
    ("new", "New"),
    ("error", "Error"),
    ("ok", "OK"),
    ("no_data", "No Sale Data"),
]


class ShopSaleData(models.Model):
    _name = "web.sale.shop.sale.data"
    _description = "Shop Week Sale Data"
    _order = "order_date, shop_id, product_id "
    _check_company_auto = True

    shop_product_id = fields.Many2one(
        comodel_name="web.sale.shop.product",
        string="Shop Product",
        store=True,
    )

    shop_id = fields.Many2one(
        related="shop_product_id.shop_id",
        string="Shop",
        store=True,
        readonly=True,
    )

    company_id = fields.Many2one(
        comodel_name="res.company",
        related="shop_id.company_id",
        string='Company', store=True, readonly=True)

    warehouse_id = fields.Many2one(
        related="shop_id.default_warehouse_id",
        string="Warehouse",
        store=True,
        readonly=True,
    )

    product_id = fields.Many2one(
        related="shop_product_id.product_id",
        string="Product",
        store=True,
    )

    product_default_code = fields.Char(
        related="product_id.default_code",
        string="Default Code",
        store=True,
        readonly=True,
    )

    product_name = fields.Char(
        related="product_id.name",
        string="Product Name",
        store=True,
        readonly=True,
    )

    imported_shop_name = fields.Char(
        string="Imported Shop Name",
        store=True,
        required=True,
    )

    imported_product_default_code = fields.Char(
        string="Imported Product Default Code",
        store=True,
    )

    imported_product_sku = fields.Char(
        string="Imported Product SKU",
        index=True,
    )

    imported_product_name = fields.Char(
        string="Imported Product Name",
    )

    sale_qty = fields.Float(string='Sale Qty')

    return_qty = fields.Float(string='Return Qty')

    scrap_qty = fields.Float(string='Scrap Qty')

    state = fields.Selection(
        selection=_STATES,
        string="Status",
        default="new",
        readonly=True,
        index=True,
    )

    sale_stock_move_id = fields.Many2one(
        comodel_name="stock.move",
        string="Sale Stock Move",
    )

    return_stock_move_id = fields.Many2one(
        comodel_name="stock.move",
        string="Return Stock Move",
    )

    scrap_stock_move_id = fields.Many2one(
        comodel_name="stock.move",
        string="Return Stock Move",
    )

    order_date = fields.Date(string="Order Date", required=True, help="Transaction Date")

    @api.model_create_multi
    @api.returns('self', lambda value: value.id)
    def create(self, vals_list):
        shop_product = self.env["web.sale.shop.product"]
        for val_list in vals_list:

            # 如果有产品编码，则用产品编码查找shop_product_id, 否则用店铺编码查找
            if "imported_product_default_code" in val_list:
                shop_product_id = shop_product.name_search("%s: %s: %s" % (val_list["imported_shop_name"], val_list["imported_product_default_code"], ""))
            else:
                shop_product_id = shop_product.name_search("%s: %s: %s" % (val_list["imported_shop_name"], "", val_list["imported_product_sku"]))

            if shop_product_id:
                val_list["shop_product_id"] = shop_product_id[0][0]

                if "sale_qty" not in val_list:
                    val_list["sale_qty"] = 0

                if "return_qty" not in val_list:
                    val_list["return_qty"] = 0

                if "scrap_qty" not in val_list:
                    val_list["scrap_qty"] = 0

                if val_list["sale_qty"] == 0 and val_list["return_qty"] == 0 and val_list["scrap_qty"] == 0:
                    val_list["state"] = "no_data"
                else:
                    val_list["state"] = "ok"
            else:
                val_list["state"] = "error"

        shop_sale_datas = super(models.Model, self).create(vals_list)

        self._generate_stock_moves(shop_sale_datas)

        return shop_sale_datas

    def unlink(self):

        if not self:
            return True

        # 已完成的stock_move不能够删除，直接创建反向stock_move
        self._generate_reverse_stock_moves(self)

        # for shop_sale_data in self:
        #     if shop_sale_data.sale_stock_move_id:
        #         # shop_sale_data.sale_stock_move_id._action_cancel()
        #         shop_sale_data.sale_stock_move_id.unlink()
        #     if shop_sale_data.return_stock_move_id:
        #         # shop_sale_data.return_stock_move_id._action_cancel()
        #         shop_sale_data.return_stock_move_id.unlink()
        #     if shop_sale_data.scrap_stock_move_id:
        #         # shop_sale_data.scrap_stock_move_id._action_cancel()
        #         shop_sale_data.scrap_stock_move_id.unlink()

        return super(models.Model, self).unlink()

    def _generate_stock_moves(self, shop_sale_data_list):
        """ Generate a stock move for each product of a sale order. """

        customers_location = self.env.ref('stock.stock_location_customers')
        scrap_location_id = self.env['stock.scrap']._get_default_scrap_location_id()

        for shop_sale_data in shop_sale_data_list:
            if shop_sale_data.state != "ok":
                continue

            warehouse_id = shop_sale_data.shop_id.default_warehouse_id
            location_id = warehouse_id.lot_stock_id

            if shop_sale_data.sale_qty != 0:
                picking_type_id = warehouse_id.out_type_id

                picking_name = 'Web Sale: %s' %picking_type_id.sequence_id.next_by_id()

                stock_move_vals = {
                    'company_id': shop_sale_data.company_id.id,
                    'name': shop_sale_data.product_id.name_get(),
                    'state': 'draft',
                    'picking_type_id': picking_type_id,
                    'location_id': location_id.id,
                    'location_dest_id': customers_location.id,
                    'additional': False,
                    'product_id': shop_sale_data.product_id.id,
                    'description_picking': shop_sale_data.product_id.name,
                    'date': shop_sale_data.order_date,
                    'product_uom_qty': shop_sale_data.sale_qty,
                    'product_uom': shop_sale_data.product_id.uom_id.id,
                    'lot_ids': [[6, False, []]],
                }

                stock_picking_vals = {
                    'is_locked': True,
                    'immediate_transfer': True,
                    'priority': '0',
                    'partner_id': False,
                    'picking_type_id': picking_type_id.id,
                    'location_id': location_id.id,
                    'location_dest_id': customers_location.id,
                    'scheduled_date': shop_sale_data.order_date,
                    'origin': False,
                    'owner_id': False,
                    'package_level_ids_details': [],
                    'move_ids_without_package': [[0, 0, stock_move_vals]],
                    'package_level_ids': [],
                    'carrier_id': False,
                    'carrier_tracking_ref': False,
                    'move_type': 'direct',
                    'user_id': 2,
                    'company_id': shop_sale_data.company_id.id,
                    'note': False,
                    'message_follower_ids': [],
                    'activity_ids': [],
                    'message_ids': [],
                    'name': picking_name,
                    # 'date': shop_sale_data.order_date,
                    # 'state': 'confirmed',
                }
                stock_picking = self.env['stock.picking'].create(stock_picking_vals)

                # stock_picking.action_assign()
                for stock_move in stock_picking.mapped('move_lines'):
                    stock_move._set_quantity_done(stock_move.product_uom_qty)

                stock_picking._action_done()

                # 回写调拨日期为订单日期
                stock_picking.write({'date': shop_sale_data.order_date})
                stock_picking.mapped('move_lines').write({'date': shop_sale_data.order_date})
                stock_picking.mapped('move_line_ids').write({'date': shop_sale_data.order_date})

                # 设置出货对应的move
                shop_sale_data.sale_stock_move_id = stock_picking.mapped('move_lines')[0]

            if shop_sale_data.return_qty != 0:
                picking_type_id = warehouse_id.in_type_id

                picking_name = 'Web Return: %s' %picking_type_id.sequence_id.next_by_id()

                stock_move_vals = {
                    'company_id': shop_sale_data.company_id.id,
                    'name': shop_sale_data.product_id.name_get(),
                    'state': 'draft',
                    'picking_type_id': picking_type_id,
                    'location_id': customers_location.id,
                    'location_dest_id': location_id.id,
                    'additional': False,
                    'product_id': shop_sale_data.product_id.id,
                    'description_picking': shop_sale_data.product_id.name,
                    'date': shop_sale_data.order_date,
                    'product_uom_qty': shop_sale_data.return_qty,
                    'product_uom': shop_sale_data.product_id.uom_id.id,
                    'lot_ids': [[6, False, []]],
                }

                stock_picking_vals = {
                    'is_locked': True,
                    'immediate_transfer': True,
                    'priority': '0',
                    'partner_id': False,
                    'picking_type_id': picking_type_id.id,
                    'location_id': customers_location.id,
                    'location_dest_id': location_id.id,
                    'scheduled_date': shop_sale_data.order_date,
                    'origin': False,
                    'owner_id': False,
                    'package_level_ids_details': [],
                    'move_ids_without_package': [[0, 0, stock_move_vals]],
                    'package_level_ids': [],
                    'carrier_id': False,
                    'carrier_tracking_ref': False,
                    'move_type': 'direct',
                    'user_id': 2,
                    'company_id': shop_sale_data.company_id.id,
                    'note': False,
                    'message_follower_ids': [],
                    'activity_ids': [],
                    'message_ids': [],
                    'name': picking_name,
                    # 'date': shop_sale_data.order_date,
                    # 'state': 'confirmed',
                }
                stock_picking = self.env['stock.picking'].create(stock_picking_vals)

                # stock_picking.action_assign()

                for stock_move in stock_picking.mapped('move_lines'):
                    stock_move._set_quantity_done(stock_move.product_uom_qty)

                stock_picking._action_done()

                # 回写调拨日期为订单日期
                stock_picking.write({'date': shop_sale_data.order_date})
                stock_picking.mapped('move_lines').write({'date': shop_sale_data.order_date})
                stock_picking.mapped('move_line_ids').write({'date': shop_sale_data.order_date})

                # 设置退货对应的move
                shop_sale_data.return_stock_move_id = stock_picking.mapped('move_lines')[0]

            if shop_sale_data.scrap_qty != 0:
                picking_type_id = warehouse_id.int_type_id

                picking_name = 'Web Scrap: %s' %picking_type_id.sequence_id.next_by_id()

                stock_move_vals = {
                    'company_id': shop_sale_data.company_id.id,
                    'name': shop_sale_data.product_id.name_get(),
                    'state': 'draft',
                    'picking_type_id': picking_type_id,
                    'location_id': location_id.id,
                    'location_dest_id': scrap_location_id,
                    'additional': False,
                    'product_id': shop_sale_data.product_id.id,
                    'description_picking': shop_sale_data.product_id.name,
                    'date': shop_sale_data.order_date,
                    'product_uom_qty': shop_sale_data.scrap_qty,
                    'product_uom': shop_sale_data.product_id.uom_id.id,
                    'lot_ids': [[6, False, []]],
                }

                stock_picking_vals = {
                    'is_locked': True,
                    'immediate_transfer': True,
                    'priority': '0',
                    'partner_id': False,
                    'picking_type_id': picking_type_id.id,
                    'location_id': location_id.id,
                    'location_dest_id': scrap_location_id,
                    'scheduled_date': shop_sale_data.order_date,
                    'origin': False,
                    'owner_id': False,
                    'package_level_ids_details': [],
                    'move_ids_without_package': [[0, 0, stock_move_vals]],
                    'package_level_ids': [],
                    'carrier_id': False,
                    'carrier_tracking_ref': False,
                    'move_type': 'direct',
                    'user_id': 2,
                    'company_id': shop_sale_data.company_id.id,
                    'note': False,
                    'message_follower_ids': [],
                    'activity_ids': [],
                    'message_ids': [],
                    'name': picking_name,
                    # 'date': shop_sale_data.order_date,
                    # 'state': 'confirmed',
                }
                stock_picking = self.env['stock.picking'].create(stock_picking_vals)

                # stock_move = self.env['stock.move'].create(stock_move_vals)

                # stock_picking.action_assign()
                for stock_move in stock_picking.mapped('move_lines'):
                    stock_move._set_quantity_done(stock_move.product_uom_qty)

                stock_picking._action_done()

                # 回写调拨日期为订单日期
                stock_picking.write({'date': shop_sale_data.order_date})
                stock_picking.mapped('move_lines').write({'date': shop_sale_data.order_date})
                stock_picking.mapped('move_line_ids').write({'date': shop_sale_data.order_date})

                # 设置出货对应的move
                shop_sale_data.scrap_stock_move_id = stock_picking.mapped('move_lines')[0]


    def _generate_stock_moves_bak(self, shop_sale_data_list):
        """ Generate a stock move for each product of a sale order. """

        customers_location = self.env.ref('stock.stock_location_customers')
        scrap_location_id = self.env['stock.scrap']._get_default_scrap_location_id()

        for shop_sale_data in shop_sale_data_list:
            if shop_sale_data.state != "ok":
                continue

            warehouse_id = shop_sale_data.shop_id.default_warehouse_id
            location_id = warehouse_id.lot_stock_id

            if shop_sale_data.sale_qty != 0:
                picking_type_id = warehouse_id.out_type_id

                stock_move_vals = {
                    'name': _('Web Sale: %s', picking_type_id.sequence_id.next_by_id()),
                    'company_id': shop_sale_data.company_id.id,
                    'product_id': shop_sale_data.product_id.id,
                    'product_uom_qty': shop_sale_data.sale_qty,
                    'product_uom': shop_sale_data.product_id.uom_id.id,
                    'location_id': location_id.id,
                    'location_dest_id': customers_location.id,
                    'date': shop_sale_data.order_date,
                    'picking_type_id': picking_type_id.id,
                    'state': 'confirmed',
                }
                stock_move = self.env['stock.move'].create(stock_move_vals)

                stock_move._action_assign()
                stock_move._set_quantity_done(shop_sale_data.sale_qty)
                stock_move._action_done()
                stock_move.write({'date': shop_sale_data.order_date})
                stock_move.move_line_ids.write({'date': shop_sale_data.order_date})
                shop_sale_data.sale_stock_move_id = stock_move

            if shop_sale_data.return_qty != 0:
                picking_type_id = warehouse_id.in_type_id
                stock_move = self.env['stock.move'].create({
                    'name': _('Web Return: %s', picking_type_id.sequence_id.next_by_id()),
                    'company_id': shop_sale_data.company_id.id,
                    'product_id': shop_sale_data.product_id.id,
                    'product_uom_qty': shop_sale_data.return_qty,
                    'product_uom': shop_sale_data.product_id.uom_id.id,
                    'location_id': customers_location.id,
                    'location_dest_id': location_id.id,
                    'date': shop_sale_data.order_date,
                    'picking_type_id': picking_type_id.id,
                    'state': 'confirmed',
                })
                stock_move._action_assign()
                stock_move._set_quantity_done(shop_sale_data.return_qty)
                stock_move._action_done()
                stock_move.write({'date': shop_sale_data.order_date})
                stock_move.move_line_ids.write({'date': shop_sale_data.order_date})
                shop_sale_data.return_stock_move_id = stock_move

            if shop_sale_data.scrap_qty != 0:
                picking_type_id = warehouse_id.int_type_id
                stock_move = self.env['stock.move'].create({
                    'name': _('Web Scrap: %s', picking_type_id.sequence_id.next_by_id()),
                    'company_id': shop_sale_data.company_id.id,
                    'product_id': shop_sale_data.product_id.id,
                    'product_uom_qty': shop_sale_data.scrap_qty,
                    'product_uom': shop_sale_data.product_id.uom_id.id,
                    'location_id': location_id.id,
                    'location_dest_id': scrap_location_id,
                    'date': shop_sale_data.order_date,
                    'picking_type_id': picking_type_id.id,
                    'state': 'confirmed',
                })
                stock_move._action_assign()
                stock_move._set_quantity_done(shop_sale_data.scrap_qty)
                stock_move._action_done()
                stock_move.write({'date': shop_sale_data.order_date})
                stock_move.move_line_ids.write({'date': shop_sale_data.order_date})
                shop_sale_data.scrap_stock_move_id = stock_move

    def _generate_reverse_stock_moves(self, shop_sale_data_list):
        """删除订单时，做对应入出库的回冲操作"""

        customers_location = self.env.ref('stock.stock_location_customers')
        scrap_location_id = self.env['stock.scrap']._get_default_scrap_location_id()

        for shop_sale_data in shop_sale_data_list:
            if shop_sale_data.state != "ok":
                continue

            warehouse_id = shop_sale_data.shop_id.default_warehouse_id
            location_id = warehouse_id.lot_stock_id

            if shop_sale_data.sale_qty != 0 and shop_sale_data.sale_stock_move_id.name:
                stock_move_vals = {
                    'name': _("%s / Reverse", shop_sale_data.sale_stock_move_id.name),
                    'company_id': shop_sale_data.company_id.id,
                    'product_id': shop_sale_data.product_id.id,
                    'product_uom_qty': shop_sale_data.sale_qty,
                    'product_uom': shop_sale_data.product_id.uom_id.id,
                    'location_id': customers_location.id,
                    'location_dest_id': location_id.id,
                    'date': shop_sale_data.order_date,
                    'state': 'confirmed',
                }
                stock_move = self.env['stock.move'].create(stock_move_vals)
                stock_move._action_assign()
                stock_move._set_quantity_done(shop_sale_data.sale_qty)
                stock_move._action_done()
                stock_move.write({'date': shop_sale_data.order_date})
                stock_move.move_line_ids.write({'date': shop_sale_data.order_date})

            if shop_sale_data.return_qty != 0 and shop_sale_data.return_stock_move_id.name:
                stock_move = self.env['stock.move'].create({
                    'name': _("%s / Reverse", shop_sale_data.return_stock_move_id.name),
                    'company_id': shop_sale_data.company_id.id,
                    'product_id': shop_sale_data.product_id.id,
                    'product_uom_qty': shop_sale_data.return_qty,
                    'product_uom': shop_sale_data.product_id.uom_id.id,
                    'location_id': location_id.id,
                    'location_dest_id': customers_location.id,
                    'date': shop_sale_data.order_date,
                    'state': 'confirmed',
                })
                stock_move._action_assign()
                stock_move._set_quantity_done(shop_sale_data.return_qty)
                stock_move._action_done()
                stock_move.write({'date': shop_sale_data.order_date})
                stock_move.move_line_ids.write({'date': shop_sale_data.order_date})

            if shop_sale_data.scrap_qty != 0 and shop_sale_data.scrap_stock_move_id.name:
                stock_move = self.env['stock.move'].create({
                    'name': _("%s / Reverse", shop_sale_data.scrap_stock_move_id.name),
                    'company_id': shop_sale_data.company_id.id,
                    'product_id': shop_sale_data.product_id.id,
                    'product_uom_qty': shop_sale_data.scrap_qty,
                    'product_uom': shop_sale_data.product_id.uom_id.id,
                    'location_id': scrap_location_id,
                    'location_dest_id': location_id.id,
                    'date': shop_sale_data.order_date,
                    'state': 'confirmed',
                })
                stock_move._action_assign()
                stock_move._set_quantity_done(shop_sale_data.scrap_qty)
                stock_move._action_done()
                stock_move.write({'date': shop_sale_data.order_date})
                stock_move.move_line_ids.write({'date': shop_sale_data.order_date})

