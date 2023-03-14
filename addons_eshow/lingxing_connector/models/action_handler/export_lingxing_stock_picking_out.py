# Copyright 2020-2022 Max Share Technologies
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)
import datetime

from .action_handler import ActionHandler, AHTools
from datetime import datetime

class ExportLingxingStockPickingOut(ActionHandler):

    def __init__(self, connector, log_book, start_time=None, end_time=None, **kwargs):
        super(ExportLingxingStockPickingOut, self).__init__(connector, log_book, start_time, end_time, **kwargs)
        self._request_records_limit = 1000
        self._request_offset = 0
        # 请求参数数据的总数量，初始为负数
        self._request_total = -1

        self._lx_picking_list_cache = None

        self._lx_picking_current_request_list_cache = None


    def prepare_req_body(self):

        if self._request_total < 0:
            self._lx_picking_list_cache = []
            #第一次调用
            lx_stock_picking_obj = self._connector.env["web.sale.lx.stock.picking"]

            domain = [
                ("is_synchronized", "=", False),
                ("lx_picking_type", "in", ["11", "12", "14"]),
            ]
            lx_pickings = lx_stock_picking_obj.search(domain)
            self._lx_picking_list_cache = lx_pickings

            self._request_total = len(self._lx_picking_list_cache)
            self._request_offset = 0
        else:
            # 取得下一页参数的offset
            self._request_offset += self._request_records_limit


        if self._request_offset + self._request_records_limit >= self._request_total:
            end_offset = self._request_total
            self._has_more_request_data = False
        else:
            end_offset = self._request_offset + self._request_records_limit
            self._has_more_request_data = True

        self._lx_picking_current_request_list_cache = self._lx_picking_list_cache[self._request_offset: end_offset]

        req_list = []
        for lx_picking in self._lx_picking_current_request_list_cache:
            lx_picking_dict = {
                "sys_wid": lx_picking.lx_warehouse_id,
                "type": int(lx_picking.lx_picking_type),
                "sys_supplier_id": lx_picking.lx_supplier_id,
                "remark": lx_picking.related_shipment_sn,
            }
            lx_move_list = []
            for lx_move in lx_picking.lx_stock_move_ids:
                lx_move_dict = {
                    "sku": lx_move.default_code,
                    "good_num": abs(lx_move.product_qty),
                    "bad_num": 0,
                    "price": lx_move.price_unit,
                    "seller_id": 0,
                    "fnsku": "",
                }
                lx_move_list.append(lx_move_dict)
            lx_picking_dict.setdefault("product_list", lx_move_list)
            req_list.append(lx_picking_dict)

        req_body = req_list

        return req_body

    def process_response_result(self):
        """
        self._response_result 有可能是ResponseResult，也有可能是List
        对于特定的Handler，需要对应相应的类型进行处理
        :return: 全部成功，返回True, 出现任何错误，都返回False
        """
        process_success = True
        i = 0
        for result in self._response_result:
            detail_action_state = "success"
            detail_error_message = False
            detail_ext_message = False

            lx_picking = self._lx_picking_current_request_list_cache[i]

            try:
                if result.code != 0:
                    detail_action_state = "fail"
                    detail_error_message = "%s - %s" % (result.code, result.message)
                    detail_ext_message = str(result.error_details)
                else:
                    order_sn = result.data["order_sn"]
                    lx_picking.write({
                        "name": order_sn,
                        "is_synchronized": True,
                        "sync_time": datetime.now(),
                    })
                    self._add_process_result("created", lx_picking.id)
                    detail_ext_message = "Data export successfully."
            except Exception as error:
                detail_action_state = "fail"
                detail_error_message = str(error)
            finally:
                if detail_action_state == "fail":
                    self._add_process_result("failed", lx_picking.id)
                    process_success = False

                # 添加明细行日志
                self._add_log_line(
                    code_ref=lx_picking.id,
                    name_ref=lx_picking.name,
                    action_state=detail_action_state,
                    err_msg=detail_error_message,
                    ext_msg=detail_ext_message,
                    res_id=lx_picking.id,
                )

            i = i + 1

        return process_success

