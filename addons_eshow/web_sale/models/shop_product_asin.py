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


class ShopProductAsin(models.Model):
    _name = "web.sale.shop.product.asin"
    _description = "Shop Product ASIN"
    _order = "shop_name, parent_asin, product_asin"
    _rec_name = "product_asin"
    _check_company_auto = True

    shop_id = fields.Many2one(
        comodel_name="web.sale.shop",
        string="Web Shop",
        store=True,
        readonly=False,
        domain="[]",
        index=True,
        check_company = True
    )

    company_id = fields.Many2one(
        comodel_name="res.company",
        related="shop_id.company_id",
        string='Company', store=True, readonly=True, index=True)

    shop_name = fields.Char(
        related="shop_id.name",
        string="Web Shop Name",
        store=True,
        index=True,
    )

    product_asin = fields.Char(
        string="ASIN",
        index=True,
    )

    shop_product_name = fields.Char(
        string="Product Name In Shop", index=True
    )

    parent_asin = fields.Char(
        string="Parent ASIN",
        index=True,
    )

    currency_id = fields.Many2one("res.currency", string="Currency")

    listing_update_time = fields.Datetime("Listing Update Time")

    seller_rank = fields.Integer("Seller Rank")

    seller_rank_category = fields.Char("Category")

    review_num = fields.Integer("Number of reviews")

    review_star = fields.Float("Stars")

    description = fields.Text(string="Description")

    active = fields.Boolean(default=True)

    shop_product_ids = fields.One2many("web.sale.shop.product", "product_asin_id", string="Shop Product SKUs",
                                       index=True, check_company=True)

    seller_skus = fields.Char("Seller SKUs", compute="_compute_seller_skus", store=True, index=True)

    _sql_constraints = [
        ('shop_product_asin_uniq1', 'unique(shop_id, product_asin)', 'Product Asin in one shop must be unique'),
    ]



    @api.depends("shop_product_ids")
    def _compute_seller_skus(self):
        for records in self:
            seller_sku_list = records.shop_product_ids.mapped("seller_sku")
            records.seller_skus = ",".join(seller_sku_list)

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None):
        args = args or []
        if operator == 'ilike' and not (name or '').strip():
            domain = [("shop_product_name", "ilike", name),
                      "|", ("product_asin", "ilike", name),
                      "|", ("parent_asin", "ilike", name),
                      "|", ("shop_id.name", "ilike", name),
                      ]
        else:
            domain = [("product_asin", "=", name),
                      ]
        return self._search(expression.AND([domain, args]), limit=limit, access_rights_uid=name_get_uid)

    @api.model
    def create_or_update(self, vals):
        if "id" in vals:
            shop_product_asin = self.browse(vals["id"])
            shop_product_asin.write(vals)
        elif "product_asin" in vals and "shop_id" in vals:
            shop_product_asin = self.search([("shop_id", "=", vals["shop_id"]),
                                             ("product_asin", "=", vals["product_asin"])], limit=1)
            if shop_product_asin:
                shop_product_asin.write(vals)
            else:
                shop_product_asin = self.create(vals)
        else:
            return False
        return shop_product_asin

