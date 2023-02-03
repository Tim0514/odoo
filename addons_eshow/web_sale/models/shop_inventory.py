# Copyright 2018-2019 ForgeFlow, S.L.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression


class ShopInventory(models.Model):
    _name = "web.sale.shop.inventory"
    _description = "Shop Product Inventory"
    _order = "shop_name, product_default_code, seller_sku"

    shop_product_id = fields.Many2one(comodel_name="web.sale.shop.product", string="Shop Product", store=True, )

    shop_id = fields.Many2one(related="shop_product_id.shop_id", string='Web Shop', store=True, readonly=True)

    company_id = fields.Many2one(
        comodel_name="res.company",
        related="shop_id.company_id",
        string='Company', store=True, readonly=True)

    shop_name = fields.Char(related="shop_id.name", string='Web Shop', store=True)

    shop_warehouse_id = fields.Many2one("web.sale.warehouse", string='Web Shop Warehouse')

    product_id = fields.Many2one(
        related="shop_product_id.product_id", string="Product", store=True, )

    product_default_code = fields.Char(
        related="product_id.default_code", string="Default Code", store=True, readonly=True, )

    product_name = fields.Char(
        related="product_id.name", string="Product Name", store=True, readonly=True, )

    seller_sku = fields.Char(
        related="shop_product_id.seller_sku", string="MSKU", index=True, store=True)

    product_asin_id = fields.Many2one(
        related="shop_product_id.product_asin_id", string="ASIN", store=True)

    inventory_date = fields.Datetime(string="Inventory Date")

    is_latest_inventory = fields.Boolean(string="Is Latest Inventory", default=False, index=True)

    # 过去30天中，如果可售数量, 待调仓数量, 调仓中, 入库中 四个数据加起来，出现过0 则为True
    is_out_of_stock_occurred = fields.Boolean(string="Is out of stock occurred", default=False,
                                              help="Is out of stock occurred in last 30 days")

    # 可售数量
    afn_fulfillable_quantity = fields.Float("Available Qty")

    # 待调仓数量
    reserved_fc_transfers = fields.Float("Waiting Transfer Qty")

    # 调仓中
    reserved_fc_processing = fields.Float("Transfer Processing Qty")

    # 待发货
    reserved_customerorders = fields.Float("Waiting Delivery Qty")

    # 总可售库存
    total_fulfillable_quantity = fields.Float("Total Available Qty")

    # 在途
    afn_inbound_shipped_quantity = fields.Float("Inbound Shipped Qty")

    # 不可售
    afn_unsellable_quantity = fields.Float("Unsellable Qty")

    # 计划入库
    afn_inbound_working_quantity = fields.Float("Inbound Working Qty")

    # 入库中
    afn_inbound_receiving_quantity = fields.Float("Inbound Receiving Qty")

    # 实际在途
    afn_erp_real_shipped_quantity = fields.Float("Actually Shipped Qty")

    # 调查中
    afn_researching_quantity = fields.Float("Investigating Qty")

    afn_fulfillable_quantity_multi = fields.Char("Shared Inventory for Multi Countries")

    sellable_quantity = fields.Float("Sellable Quantity", compute="_compute_sellable_quantity", store=True)

    @api.depends("afn_fulfillable_quantity", "reserved_fc_transfers", "reserved_fc_processing", "afn_inbound_receiving_quantity")
    def _compute_sellable_quantity(self):
        for shop_inventory in self:
            shop_inventory.sellable_quantity = shop_inventory.get_sellable_quantity()

    def get_sellable_quantity(self):
        self.ensure_one()
        sellable_quantity = self.afn_fulfillable_quantity + self.reserved_fc_transfers \
            + self.reserved_fc_processing + self.afn_inbound_receiving_quantity
        return sellable_quantity

    def get_shipped_quantity(self):
        self.ensure_one()
        shipped_quantity = self.afn_erp_real_shipped_quantity
        return shipped_quantity
