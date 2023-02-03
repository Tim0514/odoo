# Copyright 2020-2022 Max Share Technologies
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)

from odoo import _, api, fields, models, exceptions
from .lingxing_connector import LingxingConnector as Connector

import logging
_logger = logging.getLogger(__name__)


class Shop(models.Model):
    _inherit = "web.sale.shop"

    lingxing_shop_id = fields.Integer(string="Ling Xing Shop ID",)
    lingxing_shop_name = fields.Char(string="Ling Xing Shop Name",)

    def _prepare_shop_value(self, lingxing_shop_id, lingxing_shop_name, marketplace_id, merchant_id):
        data = {
            "name": lingxing_shop_name,
            "lingxing_shop_id": lingxing_shop_id,
            "lingxing_shop_name": lingxing_shop_name,
            "marketplace_id": marketplace_id,
            "merchant_id": merchant_id,
        }
        return data

    def action_import_web_shops(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "import_web_shops")])
        log_book = connector.do_sync_action()

        return {
            "type": "ir.actions.act_window",
            "res_model": "eshow.log.book",
            "res_id": log_book.id,
            "view_mode": "form,tree",
            "view_id": False,
            "domain": [],
            "context": {},
        }
