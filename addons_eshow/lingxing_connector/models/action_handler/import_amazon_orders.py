# Copyright 2020-2022 Max Share Technologies
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)
from collections import defaultdict
from odoo import _

from dateutil.parser import parse

from .action_handler import ActionHandler, ActionHandlerTools
from datetime import datetime

class ImportAmazonOrders(ActionHandler):

    def __init__(self, connector, log_book, start_time=None, end_time=None, **kwargs):
        super(ImportAmazonOrders, self).__init__(connector, log_book, start_time, end_time, **kwargs)
        self._search_param_list = []

        self._has_more_request_data = True
        self._has_more_result_data = False

        # 请求参数数据的总数量，默认为负数
        self._request_total = -1
        self._request_offset = -1

        self._shop_cache = {}
        self._shop_product_cache = {}

        self._init_cache()

    def _init_cache(self):
        shop_obj = self._connector.env["web.sale.shop"]
        domain = [
            ("enable_exchange_data", "=", True),
        ]
        shops = shop_obj.search(domain)
        for shop in shops:
            key = (shop.lingxing_shop_id,)
            self._shop_cache.setdefault(key, shop)

        shop_product_obj = self._connector.env["web.sale.shop.product"]
        # 在shop_product_asin表中查找对应的产品。
        domain = [
            ("shop_id", "in", shops.ids),
        ]
        shop_products = shop_product_obj.search(domain)
        for line in shop_products:
            key = (line.shop_id.lingxing_shop_id, line.seller_sku)
            self._shop_product_cache.setdefault(key, line)

    def prepare_req_body(self):
        if self._request_total < 0:
            # 初始化请求参数
            for shop in self._shop_cache.values():
                req_body = {
                    "sid": shop.lingxing_shop_id,
                    "start_date": self._data_start_time.strftime('%Y-%m-%d %H:%M:%S'),
                    "end_date": self._data_end_time.strftime('%Y-%m-%d %H:%M:%S'),
                    "date_type": 3,
                }
                self._search_param_list.append(req_body)
            self._request_total = len(self._search_param_list)

            self._request_offset = -1
            if self._request_total > 0:
                self._has_more_request_data = True
            else:
                self._has_more_request_data = False
            self._has_more_result_data = False

        if self._has_more_result_data:
            req_body = self._search_param_list[self._request_offset].copy()
            req_body.setdefault("offset", self._result_offset)
            req_body.setdefault("length", self._result_records_limit)
            return req_body
        elif self._has_more_request_data:
            self._request_offset += 1
            req_body = self._search_param_list[self._request_offset].copy()
            req_body.setdefault("offset", self._result_offset)
            req_body.setdefault("length", self._result_records_limit)
            if self._request_offset + 1 >= self._request_total:
                # 已经是最后一个请求参数。
                self._has_more_request_data = False
            return req_body
        else:
            raise Exception("没有获取到可请求的参数。")

    def process_response_result(self):
        """
        self._response_result 有可能是ResponseResult，也有可能是List
        对于特定的Handler，需要对应相应的类型进行处理
        :return: 全部成功，返回True, 出现任何错误，都返回False
        """

        order_obj = self._connector.env["web.sale.order"]
        order_line_obj = self._connector.env["web.sale.order.line"]

        key = (self._search_param_list[self._request_offset]["sid"],)
        shop = self._shop_cache.get(key)


        # 用于临时存储货币类型
        currency_dict = {}

        process_success = True

        for result in self._response_result.data:
            detail_action_state = "success"
            detail_error_message = False
            detail_ext_message = False

            # 对每一行数据都捕捉错误，记录LOG
            order = False

            try:
                order_vals = {}

                order_vals["shop_id"] = shop.id
                order_vals["order_ref"] = result["amazon_order_id"]
                order_vals["date_ordered"] = ActionHandlerTools.get_utc_datetime(result["purchase_date"], "UTC")
                order_vals["date_ordered_local"] = ActionHandlerTools.get_local_datetime_str(result["purchase_date_local"], shop.timezone)
                order_vals["state"] = result["order_status"]

                # 检查currency是否已经存在
                if not result["order_total_currency_code"] or result["order_total_currency_code"] == "":
                    order_vals["currency_id"] = shop.marketplace_id.country_id.currency_id.id
                elif result["order_total_currency_code"] in currency_dict:
                    order_vals["currency_id"] = currency_dict[result["order_total_currency_code"]]
                else:
                    currency = self._connector.env["res.currency"].search([("name", "=", result["order_total_currency_code"])], limit=1)
                    if currency:
                        currency_dict[currency.name] = currency.id
                        order_vals["currency_id"] = currency.id
                    else:
                        detail_error_message = _("Currency, %s, is not found in database.") % (result["order_total_currency_code"])
                        self._connector._raise_connector_error(detail_error_message)

                order_vals["date_modified"] = ActionHandlerTools.get_utc_datetime(result["gmt_modified"], "UTC")

                last_update_date = ActionHandlerTools.get_utc_datetime(result["last_update_date"], shop.timezone)
                last_update_date_local = ActionHandlerTools.get_local_datetime_str(result["last_update_date"], shop.timezone)
                order_vals["last_update_date"] = last_update_date
                order_vals["last_update_date_local"] = last_update_date_local
                order_vals["amount_total"] = ActionHandlerTools.cfloat(result["order_total_amount"])
                order_vals["amount_refund"] = result["refund_amount"]
                order_vals["buyer_email"] = result["buyer_email"]
                order_vals["is_return"] = str(result["is_return"])
                order_vals["is_mcf_order"] = result["is_mcf_order"]
                order_vals["is_assessed"] = result["is_assessed"]
                order_vals["earliest_ship_date"] = ActionHandlerTools.get_utc_datetime(result["earliest_ship_date"], "UTC")
                order_vals["shipment_date"] = ActionHandlerTools.get_utc_datetime(result["shipment_date"], "UTC")
                order_vals["shipment_date_local"] = ActionHandlerTools.get_local_datetime_str(result["shipment_date_local"], shop.timezone)
                order_vals["tracking_number"] = result["tracking_number"]
                order_vals["postal_code"] = result["postal_code"]
                order_vals["phone"] = result["phone"]

                posted_date = ActionHandlerTools.get_utc_datetime(result["posted_date"], shop.timezone)
                order_vals["posted_date"] = posted_date

                domain = [
                    ("shop_id", "=", order_vals["shop_id"]),
                    ("order_ref", "=", order_vals["order_ref"]),
                    ]
                order = order_obj.search(domain, limit=1)
                if order:
                    # 已经存在，则更新。
                    order.write(order_vals)
                    detail_action_state = "updated"
                    detail_error_message = ""
                    detail_ext_message = "Data updated."
                else:
                    order = order_obj.create(order_vals)
                    detail_action_state = "created"
                    detail_error_message = ""
                    detail_ext_message = "Data created."

                item_list = result["item_list"]
                for item in item_list:
                    line_vals = {}
                    key = (shop.lingxing_shop_id, item["seller_sku"],)
                    shop_product = self._shop_product_cache.get(key)
                    if shop_product:
                        line_vals["shop_product_id"] = shop_product.id
                        line_vals["quantity_ordered"] = ActionHandlerTools.cint(item["quantity_ordered"])
                        line_vals["order_id"] = order.id

                        order_line = order.order_lines.filtered(
                            lambda r: r.shop_product_id.id == line_vals["shop_product_id"])
                        if order_line:
                            order_line.write(line_vals)
                        else:
                            order_line = order_line_obj.create(line_vals)
                    else:
                        detail_action_state = "warning"
                        if detail_error_message and detail_error_message != "":
                            detail_error_message += "\n"
                        detail_error_message += _("Order line ignored, as product is not found in database.\n"
                                                  "Shop: %s, Order No.: %s, Product: %s"
                                                  ) % (order.shop_id.name, order.order_ref, item["seller_sku"],)

                self._add_process_result(detail_action_state, order.id)

            except ConnectionError as error:
                detail_action_state = "fail"
                detail_ext_message = str(error)
            except Exception as error:
                detail_action_state = "fail"
                detail_error_message = "Some error occurred while processing order: %s." % (result["amazon_order_id"])
                detail_ext_message = str(error)
            finally:
                if detail_action_state == "fail":
                    self._add_process_result("failed", result["amazon_order_id"])
                    process_success = False

                # 添加明细行日志
                self._add_log_line(
                    code_ref=result["amazon_order_id"],
                    name_ref=result["amazon_order_id"],
                    action_state=detail_action_state,
                    err_msg=detail_error_message,
                    ext_msg=detail_ext_message,
                    res_id=order.id if order else False,
                )

        return process_success

