# Copyright 2020-2022 Max Share Technologies
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)
from collections import defaultdict

from dateutil.relativedelta import relativedelta

from .action_handler import ActionHandler, ActionHandlerTools
from datetime import datetime
from dateutil.parser import parse
from dateutil.relativedelta import *
from dateutil.rrule import *
from odoo.tools import date_utils
from odoo import _

class ImportFbaShipmentDetail(ActionHandler):

    def __init__(self, connector, log_book, start_time=None, end_time=None, operation="get_draft_shipments", **kwargs):
        super(ImportFbaShipmentDetail, self).__init__(connector, log_book, start_time, end_time, **kwargs)

        self._shipment_sn_cache = None

        self._picking_cache = defaultdict(dict)

        self._init_cache()

    def _init_cache(self):
        stock_picking_obj = self._connector.env["stock.picking"]
        domain = [
            ('move_document_type', '=', 'sale_out'),
            ('partner_id.is_web_shop', '=', True),
            ('lx_shipment_sn', '!=', False),
            # ("state", "=", "Done"),
            ("fba_shipment_state", "not in", ["closed", "cancelled", "delete"])
        ]
        stock_pickings = stock_picking_obj.search(domain, order="lx_shipment_sn")
        self._shipment_sn_cache = stock_pickings.mapped("lx_shipment_sn")
        for picking in stock_pickings:
            self._picking_cache.setdefault(picking.lx_shipment_sn, picking)

        # 请求参数数据的总数量，默认为负数
        self._request_total = len(self._shipment_sn_cache)

        self._request_offset = 0

        if self._request_offset < self._request_total:
            self._has_more_request_data = True
        else:
            self._has_more_request_data = False

    def prepare_req_body(self):
        if self._request_offset < self._request_total:
            req_body = {
                "shipment_sn": self._shipment_sn_cache[self._request_offset],
            }

            self._request_offset += 1

            if self._request_offset >= self._request_total:
                self._has_more_request_data = False

            return req_body

    def set_result(self, response_result):
        """
        重载本方法
        请求每次只返回一条数据
        :param response_result:
        :return:
        """
        self._response_result = response_result
        self._has_more_result_data = False

    def process_response_result(self):
        """
        self._response_result 有可能是ResponseResult，也有可能是List
        对于特定的Handler，需要对应相应的类型进行处理
        :return: 全部成功，返回True, 出现任何错误，都返回False
        """
        detail_action_state = "success"
        detail_error_message = False
        detail_ext_message = False

        shipment_sn = self._response_result.data["shipment_sn"]
        stock_picking = self._picking_cache.get(shipment_sn)

        try:
            for result in self._response_result.data["items"]:
                stock_move = stock_picking.move_lines.filtered(
                    lambda r: r.shop_product_id.seller_sku == result["msku"]
                              and r.fba_shipment_id == result["shipment_id"])
                if not stock_move:
                    detail_action_state = "failed"
                    detail_error_message = _("Can not find related stock move: \nShipment Id: %s, MSKU: %s") % (result["shipment_id"], result["msku"])
                    detail_ext_message = False
                    self._connector._raise_connector_error(detail_error_message)
                elif len(stock_move) > 1:
                    detail_action_state = "failed"
                    detail_error_message = _("Found too many related stock moves: \nShipment Id: %s, MSKU: %s") % (result["shipment_id"], result["msku"])
                    detail_ext_message = False
                    self._connector._raise_connector_error(detail_error_message)
                else:
                    stock_move.quantity_received = result["quantity_receive"]
                    stock_move.fba_shipment_state = result["shipment_status"].lower()

        except ConnectionError as error:
            detail_action_state = "failed"
            detail_ext_message = str(error)
        except Exception as error:
            detail_action_state = "failed"
            detail_error_message = _("Some error occurred while processing shipment data: %s.") % shipment_sn
            detail_ext_message = str(error)
        finally:
            if detail_action_state == "failed":
                self._add_process_result("failed", stock_picking.id)
                process_success = False
            else:
                self._add_process_result("updated", stock_picking.id)
                process_success = True

            # 添加明细行日志
            self._add_log_line(
                code_ref=self._response_result.data["id"],
                name_ref=self._response_result.data["shipment_sn"],
                action_state=detail_action_state,
                err_msg=detail_error_message,
                ext_msg=detail_ext_message,
                res_id=stock_picking.id if stock_picking else False,
            )

        return process_success
