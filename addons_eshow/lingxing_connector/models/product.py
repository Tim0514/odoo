# Copyright 2018-2019 ForgeFlow, S.L.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)

from odoo import _, api, fields, models

class Product(models.Model):
    _inherit = "product.product"

    def action_export_products(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "export_local_products")])
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
