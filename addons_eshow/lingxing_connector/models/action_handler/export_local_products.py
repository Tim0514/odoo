# Copyright 2020-2022 Max Share Technologies
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)

from .action_handler import ActionHandler, ActionHandlerTools


class ExportLocalProducts(ActionHandler):

    def __init__(self, connector, log_book, start_time=None, end_time=None, **kwargs):
        super(ExportLocalProducts, self).__init__(connector, log_book, start_time, end_time, **kwargs)
        self._lx_product_list_cache = False

        # 每次上传的记录数量
        self._request_records_limit = 1000
        self._request_offset = 0
        # 请求参数数据的总数量，初始为负数
        self._request_total = -1


    def _get_export_local_products(self):

        product_obj = self._connector.env["product.product"]

        cursor = self._connector.env.cr

        if self._request_total < 0:
            # 如果是第一次调用本方法，则先查询参数总数量。
            sql = "SELECT count(a.id) FROM product_product AS a " \
                  "JOIN product_template AS c ON a.product_tmpl_id = c.id AND c.sale_ok = TRUE " \
                  "LEFT JOIN connector_data_sync_info b ON a.id = b.res_id AND b.operation_name = '%s' " \
                  "WHERE a.active = TRUE AND (a.write_date > b.last_export_time OR b.last_export_time IS NULL)" \
                  % self._connector.name
            cursor.execute(sql)
            self._request_total = cursor.fetchall()
            self._request_total = self._request_total[0][0]
            self._request_offset = 0
        elif self._has_more_result_data:
            # 如果当前参数还有数据需要继续下载，则直接返回cache中的值
            return self._lx_product_list_cache
        else:
            # 否则，要取得下一页参数
            self._request_offset += self._request_records_limit

        sql = "SELECT a.id FROM product_product AS a " \
              "JOIN product_template AS c ON a.product_tmpl_id = c.id AND c.sale_ok = TRUE " \
              "LEFT JOIN connector_data_sync_info b ON a.id = b.res_id AND b.operation_name = '%s' " \
              "WHERE a.active = TRUE AND (a.write_date > b.last_export_time OR b.last_export_time IS NULL)" \
              % self._connector.name
        cursor.execute(sql)

        product_ids = []

        # 由于每一轮上传数据以后，都会commit connector_data_sync_info数据，
        # 因此每一轮查询都是查询的剩余数据，因此不需要做cursor.scroll动作
        # if self._request_offset < cursor.rowcount:
            # cursor.scroll(self._request_offset, mode='absolute')

        product_ids_temp = cursor.fetchmany(self._request_records_limit)
        for product in product_ids_temp:
            product_ids.append(product[0])

        products = product_obj.browse(product_ids)

        if self._request_offset + len(product_ids) >= self._request_total:
            # 全部数据已经查询出来了
            self._has_more_request_data = False
        else:
            self._has_more_request_data = True

        lx_product_list = []

        for product in products:
            lx_product_dict = {
                "sku": product.default_code,
                "product_name": product.name,
                "unit": product.uom_id.name,
                "status": 1,
                "cg_price": product.standard_price,
                "cg_product_length": round(product.length / 10, 2),
                "cg_product_width": round(product.width / 10, 2),
                "cg_product_height": round(product.height / 10, 2),
                "cg_product_net_weight": round(product.weight * 1000, 2),
                "cg_product_gross_weight": round(product.weight * 1000, 2),
                "cg_package_length": round(product.length / 10, 2),
                "cg_package_width": round(product.width / 10, 2),
                "cg_package_height": round(product.height / 10, 2),
                "odoo_product_id": product.id,
                # "bg_customs_import_price": product.destination_declare_price,
            }
            lx_product_list.append(lx_product_dict)

        self._lx_product_list_cache = lx_product_list

        return lx_product_list

    def prepare_req_body(self):
        req_body = self._get_export_local_products()

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

            product_data = self._lx_product_list_cache[i]

            try:
                if result.code != 0:
                    detail_action_state = "fail"
                    detail_error_message = "%s - %s" % (result.code, result.message)
                    detail_ext_message = str(result.error_details)
                else:
                    self._add_process_result("created", product_data["odoo_product_id"])
                    detail_ext_message = "Data export successfully."
            except Exception as error:
                detail_action_state = "fail"
                detail_error_message = str(error)
            finally:
                if detail_action_state == "fail":
                    self._add_process_result("failed", product_data["odoo_product_id"])
                    process_success = False

                # 添加明细行日志
                self._add_log_line(
                    code_ref=product_data["sku"],
                    name_ref=product_data["product_name"],
                    action_state=detail_action_state,
                    err_msg=detail_error_message,
                    ext_msg=detail_ext_message,
                    res_id=product_data["odoo_product_id"],
                )

            i = i + 1

        return process_success

