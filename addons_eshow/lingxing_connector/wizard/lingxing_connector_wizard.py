# Copyright 2018-2019 ForgeFlow, S.L.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class LingxingConnectorWizard(models.TransientModel):
    _name = "connector.lingxing.wizard"
    _description = "Lingxing Connector Actions"

    start_time = fields.Date("Start Date")

    end_time = fields.Date("End Date")

    def _get_action_log_book_view(self, log_books):
        if len(log_books) > 1:
            return {
                "type": "ir.actions.act_window",
                "res_model": "eshow.log.book",
                "view_mode": "tree,form",
                "view_id": False,
                "name": _("Log Books"),
                "domain": [("id", "in", log_books.ids)],
                "context": {},
            }
        else:
            return {
                "type": "ir.actions.act_window",
                "res_model": "eshow.log.book",
                "res_id": log_books.id,
                "view_mode": "form,tree",
                "view_id": False,
                "domain": [],
                "context": {},
            }

    def action_import_multiplatform_shops(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "import_multiplatform_shops")])
        log_book = connector.do_sync_action(self.start_time, self.end_time)

        return self._get_action_log_book_view(log_book)

    def action_import_amazon_shops(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "import_amazon_shops")])
        log_book = connector.do_sync_action(self.start_time, self.end_time)

        return self._get_action_log_book_view(log_book)

    def action_export_products(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "export_local_products")])
        log_book = connector.do_sync_action(self.start_time, self.end_time)

        return self._get_action_log_book_view(log_book)

    def action_import_amazon_products(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "import_amazon_products")])
        log_book = connector.do_sync_action(self.start_time, self.end_time)

        return self._get_action_log_book_view(log_book)

    def action_import_amazon_product_pair_states(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "import_amazon_product_pair_states")])
        log_book = connector.do_sync_action(self.start_time, self.end_time)

        return self._get_action_log_book_view(log_book)

    def action_import_multiplatform_products(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "import_multiplatform_products")])
        log_book = connector.do_sync_action(self.start_time, self.end_time)

        return self._get_action_log_book_view(log_book)

    def action_import_product_weekly_stat(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "import_product_weekly_stat")])
        log_book = connector.do_sync_action(self.start_time, self.end_time)

        return self._get_action_log_book_view(log_book)

    def action_import_product_monthly_stat(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "import_product_monthly_stat")])
        log_book = connector.do_sync_action(self.start_time, self.end_time)

        return self._get_action_log_book_view(log_book)

    def action_import_shop_inventory(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "import_shop_inventory")])
        log_book = connector.do_sync_action(self.start_time, self.end_time)

        return self._get_action_log_book_view(log_book)

    def action_import_shop_warehouse(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "import_shop_warehouse")])
        log_book = connector.do_sync_action(self.start_time, self.end_time)

        return self._get_action_log_book_view(log_book)

    def action_import_draft_fba_shipments(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "import_fba_shipments")])
        log_book = connector.do_sync_action(self.start_time, self.end_time, operation="get_draft_shipments")

        return self._get_action_log_book_view(log_book)

    def action_import_shipped_fba_shipments(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "import_fba_shipments")])
        log_book = connector.do_sync_action(self.start_time, self.end_time, operation="get_shipped_shipments")

        return self._get_action_log_book_view(log_book)

    def action_import_scraped_fba_shipments(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "import_fba_shipments")])
        log_book = connector.do_sync_action(self.start_time, self.end_time, operation="get_scraped_shipments")
        return self._get_action_log_book_view(log_book)

    def action_export_lingxing_stock_picking_in(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "export_lingxing_stock_picking_in")])
        log_book = connector.do_sync_action(self.start_time, self.end_time)

        return self._get_action_log_book_view(log_book)

    def action_export_lingxing_stock_picking_out(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "export_lingxing_stock_picking_out")])
        log_book = connector.do_sync_action(self.start_time, self.end_time)

        return self._get_action_log_book_view(log_book)

    def action_sync_draft_fba_shipments(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "import_fba_shipments")])
        log_book1 = connector.do_sync_action(self.start_time, self.end_time, operation="get_draft_shipments")

        connector = self.env["connector.lingxing"].search([("name", "=", "export_lingxing_stock_picking_in")])
        log_book2 = connector.do_sync_action(self.start_time, self.end_time)

        connector = self.env["connector.lingxing"].search([("name", "=", "export_lingxing_stock_picking_out")])
        log_book3 = connector.do_sync_action(self.start_time, self.end_time)

        log_books = self.env["eshow.log.book"].concat(log_book1, log_book2, log_book3)

        return self._get_action_log_book_view(log_books)

    def action_import_fba_shipment_detail(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "import_fba_shipment_detail")])
        log_book = connector.do_sync_action(self.start_time, self.end_time)
        return self._get_action_log_book_view(log_book)

    def action_import_amazon_orders(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "import_amazon_orders")])
        log_book = connector.do_sync_action(self.start_time, self.end_time)
        return self._get_action_log_book_view(log_book)

    def action_import_multiplatform_orders(self):
        connector = self.env["connector.lingxing"].search([("name", "=", "import_multiplatform_orders")])
        log_book = connector.do_sync_action(self.start_time, self.end_time)
        return self._get_action_log_book_view(log_book)
