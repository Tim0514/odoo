import logging

from odoo import models
from odoo.tools.translate import translate

from odoo.addons.report_xlsx_helper.report.report_xlsx_format import (
    FORMATS,
    XLS_HEADERS,
)

_logger = logging.getLogger(__name__)

IR_TRANSLATION_NAME = "shipping.schedule.list.xls"

class ShippingScheduleXlsx(models.AbstractModel):
    _name = "report.web_sale.shipping_schedule_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "XLSX report for shipping schedule."

    def _(self, src):
        lang = self.env.context.get("lang", "en_US")
        val = translate(self.env.cr, IR_TRANSLATION_NAME, "report", lang, src) or src
        return val

    def _get_objs_for_report(self, docids, data):
        """
        Returns objects for xlx report.  From WebUI these
        are either as docids taken from context.active_ids or
        in the case of wizard are in data.  Manual calls may rely
        on regular context, setting docids, or setting data.

        :param docids: list of integers, typically provided by
            qwebactionmanager for regular Models.
        :param data: dictionary of data, if present typically provided
            by qwebactionmanager for TransientModels.
        :param ids: list of integers, provided by overrides.
        :return: recordset of active model for ids.
        """
        if docids:
            ids = docids
        elif data and "context" in data:
            ids = data["context"].get("active_ids", [])
        else:
            ids = self.env.context.get("active_ids", [])
        shipping_schedule_groups = self.env["web.sale.shipping.schedule.group"].browse(ids)

        domain = [
            ("id", "in", shipping_schedule_groups.shipping_schedule_ids.ids)
        ]
        schedule_main = self.env["web.sale.shipping.schedule"].get_shipping_schedule_main_view_state(domain)
        return schedule_main


    def _get_ws_params(self, workbook, data, schedule_main):

        # XLSX Template
        col_specs = {
            "shop_name": {
                "header": {"value": self._("Shop Name")},
                "lines": {"value": self._render("schedule['shop_id'][1]")},
                "width": 16,
            },
            "seller_sku": {
                "header": {"value": self._("MSKU")},
                "lines": {"value": self._render("schedule['seller_sku']")},
                "width": 20,
            },
            "product_default_code": {
                "header": {"value": self._("Product Default Code")},
                "lines": {"value": self._render("schedule['product_default_code']")},
                "width": 20,
            },
            "product_name": {
                "header": {"value": self._("Product Name")},
                "lines": {
                    "value": self._render("schedule['product_name']"),
                },
                "width": 40,
            },
            "schedule_year": {
                "header": {"value": self._("Year")},
                "lines": {
                    "value": self._render("schedule['schedule_year']")
                },
                "width": 10,
            },
            "schedule_month": {
                "header": {"value": self._("Month")},
                "lines": {
                    "value": self._render("schedule['schedule_month']")
                },
                "width": 10,
            },
            "forecast_period_0": {
                "header": {
                    "value": self._render("schedule_main['dates'][0]"),
                    "format": FORMATS["format_theader_yellow_right"],
                },
                "lines": {
                    "value": self._render("schedule['forecast_ids'][0]['arriving_qty_confirmed'] - schedule['forecast_ids'][0]['arriving_qty_shipped']"),
                    "format": FORMATS["format_tcell_amount_right"],
                },
                "width": 10,
            },
            "forecast_period_1": {
                "header": {
                    "value": self._render("schedule_main['dates'][1]"),
                    "format": FORMATS["format_theader_yellow_right"],
                },
                "lines": {
                    "value": self._render("schedule['forecast_ids'][1]['arriving_qty_confirmed'] - schedule['forecast_ids'][1]['arriving_qty_shipped']"),
                    "format": FORMATS["format_tcell_amount_right"],
                },
                "width": 10,
            },
            "forecast_period_2": {
                "header": {
                    "value": self._render("schedule_main['dates'][2]"),
                    "format": FORMATS["format_theader_yellow_right"],
                },
                "lines": {
                    "value": self._render("schedule['forecast_ids'][2]['arriving_qty_confirmed'] - schedule['forecast_ids'][2]['arriving_qty_shipped']"),
                    "format": FORMATS["format_tcell_amount_right"],
                },
                "width": 10,
            },
            "forecast_period_3": {
                "header": {
                    "value": self._render("schedule_main['dates'][3]"),
                    "format": FORMATS["format_theader_yellow_right"],
                },
                "lines": {
                    "value": self._render("schedule['forecast_ids'][3]['arriving_qty_confirmed'] - schedule['forecast_ids'][3]['arriving_qty_shipped']"),
                    "format": FORMATS["format_tcell_amount_right"],
                },
                "width": 10,
            },
        }

        wanted_list = [
            "shop_name",
            "seller_sku",
            "product_default_code",
            "product_name",
            "schedule_year",
            "schedule_month",
            "forecast_period_0",
            "forecast_period_1",
            "forecast_period_2",
            "forecast_period_3",
        ]

        # col_specs.update(self.env["account.move.line"]._report_xlsx_template())
        # wanted_list = self.env["account.move.line"]._report_xlsx_fields()

        title = self._("Shipping Schedules")

        return [
            {
                "ws_name": title,
                "generate_ws_method": "_shipping_schedule_export",
                "title": title,
                "wanted_list": wanted_list,
                "col_specs": col_specs,
            }
        ]

    def _shipping_schedule_export(self, workbook, ws, ws_params, data, schedule_main):

        ws.set_landscape()
        ws.fit_to_pages(1, 0)
        ws.set_header(XLS_HEADERS["xls_headers"]["standard"])
        ws.set_footer(XLS_HEADERS["xls_footers"]["standard"])

        self._set_column_width(ws, ws_params)

        row_pos = 0
        row_pos = self._write_ws_title(ws, row_pos, ws_params)

        row_pos = self._write_line(
            ws,
            row_pos,
            ws_params,
            col_specs_section="header",
            render_space={"schedule_main": schedule_main},
            default_format=FORMATS["format_theader_yellow_left"],
        )

        ws.freeze_panes(row_pos, 0)

        wanted_list = ws_params["wanted_list"]

        for schedule in schedule_main["shipping_schedule_ids"]:
            row_pos = self._write_line(
                ws,
                row_pos,
                ws_params,
                col_specs_section="lines",
                render_space={"schedule": schedule},
                default_format=FORMATS["format_tcell_left"],
            )
