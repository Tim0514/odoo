# Copyright 2020-2022 Max Share Technologies
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)
import datetime

import odoo.tools.date_utils
from .action_handler import ActionHandler, ActionHandlerTools


class ImportShopInventory(ActionHandler):

    def __init__(self, connector, log_book, start_time=None, end_time=None, **kwargs):
        super(ImportShopInventory, self).__init__(connector, log_book, start_time, end_time, **kwargs)
        self._request_page_limit = 1000
        self._shop_ids_cache = False

        self._inventory_date = datetime.datetime.now()

        self._shop_cache = {}
        self._shop_product_cache = {}
        self._shop_warehouse_cache = {}
        self._shop_inventory_cache = {}

        self._reset_shop_inventory()
        self._init_cache()

    def _reset_shop_inventory(self):
        """
        把库存数据中的旧数据is_latest_inventory全部设置为False。
        :return:
        """
        shop_inventory_obj = self._connector.env["web.sale.shop.inventory"]
        domain = [
            ("company_id", "=", self._connector.env.company.id),
            ("is_latest_inventory", "=", True),
        ]
        shop_inventory = shop_inventory_obj.search(domain)
        shop_inventory.write(
            {
                "is_latest_inventory": False,
            }
        )

    def set_result(self, response_result):
        """
        Import Shop Inventory 中，
        数据的total信息在response_result.data["total"]中

        :param response_result:
        :return:
        """
        self._response_result = response_result

        # 如果返回的是ResponseResult, 此时是发送了single_request以后的返回值。
        self._result_total = self._response_result.data["total"]
        self._result_length = len(self._response_result.data["list"])

        if self._result_offset + self._result_length < self._result_total:
            self._has_more_result_data = True
        else:
            self._has_more_result_data = False
        self._result_offset += self._result_length

    def _init_cache(self):
        shop_obj = self._connector.env["web.sale.shop"]
        shop_product_obj = self._connector.env["web.sale.shop.product"]
        shop_warehouse_obj = self._connector.env["web.sale.warehouse"]
        shop_inventory_obj = self._connector.env["web.sale.shop.inventory"]

        domain = [
            ("company_id", "=", self._connector.env.company.id),
            ("enable_exchange_data", "=", True),
        ]
        shops = shop_obj.search(domain)
        for shop in shops:
            key = (shop.lingxing_shop_id,)
            self._shop_cache.setdefault(key, shop)

        domain = [
            ("company_id", "=", self._connector.env.company.id),
        ]
        shop_products = shop_product_obj.search(domain)
        for shop_product in shop_products:
            key = (shop_product.lingxing_shop_id, shop_product.seller_sku, shop_product.product_fnsku)
            if self._shop_product_cache.get(key):
                detail_error_message = "Found more than one record for MSKU, %s, in shop, %s in shop product database.  " \
                                       "You must archive all useless shop products." % (shop_product.seller_sku, shop_product.shop_name)
                self._connector._raise_connector_error(detail_error_message)
            self._shop_product_cache.setdefault(key, shop_product)

        shop_warehouse = shop_warehouse_obj.search(domain)
        for line in shop_warehouse:
            key = (line.name,)
            self._shop_warehouse_cache.setdefault(key, line)

        date_start = odoo.tools.date_utils.subtract(self._inventory_date, days=30)
        domain = [
            ("company_id", "=", self._connector.env.company.id),
            ("inventory_date", ">=", date_start),
        ]
        fields = ["shop_warehouse_id", "shop_product_id", "sellable_quantity:min"]
        group_by = ["shop_warehouse_id", "shop_product_id"]
        shop_inventory = shop_inventory_obj.read_group(domain, fields=fields, groupby=group_by, lazy=False)
        for line in shop_inventory:
            key = (line["shop_warehouse_id"][0], line["shop_product_id"][0])
            self._shop_inventory_cache.setdefault(key, line["sellable_quantity"])

    def _get_shop_ids(self):
        """
        取得参数中，需要的店铺数据
        该方法会根据上一次request的返回情况，决定是返回当前页数据，还是下一页数据。
        :return:
        """
        web_shop_obj = self._connector.env["web.sale.shop"]
        domain = [("company_id", "=", self._connector.env.company.id), ("enable_exchange_data", "=", True)]

        if self._request_total < 0:
            # 如果是第一次调用本方法，则先查询参数总数量。
            self._request_total = web_shop_obj.search_count(domain)
            self._request_offset = 0
        elif self._has_more_result_data:
            # 如果当前参数还有数据需要继续下载，则直接返回cache中的值
            return self._shop_ids_cache
        else:
            # 否则，要取得下一页参数
            self._request_offset += self._request_page_limit

        web_shops = web_shop_obj.search(
            domain,
            offset=self._request_offset,
            limit=self._request_page_limit,
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

        req_body = {
            "sid": web_shop_ids,
            "offset": self._result_offset,
            "length": self._result_page_limit,
        }

        return req_body

    def process_response_result(self):
        """
        self._response_result 有可能是ResponseResult，也有可能是List
        对于特定的Handler，需要对应相应的类型进行处理
        :return: 全部成功，返回True, 出现任何错误，都返回False
        """

        shop_obj = self._connector.env["web.sale.shop"]
        shop_inventory_obj = self._connector.env["web.sale.shop.inventory"]
        shop_product_obj = self._connector.env["web.sale.shop.product"]
        shop_warehouse_obj = self._connector.env["web.sale.warehouse"]

        process_success = True

        for result in self._response_result.data["list"]:
            detail_action_state = "success"
            detail_error_message = False
            detail_ext_message = False

            # 对每一行数据都捕捉错误，记录LOG
            try:
                is_parent_product = False

                # 创建新的model_vals 用于创建或更新产品信息
                model_vals = {}

                key = (result["wname"],)
                shop_warehouse = self._shop_warehouse_cache.get(key)
                if shop_warehouse:
                    # 临时代码，补上shop_warehouse中没有设置的share_type字段值
                    if not shop_warehouse.share_type:
                        if result["share_type"] == 1:
                            share_type = "na"
                        elif result["share_type"] == 2:
                            share_type = "eu"
                        else:
                            share_type = "none"
                        shop_warehouse.share_type = share_type

                    # 如果是多国店铺，则仓库的默认店铺，要设置到美国站，或者是德国站
                    if shop_warehouse.share_type == "na" and not shop_warehouse.default_shop_id:
                        warehouse_name = result["wname"]
                        default_lingxing_shop_name = warehouse_name[:warehouse_name.rfind("北美仓")] + "-US"
                        shop_obj = self._connector.env["web.sale.shop"]
                        domain = [
                            ("company_id", "=", self._connector.env.company.id),
                            ("lingxing_shop_name", "=", default_lingxing_shop_name),
                        ]
                        shops = shop_obj.search(domain)
                        if shops:
                            shop = shops[0]
                        else:
                            key = (result["sid"],)
                            shop = self._shop_cache.get(key)
                        shop_warehouse.default_shop_id = shop

                        key = (result["sid"],)
                        shop = self._shop_cache.get(key)
                        # 如果是多国仓库，但是该仓库的店铺信息里还没有该店铺。
                        # 则要建立仓库与该店铺的关联
                        if shop.id not in shop_warehouse.shop_ids.ids:
                            shop_warehouse.write({"shop_ids": [(4, shop.id)]})

                    elif shop_warehouse.share_type == "eu" and not shop_warehouse.default_shop_id:
                        warehouse_name = result["wname"]
                        default_lingxing_shop_name = warehouse_name[:warehouse_name.rfind("欧洲仓")] + "-DE"
                        shop_obj = self._connector.env["web.sale.shop"]
                        domain = [
                            ("company_id", "=", self._connector.env.company.id),
                            ("lingxing_shop_name", "=", default_lingxing_shop_name),
                        ]
                        shops = shop_obj.search(domain)
                        if shops:
                            shop = shops[0]
                        else:
                            key = (result["sid"],)
                            shop = self._shop_cache.get(key)
                        shop_warehouse.default_shop_id = shop

                        key = (result["sid"],)
                        shop = self._shop_cache.get(key)
                        # 如果是多国仓库，但是该仓库的店铺信息里还没有该店铺。
                        # 则要建立仓库与该店铺的关联
                        if shop.id not in shop_warehouse.shop_ids.ids:
                            shop_warehouse.write({"shop_ids": [(4, shop.id)]})
                    elif not shop_warehouse.default_shop_id:
                        key = (result["sid"],)
                        shop = self._shop_cache.get(key)
                        shop_warehouse.default_shop_id = shop
                else:
                    # 如果没有找到店铺仓库信息，则新建仓库记录，并建立店铺与仓库的关联。
                    if result["share_type"] == 1:
                        share_type = "na"
                    elif result["share_type"] == 2:
                        share_type = "eu"
                    else:
                        share_type = "none"

                    key = (result["sid"],)
                    shop = self._shop_cache.get(key)
                    # 如果是多国店铺，则仓库的默认店铺，要设置到美国站，或者是德国站
                    if share_type == "na":
                        warehouse_name = result["wname"]
                        default_lingxing_shop_name = warehouse_name[:warehouse_name.rfind("北美仓")] + "-US"
                        shop_obj = self._connector.env["web.sale.shop"]
                        domain = [
                            ("company_id", "=", self._connector.env.company.id),
                            ("lingxing_shop_name", "=", default_lingxing_shop_name),
                        ]
                        shops = shop_obj.search(domain)
                        if shops:
                            shop = shops[0]
                    elif share_type == "eu":
                        warehouse_name = result["wname"]
                        default_lingxing_shop_name = warehouse_name[:warehouse_name.rfind("北美仓")] + "-DE"
                        shop_obj = self._connector.env["web.sale.shop"]
                        domain = [
                            ("company_id", "=", self._connector.env.company.id),
                            ("lingxing_shop_name", "=", default_lingxing_shop_name),
                        ]
                        shops = shop_obj.search(domain)
                        if shops:
                            shop = shops[0]

                    warehouse_vals = {
                        "company_id": self._connector.env.company.id,
                        "name": result["wname"],
                        "share_type": share_type,
                        "shop_ids": [(4, shop.id)],
                        "default_shop_id": shop.id,
                    }
                    shop_warehouse = shop_warehouse_obj.create(warehouse_vals)
                    key = (shop_warehouse.name,)
                    self._shop_warehouse_cache.setdefault(key, shop_warehouse)

                if shop_warehouse.share_type != "none":
                    # 如果是多国共享仓库，需要使用该仓库的默认补货店铺的ID，用来查找店铺商品
                    key = (shop_warehouse.default_shop_id.lingxing_shop_id, result["msku"], result["fnsku"])
                else:
                    key = (result["sid"], result["msku"], result["fnsku"])
                shop_product = self._shop_product_cache.get(key)

                if not shop_product:
                    key = (result["sid"],)
                    shop = self._shop_cache.get(key)
                    if result["fnsku"] == "" or result["msku"].count('-') < 2:
                        # 可能是父SKU，忽略
                        is_parent_product = True
                        self._add_process_result("ignored", result["msku"])
                        detail_ext_message = "MSKU, %s, in shop, %s, is a parent sku." % (result["msku"], shop.name)
                    else:
                        # 如果是多国店铺，有可能产品在补货店铺里面不存在。则找当前店铺产品
                        if shop_warehouse.share_type != "none":
                            key = (result["sid"], result["msku"], result["fnsku"])
                            shop_product = self._shop_product_cache.get(key)
                            if shop_product:
                                # 如果找到产品, 则给警告信息
                                detail_action_state = "warning"
                                detail_error_message = "MSKU, %s is not found in procurement shop, %s, but found in shop, %s, please check." \
                                                       % (result["msku"], shop_warehouse.default_shop_id.name, shop.name)
                            else:
                                # 没有找到产品, 则记录错误
                                detail_error_message = "MSKU, %s, in shop, %s, is not found, please download shop product data first." \
                                                       % (result["msku"], shop.name)
                                self._connector._raise_connector_error(detail_error_message)
                        else:
                            # 没有找到产品, 则记录错误
                            detail_error_message = "MSKU, %s, in shop, %s, is not found, please download shop product data first." \
                                                   % (result["msku"], shop.name)
                            self._connector._raise_connector_error(detail_error_message)

                        # 由于存在下载的店铺库存中的产品，在下载的店铺产品数据中没有的情况，因此如果没有找到店铺产品，则新增一个。
                        # domain = [
                        #     ("company_id", "=", self._connector.env.company.id),
                        #     ("lingxing_shop_id", "=", result["sid"]),
                        # ]
                        # shop = shop_obj.search(domain, limit=1)
                        #
                        # shop_product_vals = {
                        #     "shop_id": shop.id,
                        #     "seller_sku": result.get("msku"),
                        #     # "product_asin": result.get("asin"),
                        #     "product_fnsku": result.get("fnsku"),
                        #     "shop_product_name": result.get("product_name"),
                        #     "parent_asin": False,
                        #     # "currency_id": shop.currency_id,
                        #     "listing_update_time": False,
                        #     "pair_update_time": False,
                        #     "seller_rank": 0,
                        #     "seller_rank_category": False,
                        #     "review_num": 0,
                        #     "state": "stop",
                        #     "is_deleted": True,
                        # }
                        # shop_product = shop_product_obj.create(shop_product_vals)
                        # key = (shop_product.lingxing_shop_id, shop_product.seller_sku, shop_product.product_fnsku)
                        # self._shop_product_cache.setdefault(key, shop_product)
                        # model_vals["shop_product_id"] = shop_product.id
                        # detail_ext_message = "MSKU, %s, in shop, %s, is a parent sku." % (result["msku"], str(result["sid"]))

                # 如果不是父产品，则需要保存库存数据
                if not is_parent_product:
                    model_vals["shop_product_id"] = shop_product.id
                    model_vals["shop_warehouse_id"] = shop_warehouse.id
                    model_vals["inventory_date"] = self._inventory_date
                    model_vals["is_latest_inventory"] = True
                    model_vals["afn_fulfillable_quantity"] = ActionHandlerTools.cint(result["afn_fulfillable_quantity"])
                    model_vals["reserved_fc_transfers"] = ActionHandlerTools.cint(result["reserved_fc_transfers"])
                    model_vals["reserved_fc_processing"] = ActionHandlerTools.cint(result["reserved_fc_processing"])
                    model_vals["reserved_customerorders"] = ActionHandlerTools.cint(result["reserved_customerorders"])
                    model_vals["total_fulfillable_quantity"] = ActionHandlerTools.cint(result["total_fulfillable_quantity"])
                    model_vals["afn_inbound_shipped_quantity"] = ActionHandlerTools.cint(result["afn_inbound_shipped_quantity"])
                    model_vals["afn_unsellable_quantity"] = ActionHandlerTools.cint(result["afn_unsellable_quantity"])
                    model_vals["afn_inbound_working_quantity"] = ActionHandlerTools.cint(result["afn_inbound_working_quantity"])
                    model_vals["afn_inbound_receiving_quantity"] = ActionHandlerTools.cint(result["afn_inbound_receiving_quantity"])
                    model_vals["afn_erp_real_shipped_quantity"] = ActionHandlerTools.cint(result["afn_erp_real_shipped_quantity"])
                    model_vals["afn_researching_quantity"] = ActionHandlerTools.cint(result["afn_researching_quantity"])
                    model_vals["afn_fulfillable_quantity_multi"] = str(result["afn_fulfillable_quantity_multi"])

                    # 最近是否发生过缺货
                    key = (model_vals["shop_warehouse_id"], model_vals["shop_product_id"])
                    sellable_quantity_history = self._shop_inventory_cache.get(key)
                    sellable_quantity_new = model_vals["afn_fulfillable_quantity"] \
                                            + model_vals["reserved_fc_transfers"] \
                                            + model_vals["reserved_fc_processing"] \
                                            + model_vals["afn_inbound_receiving_quantity"]
                    if not sellable_quantity_history or sellable_quantity_history <= 0 or sellable_quantity_new <= 0:
                        model_vals["is_out_of_stock_occurred"] = True
                    else:
                        model_vals["is_out_of_stock_occurred"] = False

                    shop_inventory = shop_inventory_obj.create(model_vals)

                    if detail_action_state == "warning":
                        self._add_process_result("warning", shop_inventory.id)
                    else:
                        self._add_process_result("created", shop_inventory.id)
                    detail_ext_message = "Data created."

            except ConnectionError as error:
                detail_action_state = "fail"
                detail_ext_message = str(error)
            except Exception as error:
                detail_action_state = "fail"
                detail_error_message = "Some error occurred while processing data: %s." % (result["msku"])
                detail_ext_message = str(error)
            finally:
                if detail_action_state == "fail":
                    self._add_process_result("failed", result["msku"])
                    process_success = False

                # 添加明细行日志
                self._add_log_line(
                    code_ref=result["msku"],
                    name_ref=result["product_name"],
                    action_state=detail_action_state,
                    err_msg=detail_error_message,
                    ext_msg=detail_ext_message,
                    res_id=shop_inventory.id if shop_inventory else False,
                )

        return process_success
