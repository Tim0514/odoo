# Copyright 2020-2022 Max Share Technologies
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)
import time
from collections import defaultdict
from odoo import _

from dateutil.parser import parse

from .action_handler import ActionHandler, AHTools
from datetime import datetime, date
from re import sub
from decimal import Decimal

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
            ("marketplace_id.type", "=", "amazon"),
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
                order_vals["date_ordered"] = AHTools.get_utc_datetime(result["purchase_date"], "UTC")
                order_vals["date_ordered_local"] = AHTools.get_local_datetime_str(result["purchase_date_local"], shop.timezone)
                order_vals["state"] = result["order_status"].lower()

                # 检查currency是否已经存在
                if not result["order_total_currency_code"] or result["order_total_currency_code"] == "":
                    order_vals["currency_id"] = shop.get_currency_id().id
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

                order_vals["date_modified"] = AHTools.get_utc_datetime(result["gmt_modified"], "Asia/Shanghai")

                last_update_date = AHTools.get_utc_datetime(result["last_update_date"], shop.timezone)
                last_update_date_local = AHTools.get_local_datetime_str(result["last_update_date"], shop.timezone)
                order_vals["last_update_date"] = last_update_date
                order_vals["last_update_date_local"] = last_update_date_local
                order_vals["amount_total"] = AHTools.cfloat(result["order_total_amount"])
                order_vals["amount_refund"] = result["refund_amount"]
                order_vals["buyer_email"] = result["buyer_email"]
                order_vals["is_return"] = str(result["is_return"])
                order_vals["is_mcf_order"] = result["is_mcf_order"]
                order_vals["is_assessed"] = result["is_assessed"]
                order_vals["earliest_ship_date"] = AHTools.get_utc_datetime(result["earliest_ship_date"], "UTC")
                order_vals["shipment_date"] = AHTools.get_utc_datetime(result["shipment_date"], "UTC")
                order_vals["shipment_date_local"] = AHTools.get_local_datetime_str(result["shipment_date_local"], shop.timezone)
                order_vals["tracking_number"] = result["tracking_number"]
                order_vals["postal_code"] = result["postal_code"]
                order_vals["phone"] = result["phone"]
                order_vals["fulfillment_channel_type"] = result["fulfillment_channel"]

                posted_date = AHTools.get_utc_datetime(result["posted_date"], shop.timezone)
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
                        line_vals["quantity_ordered"] = AHTools.cint(item["quantity_ordered"])
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


class ImportMultiplatformOrders(ActionHandler):

    def __init__(self, connector, log_book, start_time=None, end_time=None, **kwargs):
        super(ImportMultiplatformOrders, self).__init__(connector, log_book, start_time, end_time, **kwargs)
        self._result_records_limit = 200

        if not isinstance(start_time, datetime):
            self._data_start_time = datetime.combine(start_time, datetime.min.time())

        if not isinstance(end_time, datetime):
            self._data_end_time = datetime.combine(end_time, datetime.min.time())

        self._has_more_request_data = True
        self._has_more_result_data = False

        self._shop_cache = {}
        self._mp_shop_ids = []
        self._shop_product_cache = {}

        self._init_cache()

    def _init_cache(self):
        shop_obj = self._connector.env["web.sale.shop"]
        domain = [
            ("enable_exchange_data", "=", True),
            ("marketplace_id.type", "!=", "amazon"),
        ]
        shops = shop_obj.search(domain)
        for shop in shops:
            key = (shop.lingxing_mp_shop_id,)
            self._shop_cache.setdefault(key, shop)
            self._mp_shop_ids.append(int(shop.lingxing_mp_shop_id))

        shop_product_obj = self._connector.env["web.sale.shop.product"]
        # 在shop_product_asin表中查找对应的产品。
        domain = [
            ("shop_id", "in", shops.ids),
        ]
        shop_products = shop_product_obj.search(domain)
        for line in shop_products:
            key = (line.shop_id.lingxing_mp_shop_id, line.seller_sku)
            self._shop_product_cache.setdefault(key, line)

    def prepare_req_body(self):

        self._has_more_request_data = False
        req_body = {
            "store_id": self._mp_shop_ids,
            "start_time": int(self._data_start_time.timestamp()),
            "end_time": int(self._data_end_time.timestamp()),
            "date_type": "update_time",
        }

        req_body.setdefault("offset", self._result_offset)
        req_body.setdefault("length", self._result_records_limit)
        return req_body

    def process_response_result(self):
        """
        self._response_result 有可能是ResponseResult，也有可能是List
        对于特定的Handler，需要对应相应的类型进行处理
        :return: 全部成功，返回True, 出现任何错误，都返回False
        """

        order_obj = self._connector.env["web.sale.order"]
        order_line_obj = self._connector.env["web.sale.order.line"]

        # 用于临时存储货币类型
        currency_dict = {}

        process_success = True

        for result in self._response_result.data["list"]:
            detail_action_state = "success"
            detail_error_message = False
            detail_ext_message = False

            # 对每一行数据都捕捉错误，记录LOG
            order = False

            try:
                key = (result["store_id"],)
                shop = self._shop_cache.get(key)

                if not shop:
                    # 如果请求参数中店铺为空，则会返回全部店铺的订单。
                    # 但有可能该店铺在Odoo中设置了不允许交换数据。从而不在店铺缓存中。
                    detail_action_state = "fail"
                    detail_error_message = _("Shop is not found. Order No.: %s, Shop Id.: %s") % (result["global_order_no"], result["store_id"])
                    detail_ext_message = ""
                    continue


                order_vals = {}

                order_vals["shop_id"] = shop.id
                order_vals["order_ref"] = result["platform_info"][0]["platform_order_no"]
                order_vals["system_order_ref"] = result["global_order_no"]
                order_vals["date_ordered"] = datetime.utcfromtimestamp(result["global_purchase_time"])
                order_vals["date_ordered_local"] = AHTools.get_local_datetime_str(order_vals["date_ordered"], shop.timezone)

                order_status = result["status"]
                if order_status in [6,9]:
                    order_vals["state"] = "shipped"
                elif order_status in [7]:
                    order_vals["state"] = "canceled"
                else:
                    order_vals["state"] = order_status

                # 检查currency是否已经存在
                if not result["amount_currency"] or result["amount_currency"] == "":
                    order_vals["currency_id"] = shop.get_currency_id().id
                elif result["amount_currency"] in currency_dict:
                    order_vals["currency_id"] = currency_dict[result["amount_currency"]]
                else:
                    currency = self._connector.env["res.currency"].search([("name", "=", result["amount_currency"])], limit=1)
                    if currency:
                        currency_dict[currency.name] = currency.id
                        order_vals["currency_id"] = currency.id
                    else:
                        detail_error_message = _("Currency, %s, is not found in database.") % (result["amount_currency"])
                        self._connector._raise_connector_error(detail_error_message)

                order_vals["date_modified"] = datetime.utcfromtimestamp(int(result["update_time"]))
                order_vals["last_update_date"] = order_vals["date_modified"]
                order_vals["last_update_date_local"] = AHTools.get_local_datetime_str(order_vals["date_modified"], shop.timezone)
                amount_item_total = Decimal(sub(r'[^\d\-.]', '', result["transaction_info"][0]["order_item_amount"]))
                discount_amount = Decimal(sub(r'[^\d\-.]', '', result["transaction_info"][0]["discount_amount"]))
                order_vals["amount_total"] = amount_item_total - discount_amount
                order_vals["amount_refund"] = 0
                order_vals["is_return"] = "0"
                order_vals["is_mcf_order"] = False
                order_vals["is_assessed"] = False
                order_vals["buyer_name"] = result["buyers_info"]["buyer_name"]
                order_vals["buyer_email"] = result["buyers_info"]["buyer_email"]
                order_vals["earliest_ship_date"] = datetime.utcfromtimestamp(result["platform_info"][0]["latest_ship_time"])
                order_vals["shipment_date"] = order_vals["earliest_ship_date"]
                order_vals["shipment_date_local"] = AHTools.get_local_datetime_str(order_vals["earliest_ship_date"], shop.timezone)
                order_vals["postal_code"] = result["address_info"]["postal_code"]
                order_vals["phone"] = result["address_info"]["receiver_mobile"]
                order_vals["posted_date"] = datetime.utcfromtimestamp(result["global_delivery_time"])
                order_vals["fulfillment_channel_type"] = result["delivery_type"]
                order_vals["receiver_name"] = result["address_info"]["receiver_name"]
                order_vals["receiver_country_code"] = result["address_info"]["receiver_country_code"]
                order_vals["receiver_city"] = result["address_info"]["city"]
                order_vals["receiver_state_or_region"] = result["address_info"]["state_or_region"]
                order_vals["receiver_address_1"] = result["address_info"]["address_line1"]
                order_vals["receiver_address_2"] = result["address_info"]["address_line2"]
                order_vals["receiver_address_3"] = result["address_info"]["address_line3"]

                domain = [
                    ("shop_id", "=", order_vals["shop_id"]),
                    ("order_ref", "=", order_vals["order_ref"]),
                    ]
                order = order_obj.search(domain, limit=1)
                if order:
                    # 已经存在，则更新。
                    order_vals = AHTools.get_changed_vals(order, order_vals)
                    order.write(order_vals)
                    detail_action_state = "updated"
                    detail_error_message = ""
                    detail_ext_message = "Data updated."
                else:
                    order = order_obj.create(order_vals)
                    detail_action_state = "created"
                    detail_error_message = ""
                    detail_ext_message = "Data created."

                item_list = result["item_info"]
                for item in item_list:
                    line_vals = {}
                    key = (shop.lingxing_mp_shop_id, item["msku"],)
                    shop_product = self._shop_product_cache.get(key)
                    if shop_product:
                        line_vals["shop_product_id"] = shop_product.id
                        line_vals["quantity_ordered"] = AHTools.cint(item["quantity"])
                        line_vals["order_id"] = order.id

                        order_line = order.order_lines.filtered(
                            lambda r: r.shop_product_id.id == line_vals["shop_product_id"])
                        if order_line:
                            line_vals = AHTools.get_changed_vals(order_line, line_vals)
                            if len(line_vals) > 0:
                                order_line.write(line_vals)
                        else:
                            order_line = order_line_obj.create(line_vals)
                    else:
                        detail_action_state = "warning"
                        if detail_error_message and detail_error_message != "":
                            detail_error_message += "\n"
                        detail_error_message += _("Order line ignored, as product is not found in database.\n"
                                                  "Shop: %s, Order No.: %s, Product: %s"
                                                  ) % (order.shop_id.name, order.order_ref, item["msku"],)

                self._add_process_result(detail_action_state, order.id)

            except ConnectionError as error:
                detail_action_state = "fail"
                detail_ext_message = str(error)
            except Exception as error:
                detail_action_state = "fail"
                detail_error_message = "Some error occurred while processing order: %s." % (result["global_order_no"])
                detail_ext_message = str(error)
            finally:
                if detail_action_state == "fail":
                    self._add_process_result("failed", result["global_order_no"])
                    process_success = False

                # 添加明细行日志
                self._add_log_line(
                    code_ref=result["global_order_no"],
                    name_ref=result["global_order_no"],
                    action_state=detail_action_state,
                    err_msg=detail_error_message,
                    ext_msg=detail_ext_message,
                    res_id=order.id if order else False,
                )

        return process_success
