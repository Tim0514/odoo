# Copyright 2020-2022 Max Share Technologies
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)
from .action_handler import ActionHandler, AHTools
from datetime import datetime

class ImportAmazonProducts(ActionHandler):

    def __init__(self, connector, log_book, start_time=None, end_time=None, **kwargs):
        super(ImportAmazonProducts, self).__init__(connector, log_book, start_time, end_time, **kwargs)
        self._request_records_limit = 1000
        self._request_offset = 0
        # 请求参数数据的总数量，默认为负数
        self._request_total = -1

        self._shop_ids_cache = False

    def _get_shop_ids(self):
        """
        取得参数中，需要的店铺数据
        该方法会根据上一次request的返回情况，决定是返回当前页数据，还是下一页数据。
        :return:
        """
        web_shop_obj = self._connector.env["web.sale.shop"]
        domain = [
            ("enable_exchange_data", "=", True),
            ("marketplace_id.type", "=", "amazon"),
        ]

        if self._request_total < 0:
            # 如果是第一次调用本方法，则先查询参数总数量。
            self._request_total = web_shop_obj.search_count(domain)
            self._request_offset = 0
        elif self._has_more_result_data:
            # 如果当前参数还有数据需要继续下载，则直接返回cache中的值
            return self._shop_ids_cache
        else:
            # 否则，要取得下一页参数
            self._request_offset += self._request_records_limit

        web_shops = web_shop_obj.search(
            domain,
            offset=self._request_offset,
            limit=self._request_records_limit,
            order="lingxing_shop_id")

        if self._request_offset + len(web_shops) >= self._request_total:
            # 全部数据已经查询出来了
            self._has_more_request_data = False
        else:
            self._has_more_request_data = True


        web_shop_ids = web_shops.mapped("lingxing_shop_id")
        web_shop_ids = ",".join(map(str, web_shop_ids))

        self._shop_ids_cache = web_shop_ids

        return web_shop_ids

    def prepare_req_body(self):

        web_shop_ids = self._get_shop_ids()

        if self._connector.name == "import_amazon_products":
            req_body = {
                "sid": web_shop_ids,
                "offset": self._result_offset,
                "length": self._result_records_limit,
                # "is_pair": 1,
                # "pair_update_start_time": self._data_start_time.strftime('%Y-%m-%d %H:%M:%S'),
                # "pair_update_end_time": self._data_end_time.strftime('%Y-%m-%d %H:%M:%S'),
                "listing_update_start_time": self._data_start_time.strftime('%Y-%m-%d %H:%M:%S'),
                "listing_update_end_time": self._data_end_time.strftime('%Y-%m-%d %H:%M:%S'),
            }
        else:
            req_body = {
                "sid": web_shop_ids,
                "offset": self._result_offset,
                "length": self._result_records_limit,
                "is_pair": 1,
                "pair_update_start_time": self._data_start_time.strftime('%Y-%m-%d %H:%M:%S'),
                "pair_update_end_time": self._data_end_time.strftime('%Y-%m-%d %H:%M:%S'),
                # "listing_update_start_time": self._data_start_time.strftime('%Y-%m-%d %H:%M:%S'),
                # "listing_update_end_time": self._data_end_time.strftime('%Y-%m-%d %H:%M:%S'),
            }

        return req_body

    def process_response_result(self):
        """
        self._response_result 有可能是ResponseResult，也有可能是List
        对于特定的Handler，需要对应相应的类型进行处理
        :return: 全部成功，返回True, 出现任何错误，都返回False
        """

        shop_product_obj = self._connector.env["web.sale.shop.product"]
        shop_product_asin_obj = self._connector.env["web.sale.shop.product.asin"]

        # 用于临时存储货币类型
        currency_dict = {}
        # 用于临时shop
        lingxing_shop_dict = {}

        process_success = True

        for result in self._response_result.data:
            detail_action_state = "success"
            detail_error_message = False
            detail_ext_message = False

            # 新建或修改的shop_product, 如果中途出错，则为False
            shop_product = False

            # 对每一行数据都捕捉错误，记录LOG
            try:
                # 创建新的product_vals 用于创建或更新产品信息
                product_vals = {}
                product_vals["seller_sku"] = result["seller_sku"]
                product_vals["product_asin"] = result["asin"]
                product_vals["product_listing_id"] = result["listing_id"]
                product_vals["product_fnsku"] = result["fnsku"]
                product_vals["parent_asin"] = result["parent_asin"]
                product_vals["shop_product_name"] = result["item_name"]
                product_vals["seller_rank"] = result["seller_rank"]
                product_vals["seller_rank_category"] = result["seller_category"]
                product_vals["review_num"] = result["review_num"]
                product_vals["review_star"] = AHTools.cfloat(result["last_star"])
                product_vals["fulfillment_channel_type"] = result["fulfillment_channel_type"]
                product_vals["afn_fulfillable_quantity"] = result["afn_fulfillable_quantity"]
                product_vals["reserved_fc_transfers"] = result["reserved_fc_transfers"]
                product_vals["reserved_fc_processing"] = result["reserved_fc_processing"]
                product_vals["reserved_customerorders"] = result["reserved_customerorders"]
                product_vals["afn_inbound_shipped_quantity"] = result["afn_inbound_shipped_quantity"]
                product_vals["afn_unsellable_quantity"] = result["afn_unsellable_quantity"]
                product_vals["afn_inbound_working_quantity"] = result["afn_inbound_working_quantity"]
                product_vals["afn_inbound_receiving_quantity"] = result["afn_inbound_receiving_quantity"]

                if (not ("listing_update_date" in result)) or result["listing_update_date"] == "":
                    product_vals["listing_update_time"] = False
                else:
                    product_vals["listing_update_time"] = datetime.strptime(result["listing_update_date"],
                                                                            "%Y-%m-%d %H:%M:%S")

                if (not ("pair_update_time" in result)) or result["pair_update_time"] == "":
                    product_vals["pair_update_time"] = False
                else:
                    product_vals["pair_update_time"] = datetime.strptime(result["pair_update_time"],
                                                                         "%Y-%m-%d %H:%M:%S")

                if result["status"] == 1:
                    product_vals["shop_product_state"] = "normal"
                else:
                    product_vals["shop_product_state"] = "stop"

                if result["is_delete"] == 1:
                    product_vals["is_deleted"] = True
                else:
                    product_vals["is_deleted"] = False

                # 检查Shop是否已经存在。
                if result["sid"] in lingxing_shop_dict:
                    product_vals["shop_id"] = lingxing_shop_dict[result["sid"]]
                else:
                    lingxing_shop_id = result["sid"]
                    domain = [
                        ("lingxing_shop_id", "=", lingxing_shop_id)
                    ]

                    web_shop = self._connector.env["web.sale.shop"].search(domain, limit=1)
                    if web_shop:
                        lingxing_shop_dict[lingxing_shop_id] = web_shop.id
                        product_vals["shop_id"] = web_shop.id
                    else:
                        detail_error_message = "Web Shop, %s, is not found in database." % (result["sid"])
                        self._connector._raise_connector_error(detail_error_message)

                # 检查currency是否已经存在
                if result["currency_code"] in currency_dict:
                    product_vals["currency_id"] = currency_dict[result["currency_code"]]
                else:
                    currency = self._connector.env["res.currency"].search([("name", "=", result["currency_code"])], limit=1)
                    if currency:
                        currency_dict[currency.name] = currency.id
                        product_vals["currency_id"] = currency.id
                    else:
                        detail_error_message = "Currency, %s, is not found in database." % (result["currency_code"])
                        self._connector._raise_connector_error(detail_error_message)

                # 如果有pair_update_time，则表示产品已配对。
                if "pair_update_time" in result and result["pair_update_time"] != "":
                    # 检查product是否已经存在
                    product_default_code = result["local_sku"]
                    product = self._connector.env["product.product"].search([("default_code", "=", product_default_code)],
                                                                 limit=1)
                    if product:
                        product_vals["product_id"] = product.id
                    else:
                        detail_error_message = "Product, %s, is not found in database." % (result["local_sku"])
                        self._connector._raise_connector_error(detail_error_message)
                else:
                    # 未配对产品
                    product_vals["product_id"] = False

                # 创建或更新product_asin数据
                product_asin_vals = shop_product_obj._prepare_product_asin_vals(product_vals)
                product_asin = shop_product_asin_obj.search([("shop_id", "=", product_asin_vals["shop_id"]),
                                                 ("product_asin", "=", product_asin_vals["product_asin"])], limit=1)
                if product_asin:
                    product_asin_vals = AHTools.get_changed_vals(product_asin, product_asin_vals)
                    if len(product_asin_vals) > 0:
                        product_asin.write(product_asin_vals)
                else:
                    product_asin = shop_product_asin_obj.create(product_asin_vals)
                product_vals["product_asin_id"] = product_asin.id
                product_vals.pop("product_asin")

                domain = [
                    ("shop_id", "=", product_vals["shop_id"]),
                    ("seller_sku", "=", product_vals["seller_sku"])]
                shop_product = shop_product_obj.search(domain, limit=1)
                if shop_product:
                    # shop_product已经存在，则更新。

                    # 如果下载的产品状态为停售，则店铺的state也设置为停售
                    # 如果state为停售，则根据下载的产品状态设置state
                    # 否则保持state中原有的状态(new, clearance, normal, stop)
                    # if product_vals["shop_product_state"] == "stop":
                    #     product_vals["state"] = product_vals["shop_product_state"]
                    # elif shop_product.state == "stop":
                    #     product_vals["state"] = product_vals["shop_product_state"]

                    product_vals = AHTools.get_changed_vals(shop_product, product_vals)

                    if len(product_vals) == 0:
                        self._add_process_result("ignored", shop_product.id)
                        detail_ext_message = "No Change."
                    else:
                        shop_product.write(product_vals)
                        self._add_process_result("updated", shop_product.id)
                        detail_ext_message = "Data updated."
                else:
                    # 否则创建
                    product_vals["state"] = product_vals["shop_product_state"]
                    shop_product = shop_product_obj.create(product_vals)
                    self._add_process_result("created", shop_product.id)
                    detail_ext_message = "Data created."

                self._connector.env.cr.commit()

            except ConnectionError as error:
                detail_action_state = "fail"
                detail_ext_message = str(error)
            except Exception as error:
                detail_action_state = "fail"
                detail_error_message = "Some error occurred while processing product: %s." % (result["seller_sku"])
                detail_ext_message = str(error)
            finally:
                if detail_action_state == "fail":
                    self._add_process_result("failed", result["seller_sku"])
                    process_success = False

                # 添加明细行日志
                self._add_log_line(
                    code_ref=result["seller_sku"],
                    name_ref=result["item_name"],
                    action_state=detail_action_state,
                    err_msg=detail_error_message,
                    ext_msg=detail_ext_message,
                    res_id=shop_product.id if shop_product else False,
                )

        return process_success


class ImportMultiplatformProducts(ActionHandler):

    def __init__(self, connector, log_book, start_time=None, end_time=None, **kwargs):
        super(ImportMultiplatformProducts, self).__init__(connector, log_book, start_time, end_time, **kwargs)
        self._result_records_limit = 200

        self._has_more_request_data = True

        self._amazon_shop_cache = {}
        self._mp_shop_cache = {}

        self._init_cache()

    def _init_cache(self):
        shop_obj = self._connector.env["web.sale.shop"]
        domain = [
            ("marketplace_id.type", "=", "amazon"),
        ]
        shops = shop_obj.search(domain)
        for shop in shops:
            key = (shop.lingxing_mp_shop_id,)
            self._amazon_shop_cache.setdefault(key, shop)

        domain = [
            ("marketplace_id.type", "!=", "amazon"),
        ]
        shops = shop_obj.search(domain)
        for shop in shops:
            key = (shop.lingxing_mp_shop_id,)
            self._mp_shop_cache.setdefault(key, shop)


    def prepare_req_body(self):

        self._has_more_request_data = False

        req_body = {
            "offset": self._result_offset,
            "length": self._result_records_limit,
            "start_time": self._data_start_time.strftime('%Y-%m-%d %H:%M:%S'),
            # "end_time": self._data_end_time.strftime('%Y-%m-%d %H:%M:%S'),
        }

        return req_body

    def process_response_result(self):
        """
        self._response_result 有可能是ResponseResult，也有可能是List
        对于特定的Handler，需要对应相应的类型进行处理
        :return: 全部成功，返回True, 出现任何错误，都返回False
        """

        shop_product_obj = self._connector.env["web.sale.shop.product"]

        process_success = True

        for result in self._response_result.data["list"]:
            detail_action_state = "success"
            detail_error_message = False
            detail_ext_message = False

            # 新建或修改的shop_product, 如果中途出错，则为False
            shop_product = False

            # 对每一行数据都捕捉错误，记录LOG
            try:
                if (result["store_id"],) in self._amazon_shop_cache:
                    detail_action_state = "ignored"
                    detail_error_message = "%s is an amazon product." % (result["seller_sku"])
                    self._add_process_result(detail_action_state, result["MSKU"])
                    continue
                elif (result["store_id"],) not in self._mp_shop_cache:
                    detail_action_state = "error"
                    detail_error_message = "Shop, %s, is not found." % (result["store_id"])
                    self._connector._raise_connector_error(detail_error_message)

                # 创建新的product_vals 用于创建或更新产品信息
                product_vals = {}
                product_vals["seller_sku"] = result["msku"]
                product_vals["listing_update_time"] = datetime.strptime(result["modify_time"], "%Y-%m-%d %H:%M:%S")
                product_vals["pair_update_time"] = datetime.strptime(result["modify_time"], "%Y-%m-%d %H:%M:%S")
                product_vals["shop_product_state"] = "normal"
                product_vals["state"] = "normal"
                product_vals["shop_id"] = self._mp_shop_cache[(result["store_id"],)].id

                # 检查product是否已经存在
                product = self._connector.env["product.product"].search([("default_code", "=", result["sku"])],
                                                             limit=1)
                if product:
                    product_vals["product_id"] = product.id
                else:
                    product_vals["product_id"] = False
                    detail_action_state = "warning"
                    detail_error_message = "Product, %s, is not found in database." % (result["sku"])
                    detail_ext_message = "Data updated."

                domain = [
                    ("shop_id", "=", product_vals["shop_id"]),
                    ("seller_sku", "=", product_vals["seller_sku"])]
                shop_product = shop_product_obj.search(domain, limit=1)
                if shop_product:
                    product_vals = AHTools.get_changed_vals(shop_product, product_vals)
                    if len(product_vals) > 0:
                        shop_product.write(product_vals)
                        if detail_action_state != "warning":
                            detail_action_state = "updated"
                            detail_ext_message = "Data updated."
                        self._add_process_result(detail_action_state, shop_product.id)
                    else:
                        detail_action_state = "ignored"
                        detail_ext_message = "No Change."
                        self._add_process_result(detail_action_state, shop_product.id)
                else:
                    shop_product = shop_product_obj.create(product_vals)
                    if detail_action_state != "warning":
                        detail_action_state = "created"
                        detail_ext_message = "Data created."
                    self._add_process_result(detail_action_state, shop_product.id)
            except ConnectionError as error:
                detail_action_state = "fail"
                detail_ext_message = str(error)
            except Exception as error:
                detail_action_state = "fail"
                detail_error_message = "Some error occurred while processing product: %s." % (result["msku"])
                detail_ext_message = str(error)
            finally:
                if detail_action_state == "fail":
                    self._add_process_result("failed", result["msku"])
                    process_success = False

                # 添加明细行日志
                self._add_log_line(
                    code_ref=result["msku"],
                    name_ref=result["local_name"],
                    action_state=detail_action_state,
                    err_msg=detail_error_message,
                    ext_msg=detail_ext_message,
                    res_id=shop_product.id if shop_product else False,
                )

        return process_success
