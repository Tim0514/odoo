# Copyright 2020-2022 Max Share Technologies
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class Shop(models.Model):
    _name = "web.sale.shop"
    _description = "Shop"
    _order = "name"
    _check_company_auto = True

    @api.model
    def _company_get(self):
        return self.env["res.company"].browse(self.env.company.id)

    company_id = fields.Many2one(comodel_name="res.company", string="Company", index=True)

    name = fields.Char(
        string="Shop Name",
        index=True,
    )

    # 店铺编码
    shop_code = fields.Char(string='Shop Code', index=True)

    # 所属市场
    marketplace_id = fields.Many2one(comodel_name="web.sale.marketplace", string='Marketplace')

    # 平台商家ID
    merchant_id = fields.Char(string='Shop Merchant ID')

    auth_token = fields.Char(string='Authorization Token')

    access_key = fields.Char(string='Access Key')

    secret_key = fields.Char(string="Secret Key")

    # 允许同步数据
    enable_exchange_data = fields.Boolean("Enable Exchange Data", default=False)

    # 允许参与发货计划编制
    enable_shipping_schedule = fields.Boolean("Enable Shipping Schedule", default=False)

    default_warehouse_id = fields.Many2one("stock.warehouse", string='Web Shop Default Warehouse')

    partner_id = fields.Many2one("res.partner", string="Related Partner", check_company=True)

    shop_warehouse_ids = fields.One2many("web.sale.warehouse", inverse_name="default_shop_id", string='Web Shop Warehouse', check_company=True)

    default_shipping_method_id = fields.Many2one("web.sale.shipping.method", string="Default Shipping Method")

    default_shipping_schedule_group_id = fields.Many2one("web.sale.shipping.schedule.group", string="Default Shipping Schedule Group", check_company=True)

    timezone = fields.Char(related="marketplace_id.timezone", string="Time Zone")

    currency_id = fields.Many2one("res.currency", string="Currency", compute="_compute_currency_id", inverse="_set_currency_id")

    @api.depends("marketplace_id", "marketplace_id.country_id")
    def _compute_currency_id(self):
        for record in self:
            if not record.currency_id:
                record.currency_id = record.marketplace_id.country_id.currency_id

    def _set_currency_id(self):
        pass

    def get_currency_id(self):
        self.ensure_one()
        if self.currency_id:
            return self.currency_id
        else:
            return self.marketplace_id.country_id.currency_id

    # @api.onchange("default_shipping_method_id")
    # def _onchange_default_shipping_method(self):
    #     for shop in self:
    #         if shop.partner_id:
    #             shop.partner_id.default_shipping_method_id = shop.default_shipping_method_id
    #         else:
    #             raise UserError(_("You need to set partner value for the shop before setting the default shipping method"))

    def do_create_default_shipping_schedule_group_id(self):
        self._create_default_shipping_schedule_group_id()

    def _create_default_shipping_schedule_group_id(self):
        for shop in self:
            if shop.company_id and shop.enable_shipping_schedule and not shop.default_shipping_schedule_group_id:
                shipping_schedule_group_vals = {
                    'name': "%s-默认组" %shop.name,
                    'company_id': shop.company_id.id,
                    'shop_id': shop.id,
                    'is_default_group': True,
                    'sale_qty_compute_method': 'by_product',
                    'state': 'draft',
                }
                shipping_schedule_group = self.env['web.sale.shipping.schedule.group'].create(shipping_schedule_group_vals)
                shop.default_shipping_schedule_group_id = shipping_schedule_group

    def create(self, vals_list):
        shop = super(Shop, self).create(vals_list)
        if shop.partner_id and shop.default_shipping_method_id:
            shop.partner_id.default_shipping_method_id = shop.default_shipping_method_id
        shop._create_default_shipping_schedule_group_id()
        return shop

    def write(self, vals):
        super(Shop, self).write(vals)
        if "partner_id" in vals.keys() or "default_shipping_method_id" in vals.keys():
            if self.partner_id and self.default_shipping_method_id:
                self.partner_id.default_shipping_method_id = self.default_shipping_method_id
        self._create_default_shipping_schedule_group_id()





