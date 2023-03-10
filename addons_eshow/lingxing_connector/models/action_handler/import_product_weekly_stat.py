# Copyright 2020-2022 Max Share Technologies
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)
from dateutil.relativedelta import relativedelta

from .action_handler import ActionHandler, ActionHandlerTools
from datetime import datetime
from dateutil.parser import parse
from dateutil.relativedelta import *
from dateutil.rrule import *


class ImportProductWeeklyStat(ActionHandler):

    def __init__(self, connector, log_book, start_time=None, end_time=None, **kwargs):
        super(ImportProductWeeklyStat, self).__init__(connector, log_book, start_time, end_time, **kwargs)
        self._search_param_list = None
        self._request_records_limit = 1
        self._request_offset = 0
        # 请求参数数据的总数量，初始为负数
        self._request_total = -1

        self._shop_product_asin_cache = {}
        self._shop_cache = {}
        self._product_weekly_stat_cache = {}

        self._init_cache()

    def _init_cache(self):
        shop_product_asin_obj = self._connector.env["web.sale.shop.product.asin"]
        shop_obj = self._connector.env["web.sale.shop"]
        product_weekly_stat_obj = self._connector.env["web.sale.shop.product.weekly.stat"]

        domain = [
            ("enable_exchange_data", "=", True),
        ]
        shops = shop_obj.search(domain)
        for shop in shops:
            key = (shop.lingxing_shop_id,)
            self._shop_cache.setdefault(key, shop)

        # 在shop_product_asin表中查找对应的产品。
        domain = [
            ("shop_id", "in", shops.ids),
        ]
        product_asins = shop_product_asin_obj.search(domain)
        for line in product_asins:
            key = (line.shop_id.lingxing_shop_id, line.product_asin)
            self._shop_product_asin_cache.setdefault(key, line)

        domain = [
            ("shop_id", "in", shops.ids),
        ]
        product_weekly_stat = product_weekly_stat_obj.search(domain)
        for line in product_weekly_stat:
            key = (line.shop_id.id, line.product_asin, line.stat_year, line.stat_week)
            self._product_weekly_stat_cache.setdefault(key, line)

    def _get_search_params(self):
        if self._request_total < 0:
            start_week_calendar = self._data_start_time.isocalendar()
            end_week_calendar = self._data_end_time.isocalendar()
            self._data_start_time = datetime.fromisocalendar(start_week_calendar[0], start_week_calendar[1], 1)
            # 由于rrule生成列表时，最后一周会多生成一条数据，因此把结束天数扣掉1天。
            self._data_end_time = datetime.fromisocalendar(end_week_calendar[0], end_week_calendar[1], 1) - relativedelta(days=1)

            week_list = list(rrule(WEEKLY, dtstart=self._data_start_time, until=self._data_end_time))

            # 如果周数小于4，则最少取4周数据。
            total_weeks = len(week_list)
            total_weeks = total_weeks if total_weeks > 2 else 2

            self._data_start_time = self._data_end_time - relativedelta(weeks=total_weeks, days=-1)
            week_list = list(rrule(WEEKLY, dtstart=self._data_start_time, count=total_weeks))

            web_shop_obj = self._connector.env["web.sale.shop"]
            domain = [
                ("enable_exchange_data", "=", True)]

            shop_list = web_shop_obj.search(domain, order="lingxing_shop_id")

            search_params_list = []
            for start_date in week_list:
                for shop in shop_list:
                    end_date = start_date + relativedelta(days=7)
                    search_params = {
                        "sid": shop.lingxing_shop_id,
                        "start_date": start_date.strftime('%Y-%m-%d'),
                        "end_date": end_date.strftime('%Y-%m-%d'),
                    }
                    search_params_list.append(search_params)
            # 如果是第一次调用本方法，则先查询参数总数量。
            self._request_total = len(search_params_list)
            self._search_param_list = search_params_list
            self._request_offset = 0
        elif not self._has_more_result_data:
            # 如果当前参数没有有数据需要继续下载，则取得下一页参数
            self._request_offset += self._request_records_limit

        if self._request_offset + self._request_records_limit >= self._request_total:
            self._has_more_request_data = False
        else:
            self._has_more_request_data = True

        return self._search_param_list[self._request_offset]

    def prepare_req_body(self):

        search_params = self._get_search_params()

        req_body = {
            "sid": search_params["sid"],
            "asin_type": 0,
            "start_date": search_params["start_date"],
            "end_date": search_params["end_date"],
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

        product_weekly_stat_obj = self._connector.env["web.sale.shop.product.weekly.stat"]

        key = (self._search_param_list[self._request_offset]["sid"],)
        shop = self._shop_cache.get(key)

        process_success = True

        for result in self._response_result.data:
            detail_action_state = "success"
            detail_error_message = False
            detail_ext_message = False

            # product_weekly_stat, 如果中途出错，则为False
            product_weekly_stat = False

            # 对每一行数据都捕捉错误，记录LOG
            try:
                # 创建新的product_vals 用于创建或更新产品信息
                model_vals = {}

                model_vals["product_asin"] = result["asin"]

                model_vals["shop_id"] = shop.id

                # 在shop_product_asin表中查找对应的产品。
                key = (result["sid"], result["asin"])
                product_asin = self._shop_product_asin_cache.get(key)
                if product_asin:
                    model_vals["product_asin_id"] = product_asin.id
                else:
                    detail_error_message = "ASIN, %s, in shop, %s, is not found in shop product asin database." \
                                           % (result["asin"], shop.name)
                    self._connector._raise_connector_error(detail_error_message)

                model_vals["start_date"] = parse(self._search_param_list[self._request_offset]["start_date"])
                model_vals["end_date"] = parse(self._search_param_list[self._request_offset]["end_date"])

                model_vals["stat_year"] = model_vals["start_date"].isocalendar()[0]
                model_vals["stat_week"] = model_vals["start_date"].isocalendar()[1]

                # date_modified = parse(result["gmt_modified"] + " GMT")
                # date_modified = date_modified.astimezone(tz=tzlocal())
                # date_modified_naive = date_modified.replace(tzinfo=None)
                # model_vals["date_modified_gmt"] = date_modified_naive

                model_vals["date_modified_gmt"] = parse(result["gmt_modified"])

                model_vals["order_volume"] = ActionHandlerTools.cint(result["order_items"])
                model_vals["product_volume"] = ActionHandlerTools.cint(result["volume"])
                model_vals["amount_total"] = ActionHandlerTools.cfloat(result["amount"])
                model_vals["session_browser"] = ActionHandlerTools.cint(result["sessionsBrowser"])
                model_vals["session_mobile"] = ActionHandlerTools.cint(result["sessionsMobile"])
                model_vals["session_total"] = ActionHandlerTools.cint(result["sessionsTotal"])
                model_vals["page_view_browser"] = ActionHandlerTools.cint(result["PVBrowser"])
                model_vals["page_view_mobile"] = ActionHandlerTools.cint(result["PVMobile"])
                model_vals["page_view_total"] = ActionHandlerTools.cint(result["PVTotal"])
                model_vals["ads_clicks"] = ActionHandlerTools.cint(result["clicks"])
                model_vals["ads_impressions"] = ActionHandlerTools.cint(result["impressions"])
                model_vals["ads_total_spend"] = ActionHandlerTools.cfloat(result["total_spend"])
                model_vals["ads_click_rate"] = ActionHandlerTools.cfloat(result["ctr"])
                model_vals["ads_avg_cpc"] = ActionHandlerTools.cfloat(result["avg_cpc"])
                model_vals["ads_order_volume"] = ActionHandlerTools.cint(result["order_quantity"])
                model_vals["ads_order_rate"] = ActionHandlerTools.cfloat(result["adv_rate"])
                model_vals["ads_amount_total"] = ActionHandlerTools.cfloat(result["sales_amount"])
                model_vals["ads_cvr"] = ActionHandlerTools.cfloat(result["ad_cvr"])
                model_vals["acos"] = ActionHandlerTools.cfloat(result["acos"])
                model_vals["acoas"] = ActionHandlerTools.cfloat(result["acoas"])
                model_vals["asoas"] = ActionHandlerTools.cfloat(result["asoas"])
                model_vals["ads_convention_rate"] = ActionHandlerTools.cfloat(result["conversion_rate"])
                model_vals["total_convention_rate"] = ActionHandlerTools.cfloat(result["total_spend_rate"])
                model_vals["seller_rank"] = ActionHandlerTools.cint(result["rank"])

                for i in range(0, min(3, len(result["smallRankList"]))):
                    sub_seller_rank = result["smallRankList"][i]
                    if i == 0:
                        model_vals["seller_rank_sub1"] = sub_seller_rank["rankValue"]
                        model_vals["seller_rank_sub1_name"] = sub_seller_rank["smallRankName"]
                    elif i == 1:
                        model_vals["seller_rank_sub2"] = sub_seller_rank["rankValue"]
                        model_vals["seller_rank_sub2_name"] = sub_seller_rank["smallRankName"]
                    elif i == 2:
                        model_vals["seller_rank_sub3"] = sub_seller_rank["rankValue"]
                        model_vals["seller_rank_sub3_name"] = sub_seller_rank["smallRankName"]

                model_vals["review_num"] = ActionHandlerTools.cint(result["reviews"])
                model_vals["review_star"] = ActionHandlerTools.cfloat(result["avg_star"])
                model_vals["remark"] = str(result["remark"])

                key = (model_vals["shop_id"], model_vals["product_asin"], model_vals["stat_year"], model_vals["stat_week"],)
                product_weekly_stat = self._product_weekly_stat_cache.get(key)
                if product_weekly_stat:
                    if self._compare_values(product_weekly_stat, model_vals) == 0:
                        self._add_process_result("ignored", product_weekly_stat.id)
                        detail_ext_message = "No change in data, ignored."
                    else:
                        # 已经存在，则更新。
                        product_weekly_stat.write(model_vals)
                        self._add_process_result("updated", product_weekly_stat.id)
                        detail_ext_message = "Data updated."
                else:
                    # 否则创建
                    product_weekly_stat = product_weekly_stat_obj.create(model_vals)
                    self._add_process_result("created", product_weekly_stat.id)
                    detail_ext_message = "Data created."

            except ConnectionError as error:
                detail_action_state = "fail"
                detail_ext_message = str(error)
            except Exception as error:
                detail_action_state = "fail"
                detail_error_message = "Some error occurred while processing product: %s." % (result["asin"])
                detail_ext_message = str(error)
            finally:
                if detail_action_state == "fail":
                    self._add_process_result("failed", result["asin"])
                    process_success = False

                # 添加明细行日志
                self._add_log_line(
                    code_ref=result["asin"],
                    name_ref=result["item_name"],
                    action_state=detail_action_state,
                    err_msg=detail_error_message,
                    ext_msg=detail_ext_message,
                    res_id=product_weekly_stat.id if product_weekly_stat else False,
                )

        return process_success

    def _compare_values(self, product_weekly_stat, model_vals):
        fields = ["order_volume", "product_volume", "amount_total", "session_browser", "session_mobile",
                  "session_total", "page_view_browser", "page_view_mobile", "page_view_total", "ads_clicks",
                  "ads_impressions", "ads_total_spend", "ads_click_rate", "ads_avg_cpc", "ads_order_volume",
                  "ads_order_rate", "ads_amount_total", "ads_cvr", "acos", "acoas", "asoas",
                  "ads_convention_rate", "total_convention_rate"]
        compare_val1 = product_weekly_stat.read(fields)[0]

        compare_val2 = {}
        for field in fields:
            compare_val2.setdefault(field, model_vals[field])

        return compare_val1 == compare_val2