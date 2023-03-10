# Copyright 2020-2022 Max Share Technologies
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)

from odoo import _, api, fields, models

_SHARE_TYPES = [
    ("none", "None"),
    ("na", "North America"),
    ("eu", "European Union"),
]


class Shop(models.Model):
    _name = "web.sale.warehouse"
    _description = "Shop Warehouse"
    _order = "name"
    _check_company_auto = True

    company_id = fields.Many2one(
        comodel_name="res.company", string="Company", related="default_shop_id.company_id", store=True, index=True,
    )

    name = fields.Char(
        string="Warehouse Name",
        index=True,
    )

    shop_ids = fields.Many2many("web.sale.shop", string="Shops", check_company=True)
    shop_names = fields.Char(string="Shops Supported", compute="_compute_shop_names")

    share_type = fields.Selection(
        selection=_SHARE_TYPES,
        string="Share Type",
        copy=True,
    )

    default_shop_id = fields.Many2one("web.sale.shop", string="Default Shop", check_company=True)

    # default_shop_id = fields.Many2one("web.sale.shop", string="Default Shop",
    #                                   compute="_compute_default_shop", inverse="_set_default_shop", save=True)

    @api.depends("shop_ids")
    def _compute_shop_names(self):
        for records in self:
            shop_name_list = records.shop_ids.mapped("name")
            records.shop_names = ",".join(shop_name_list)

    # @api.depends("shop_ids")
    # def _compute_default_shop(self):
    #     # 如果是多国仓库，如果有美国店铺，则这是仓库的默认店铺为美国店，如果有德国店铺，则默认为德国店，否则取第1个店铺。
    #     for record in self:
    #         if len(record.shop_ids) == 1:
    #             record.default_shop_id = record.shop_ids[0]
    #         elif len(record.shop_ids) > 1:
    #             if len(record.shop_ids.filtered(lambda r: r.name.endswith("US"))) >= 1:
    #                 record.default_shop_id = record.shop_ids.filtered(lambda r: r.name.endswith("US"))[0]
    #             elif len(record.shop_ids.filtered(lambda r: r.name.endswith("DE"))) >= 1:
    #                 record.default_shop_id = record.shop_ids.filtered(lambda r: r.name.endswith("DE"))[0]
    #             else:
    #                 record.default_shop_id = record.shop_ids[0]
    #
    # def _set_default_shop(self):
    #     for record in self:
    #         record.default_shop_id = record.default_shop_id

    # @api.depends("name")
    # def _compute_share_type(self):
    #     for record in self:
    #         if record.name and record.name.rfind("北美仓") == len(record.name) - 3:
    #             record.share_type = "na"
    #         elif record.name and record.name.rfind("欧洲仓") == len(record.name) - 3:
    #             record.share_type = "eu"
    #         else:
    #             record.share_type = "none"
    #
    # def _set_share_type(self):
    #     for record in self:
    #         record.share_type = record.share_type
