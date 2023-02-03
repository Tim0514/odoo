# Copyright 2018-2019 ForgeFlow, S.L.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression

_STATES = [
    ("new", "New"),
    ("normal", "Normal Sale"),
    ("clearance", "Clearance"),
    ("stop", "Stop Sale"),
]


class ShopProduct(models.Model):
    _name = "web.sale.shop.product"
    _description = "Shop Product"
    _order = "shop_name, product_default_code"
    _rec_name = "product_name"

    shop_id = fields.Many2one(
        comodel_name="web.sale.shop",
        string="Web Shop",
        store=True,
        readonly=True,
        domain="[]",
        index=True,
    )

    company_id = fields.Many2one(
        comodel_name="res.company",
        related="shop_id.company_id",
        string='Company', store=True, readonly=True)

    shop_name = fields.Char(
        related="shop_id.name",
        string="Web Shop Name",
        store=True,
        index=True,
    )

    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Product",
        index=True,
        domain="[('sale_ok', '=', True)]",
    )

    product_default_code = fields.Char(
        related="product_id.default_code",
        string="Default Code",
        readonly=True,
        store=True,
        index=True,
    )

    product_name = fields.Char(
        related="product_id.name",
        string="Product Name",
        readonly=True,
    )

    seller_sku = fields.Char(
        string="MSKU",
        required=True,
        index=True,
        readonly=True,
    )

    product_asin_id = fields.Many2one(
        "web.sale.shop.product.asin",
        string="ASIN",
        index=True,
        readonly=True,
    )

    product_listing_id = fields.Char(
        string="Listing Id",
        index=True,
        readonly=True,
    )

    product_fnsku = fields.Char(
        string="FNSKU",
        index=True,
        readonly=True,
    )

    parent_asin = fields.Char(
        string="Parent ASIN",
        index=True,
        readonly=True,
    )

    shop_product_name = fields.Char(
        string="Product Name In Shop",
        readonly=True,
    )

    is_deleted = fields.Boolean(string="Is Deleted", readonly=True)

    currency_id = fields.Many2one("res.currency", string="Currency", readonly=True)

    listing_update_time = fields.Datetime("Listing Update Time")

    pair_update_time = fields.Datetime("Pair Update Time")

    seller_rank = fields.Integer("Seller Rank")

    seller_rank_category = fields.Char("Category")

    review_num = fields.Integer("Number of reviews")

    review_star = fields.Float("Stars")

    fulfillment_channel_type = fields.Char("Fulfillment Channel")

    # 人工设置的产品状态(new, clearance, normal, stop)
    state = fields.Selection(
        selection=_STATES,
        string="Status",
        index=True,
        required=True,
        copy=True,
        default="normal",
    )

    # 同步下来的产品状态(normal, stop)
    shop_product_state = fields.Selection(
        selection=_STATES,
        string="Shop Product Status",
        index=True,
        required=True,
        copy=True,
        default="normal",
        readonly=True,
    )

    salesperson_id = fields.Many2one(
        comodel_name='res.users', string='Salesperson', index=True, default=lambda self: self.env.user,
    )

    is_web_sale_manager = fields.Boolean("Is Manager", store=False, compute='_compute_is_web_sale_manager')

    is_paired = fields.Boolean("Paired", store=True, compute='_compute_is_paired')

    description = fields.Text(string="Description")

    # 可售
    afn_fulfillable_quantity = fields.Float("Available Qty")

    # 待调仓
    reserved_fc_transfers = fields.Float("Waiting Transfer Qty")

    # 调仓中
    reserved_fc_processing = fields.Float("Transfer Processing Qty")

    # 待发货
    reserved_customerorders = fields.Float("Waiting Delivery Qty")

    # 入库
    afn_inbound_shipped_quantity = fields.Float("Inbound Shipped Qty")

    # 不可售
    afn_unsellable_quantity = fields.Float("Unsellable Qty")

    # 计划入库
    afn_inbound_working_quantity = fields.Float("Inbound Working Qty")

    # 入库中
    afn_inbound_receiving_quantity = fields.Float("Inbound Receiving Qty")

    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('seller_sku_uniq1', 'unique(shop_id, seller_sku)', 'Seller SKU in one shop must be unique'),
    ]

    def name_get(self):
        # Prefetch the fields used by the `name_get`, so `browse` doesn't fetch other fields
        self.browse(self.ids).read(['shop_id', 'product_default_code', 'product_name'])
        return [(shop_product.id, '%s: %s: %s' % (shop_product.shop_id.name, shop_product.product_default_code, shop_product.product_name))
                for shop_product in self]

    '''
        如果条件为ilike, 则从店铺名称，产品名称，物料编码，店铺SKU中查找
        
        如果条件为”=“
            输入的name格式为：
                店铺名称: 产品DefaultCode: 产品SKU
            进行精确查找，可用于数据导入
            产品DefaultCode和产品SKU可以二选一输入
    '''
    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None):
        args = args or []
        if operator == 'ilike' and (name or '').strip():
            domain = ["|", ("shop_id.name", "ilike", name),
                      "|", ("product_id.name", "ilike", name),
                      "|", ("product_id.default_code", "ilike", name),
                      "|", ("seller_sku", "ilike", name),
                      "|", ("product_asin_id.product_asin", "ilike", name),
                      ("parent_asin", "ilike", name),
                      ]
        else:
            strlist = str.split(name, ": ")
            if len(strlist) == 3:
                if not strlist[1].strip() == '':
                    domain = [("shop_id.name", "=", strlist[0]),
                              ("product_id.default_code", "=", strlist[1]),
                              ]
                elif not strlist[2].strip() == '':
                    domain = [("shop_id.name", "=", strlist[0]),
                              ("seller_sku", "=", strlist[2]),
                              ]
                else:
                    return False
            else:
                return False
        return self._search(expression.AND([domain, args]), limit=limit, access_rights_uid=name_get_uid)

    def _prepare_product_asin_vals(self, shop_product_vals):
        product_asin_vals = {
            "shop_id": shop_product_vals.get("shop_id"),
            "product_asin": shop_product_vals.get("product_asin"),
            "shop_product_name": shop_product_vals.get("shop_product_name"),
            "parent_asin": shop_product_vals.get("parent_asin"),
            "currency_id": shop_product_vals.get("currency_id"),
            "listing_update_time": shop_product_vals.get("listing_update_time"),
            "seller_rank": shop_product_vals.get("seller_rank"),
            "seller_rank_category": shop_product_vals.get("seller_rank_category"),
            "review_num": shop_product_vals.get("review_num"),
        }
        return product_asin_vals

    # @api.model_create_multi
    # def create(self, vals_list):
    #     product_asin_obj = self.env["web.sale.shop.product.asin"]
    #     for vals in vals_list:
    #         product_asin_vals = self._prepare_product_asin_vals(vals)
    #         product_asin = product_asin_obj.create_or_update(product_asin_vals)
    #         vals["product_asin_id"] = product_asin.id
    #         vals.pop("product_asin")
    #     templates = super(ShopProduct, self).create(vals_list)
    #
    #     return templates

    # def write(self, vals):
    #     # 更新
    #     product_asin_obj = self.env["web.sale.shop.product.asin"]
    #     product_asin_vals = self._prepare_product_asin_vals(vals)
    #     product_asin = product_asin_obj.create_or_update(product_asin_vals)
    #     vals["product_asin_id"] = product_asin.id
    #     vals.pop("product_asin")
    #     res = super(ShopProduct, self).write(vals)
    #     return res

    def unlink(self):
        product_asin_id = self.product_asin_id
        super(ShopProduct, self).unlink()
        if len(product_asin_id.shop_product_ids) == 0:
            product_asin_id.unlink()

    @api.depends('salesperson_id')
    def _compute_is_web_sale_manager(self):
        if self.env.user.has_group("web_sale.group_web_sale_manager"):
            self.is_web_sale_manager = True
        else:
            self.is_web_sale_manager = False

    @api.depends('product_id')
    def _compute_is_paired(self):
        for record in self:
            if record.product_id:
                record.is_paired = True
            else:
                record.is_paired = False
