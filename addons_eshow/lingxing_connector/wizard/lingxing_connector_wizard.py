# Copyright 2018-2019 ForgeFlow, S.L.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class LingxingConnectorWizard(models.TransientModel):
    _name = "connector.lingxing.wizard"
    _description = "Lingxing Connector Actions"

    start_time = fields.Datetime("Start Time")

    end_time = fields.Datetime("End Time")

    def action_import_web_shops(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "import_web_shops")])
        log_book = connector.do_sync_action(self.start_time, self.end_time)

        return {
            "type": "ir.actions.act_window",
            "res_model": "eshow.log.book",
            "res_id": log_book.id,
            "view_mode": "form,tree",
            "view_id": False,
            "domain": [],
            "context": {},
        }

    def action_export_products(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "export_local_products")])
        log_book = connector.do_sync_action(self.start_time, self.end_time)

        return {
            "type": "ir.actions.act_window",
            "res_model": "eshow.log.book",
            "res_id": log_book.id,
            "view_mode": "form,tree",
            "view_id": False,
            "domain": [],
            "context": {},
        }

    def action_import_shop_products(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "import_shop_products")])
        log_book = connector.do_sync_action(self.start_time, self.end_time)

        return {
            "type": "ir.actions.act_window",
            "res_model": "eshow.log.book",
            "res_id": log_book.id,
            "view_mode": "form,tree",
            "view_id": False,
            "domain": [],
            "context": {},
        }

    def action_import_shop_product_pair_states(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "import_shop_product_pair_states")])
        log_book = connector.do_sync_action(self.start_time, self.end_time)

        return {
            "type": "ir.actions.act_window",
            "res_model": "eshow.log.book",
            "res_id": log_book.id,
            "view_mode": "form,tree",
            "view_id": False,
            "domain": [],
            "context": {},
        }

    def action_import_product_weekly_stat(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "import_product_weekly_stat")])
        log_book = connector.do_sync_action(self.start_time, self.end_time)

        return {
            "type": "ir.actions.act_window",
            "res_model": "eshow.log.book",
            "res_id": log_book.id,
            "view_mode": "form,tree",
            "view_id": False,
            "domain": [],
            "context": {},
        }

    def action_import_product_monthly_stat(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "import_product_monthly_stat")])
        log_book = connector.do_sync_action(self.start_time, self.end_time)

        return {
            "type": "ir.actions.act_window",
            "res_model": "eshow.log.book",
            "res_id": log_book.id,
            "view_mode": "form,tree",
            "view_id": False,
            "domain": [],
            "context": {},
        }

    def action_import_shop_inventory(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "import_shop_inventory")])
        log_book = connector.do_sync_action(self.start_time, self.end_time)

        return {
            "type": "ir.actions.act_window",
            "res_model": "eshow.log.book",
            "res_id": log_book.id,
            "view_mode": "form,tree",
            "view_id": False,
            "domain": [],
            "context": {},
        }

    def action_import_shop_warehouse(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "import_shop_warehouse")])
        log_book = connector.do_sync_action(self.start_time, self.end_time)

        return {
            "type": "ir.actions.act_window",
            "res_model": "eshow.log.book",
            "res_id": log_book.id,
            "view_mode": "form,tree",
            "view_id": False,
            "domain": [],
            "context": {},
        }

