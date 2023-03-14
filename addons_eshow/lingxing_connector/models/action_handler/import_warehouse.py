# Copyright 2020-2022 Max Share Technologies
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)

from .action_handler import ActionHandler, AHTools


class ImportWarehouse(ActionHandler):

    def __init__(self, connector, log_book, start_time=None, end_time=None, **kwargs):
        super(ImportWarehouse, self).__init__(connector, log_book, start_time, end_time, **kwargs)

    def prepare_req_body(self):

        # 本调用只有一次，因此一定要设置_has_more_request_data为False，否则会出现死循环
        self._has_more_request_data = False

        req_body = {
            "offset": self._result_offset,
            "length": self._result_records_limit,
        }

        return req_body

    def process_response_result(self):
        """
        self._response_result 有可能是ResponseResult，也有可能是List
        对于特定的Handler，需要对应相应的类型进行处理
        :return: 全部成功，返回True, 出现任何错误，都返回False
        """
        process_success = True

        # todo
        # 本方法尚未完成，不能使用

        shop_obj = self._connector.env["web.sale.shop"]
        marketplace_obj = self._connector.env["web.sale.marketplace"]
        for shop_dict in self._response_result.data:
            detail_action_state = "success"
            detail_error_message = False
            detail_ext_message = False

            shop = False

            try:
                domain = [
                    ('lingxing_shop_id', '=', shop_dict["sid"])
                ]
                shop = shop_obj.search(domain, limit=1)
                if shop:
                    if shop.name != shop_dict["name"] or shop.lingxing_shop_name != shop_dict["name"]:
                        shop.write({
                            "name": shop_dict["name"],
                            "lingxing_shop_name": shop_dict["name"],
                        })
                        self._add_process_result("updated", shop.id)
                        detail_ext_message = "Data updated."
                    else:
                        self._add_process_result("ignored", shop.id)
                        detail_ext_message = "No need to update."
                else:
                    domain = [
                        ('lingxing_marketplace_id', '=', shop_dict["mid"])
                    ]
                    marketplace = marketplace_obj.search(domain, limit=1)
                    if not marketplace:
                        detail_action_state = "fail"
                        detail_error_message = "Marketplace, %s, is not found in database." % (shop_dict["mid"])
                        detail_ext_message = str(shop_dict)
                    else:
                        shop_value = shop_obj._prepare_shop_value(
                            shop_dict["sid"],
                            shop_dict["name"],
                            marketplace.id,
                            shop_dict["seller_id"],
                        )
                        shop = shop_obj.create(shop_value)
                        self._add_process_result("created", shop.id)
                        detail_ext_message = "Data created."
            except Exception as error:
                detail_action_state = "fail"
                detail_error_message = str(error)
            finally:
                if detail_action_state == "fail":
                    self._add_process_result("failed", shop_dict["sid"])
                    process_success = False

                # 添加明细行日志
                self._add_log_line(
                    code_ref=shop_dict["sid"],
                    name_ref=shop_dict["name"],
                    action_state=detail_action_state,
                    err_msg=detail_error_message,
                    ext_msg=detail_ext_message,
                    res_id=shop.id if shop else False,
                )

        return process_success

