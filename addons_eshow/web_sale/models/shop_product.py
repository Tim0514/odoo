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
    _order = "shop_id, product_id"

    @api.model
    def _company_get(self):
        return self.env["res.company"].browse(self.env.company.id)


    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        default=_company_get,
    )

    shop_id = fields.Many2one(
        comodel_name="res.partner",
        string="Web Shop",
        store=True,
        readonly=False,
        domain="[('is_web_shop', '=', True)]",
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
    )

    product_name = fields.Char(
        related="product_id.name",
        string="Product Name",
        readonly=True,
    )

    product_sku = fields.Char(
        string="Product SKU",
        required=True,
        index=True,
    )

    product_asin = fields.Char(
        string="Product ASIN",
        index=True,
    )

    parent_asin = fields.Char(
        string="Parent ASIN",
    )


    state = fields.Selection(
        selection=_STATES,
        string="Status",
        index=True,
        required=True,
        copy=True,
        default="normal",
    )

    salesperson_id = fields.Many2one(
        comodel_name='res.users', string='Salesperson', index=True, default=lambda self: self.env.user,
        )

    description = fields.Text(string="Description")

    mrp_production_schedule_id = fields.Many2one(
        comodel_name="mrp.production.schedule",
        string="Production Schedule",
    )

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
        # 导入变体数据是，可以根据"父物料编码: 属性名称: 属性值"的格式找到相应的属性值行
        args = args or []
        if operator == 'ilike' and not (name or '').strip():
            domain = [("shop_id.name", "ilike", name),
                      "|", ("shop_id.name", "ilike", name),
                      "|", ("product_id.name", "ilike", name),
                      "|", ("product_id.default_code", "ilike", name),
                      "|", ("product_sku", "ilike", name),
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
                              ("product_sku", "=", strlist[2]),
                              ]
                else:
                    return False
            else:
                return False
        return self._search(expression.AND([domain, args]), limit=limit, access_rights_uid=name_get_uid)
