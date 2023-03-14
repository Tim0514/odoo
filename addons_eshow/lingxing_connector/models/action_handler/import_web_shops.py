# Copyright 2020-2022 Max Share Technologies
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)

from .action_handler import ActionHandler, AHTools
from odoo import _

class ImportAmazonShops(ActionHandler):

    def __init__(self, connector, log_book, start_time=None, end_time=None, **kwargs):
        super(ImportAmazonShops, self).__init__(connector, log_book, start_time, end_time, **kwargs)

    def prepare_req_body(self):

        # 本调用只有一次，因此一定要设置_has_more_request_data为False，否则会出现死循环
        self._has_more_request_data = False

        req_body = {}
        return req_body

    def process_response_result(self):
        """
        self._response_result 有可能是ResponseResult，也有可能是List
        对于特定的Handler，需要对应相应的类型进行处理
        :return: 全部成功，返回True, 出现任何错误，都返回False
        """
        process_success = True

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
                    shop.write({
                        "name": shop_dict["name"],
                        "lingxing_shop_name": shop_dict["name"],
                    })
                    if shop.company_id:
                        if not shop.partner_id:
                            domain = [
                                ("company_id", "=", shop.company_id.id),
                                ("name", "=", shop.name),
                            ]
                            partner = self._connector.env["res.partner"].search(domain, limit=1)
                            if partner:
                                if partner.web_shop_id and partner.web_shop_id != shop:
                                    detail_action_state = "warning"
                                    detail_error_message = _(
                                        "The partner with same name has been linked to another shop, please check.\n Shop Name: %S") % shop.name
                                    detail_ext_message = False
                                    self._add_process_result(detail_action_state, shop.id)
                                else:
                                    shop.partner_id = partner
                                    partner.is_web_shop = True
                                    partner.web_shop_id = shop
                                    detail_action_state = "updated"
                                    detail_ext_message = _("Data updated.")
                                    self._add_process_result(detail_action_state, shop.id)
                            else:
                                partner_vals = {
                                    "company_id": shop.company_id.id,
                                    "company_type": "company",
                                    "name": shop.name,
                                    "is_web_shop": True,
                                    "web_shop_id": shop.id,
                                }
                                partner = self._connector.env["res.partner"].create(partner_vals)
                                shop.partner_id = partner
                                detail_action_state = "updated"
                                detail_ext_message = _("Related partner created.")
                                self._add_process_result(detail_action_state, shop.id)
                        else:
                            if shop.partner_id.company_id != shop.company_id:
                                shop.partner_id.company_id = shop.company_id
                            shop.partner_id.web_shop_id = shop
                            detail_action_state = "updated"
                            detail_ext_message = _("Data updated.")
                            self._add_process_result(detail_action_state, shop.id)
                    else:
                        detail_action_state = "warning"
                        detail_error_message = _(
                            "Shop, %s, is update, but you must set its company manually before using.") % shop.name
                        detail_ext_message = False
                        self._add_process_result(detail_action_state, shop.id)
                else:
                    domain = [
                        ('lingxing_marketplace_id', '=', shop_dict["mid"])
                    ]
                    marketplace = marketplace_obj.search(domain, limit=1)
                    if not marketplace:
                        detail_action_state = "failed"
                        detail_error_message = _("Marketplace, %s, is not found in database.") % (shop_dict["mid"])
                        detail_ext_message = str(shop_dict)
                        self._add_process_result(detail_action_state, shop_dict["sid"])
                    else:
                        shop_value = shop_obj._prepare_shop_value(
                            shop_dict["sid"],
                            shop_dict["name"],
                            marketplace.id,
                            shop_dict["seller_id"],
                        )
                        shop = shop_obj.create(shop_value)

                        detail_action_state = "warning"
                        detail_error_message = _(
                            "Shop, %s, is created, but you must set its company manually before using") % shop.name
                        detail_ext_message = False
                        self._add_process_result(detail_action_state, shop.id)
            except Exception as error:
                detail_action_state = "failed"
                detail_error_message = str(error)
            finally:
                if detail_action_state == "failed":
                    process_success = False
                    self._add_process_result(detail_action_state, shop_dict["sid"])

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


class ImportMultiplatformShops(ActionHandler):

    def __init__(self, connector, log_book, start_time=None, end_time=None, **kwargs):
        super(ImportMultiplatformShops, self).__init__(connector, log_book, start_time, end_time, **kwargs)
        self._result_records_limit = 200
        # self._has_more_result_data = True

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

        shop_obj = self._connector.env["web.sale.shop"]
        marketplace_obj = self._connector.env["web.sale.marketplace"]
        for shop_dict in self._response_result.data["list"]:
            detail_action_state = "success"
            detail_error_message = False
            detail_ext_message = False

            shop = False

            try:
                if shop_dict["platform_code"] == "10001":
                    # 如果是亚马逊店铺，则仅更新店铺的store_id(长字符串)
                    domain=[
                        ("name", "=", shop_dict["store_name"]),
                    ]
                    shop = shop_obj.search(domain, limit=1)
                    if shop:
                        shop.write({"lingxing_mp_shop_id": shop_dict["store_id"]})
                    detail_action_state = "ignored"
                    detail_error_message = _("%s is an amazon shop.") % shop_dict["store_name"]
                    detail_ext_message = False
                    self._add_process_result(detail_action_state, shop_dict["store_id"])
                    continue

                domain = [
                    ('lingxing_mp_shop_id', '=', shop_dict["store_id"])
                ]
                shop = shop_obj.search(domain, limit=1)
                if shop:
                    shop.write({
                        "name": shop_dict["store_name"],
                        "lingxing_shop_name": shop_dict["store_name"],
                    })
                    if shop.company_id:
                        if not shop.partner_id:
                            domain = [
                                ("company_id", "=", shop.company_id.id),
                                ("name", "=", shop.name),
                            ]
                            partner = self._connector.env["res.partner"].search(domain, limit=1)
                            if partner:
                                if partner.web_shop_id and partner.web_shop_id != shop:
                                    detail_action_state = "warning"
                                    detail_error_message = _(
                                        "The partner with same name has been linked to another shop, please check.\n Shop Name: %S") % shop.name
                                    detail_ext_message = False
                                    self._add_process_result(detail_action_state, shop.id)
                                else:
                                    shop.partner_id = partner
                                    partner.is_web_shop = True
                                    partner.web_shop_id = shop
                                    detail_action_state = "updated"
                                    detail_ext_message = _("Data updated.")
                                    self._add_process_result(detail_action_state, shop.id)
                            else:
                                partner_vals = {
                                    "company_id": shop.company_id.id,
                                    "company_type": "company",
                                    "name": shop.name,
                                    "is_web_shop": True,
                                    "web_shop_id": shop.id,
                                }
                                partner = self._connector.env["res.partner"].create(partner_vals)
                                shop.partner_id = partner
                                detail_action_state = "updated"
                                detail_ext_message = _("Related partner created.")
                                self._add_process_result(detail_action_state, shop.id)
                        else:
                            if shop.partner_id.company_id != shop.company_id:
                                shop.partner_id.company_id = shop.company_id
                            shop.partner_id.web_shop_id = shop
                            detail_action_state = "updated"
                            detail_ext_message = _("Data updated.")
                            self._add_process_result(detail_action_state, shop.id)
                    else:
                        detail_action_state = "warning"
                        detail_error_message = _(
                            "Shop, %s, is update, but you must set its company manually before using.") % shop.name
                        detail_ext_message = False
                        self._add_process_result(detail_action_state, shop.id)
                else:
                    domain = [
                        ('lingxing_marketplace_id', '=', AHTools.cint(shop_dict["platform_code"]))
                    ]
                    marketplace = marketplace_obj.search(domain, limit=1)
                    if not marketplace:
                        detail_action_state = "failed"
                        detail_error_message = _("Marketplace, %s, is not found in database.") % (shop_dict["platform_name"])
                        detail_ext_message = str(shop_dict)
                        self._add_process_result(detail_action_state, shop_dict["store_id"])
                        continue

                    shop_value = {
                        "name": shop_dict["store_name"],
                        "lingxing_mp_shop_id": shop_dict["store_id"],
                        "lingxing_shop_name": shop_dict["store_name"],
                        "marketplace_id": marketplace.id,
                    }
                    shop = shop_obj.create(shop_value)

                    # 由于不知道店铺是属于哪家公司的，因此新建店铺的时候，不匹配公司。需要手动设置公司以后才可以建立partner

                    detail_action_state = "warning"
                    detail_error_message = _("Shop, %s, is created, but you must set its company manually before using") % shop.name
                    detail_ext_message = False
                    self._add_process_result(detail_action_state, shop.id)

            except Exception as error:
                detail_action_state = "failed"
                detail_error_message = str(error)
            finally:
                if detail_action_state == "failed":
                    process_success = False
                    self._add_process_result(detail_action_state, shop_dict["store_id"])

                # 添加明细行日志
                self._add_log_line(
                    code_ref=shop_dict["store_id"],
                    name_ref=shop_dict["store_name"],
                    action_state=detail_action_state,
                    err_msg=detail_error_message,
                    ext_msg=detail_ext_message,
                    res_id=shop.id if shop else False,
                )

        return process_success

