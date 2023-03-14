# Copyright 2020-2022 Max Share Technologies
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)
from dateutil.relativedelta import relativedelta

from .action_handler import ActionHandler, AHTools
from datetime import datetime
from dateutil.parser import parse
from dateutil.relativedelta import *
from dateutil.rrule import *
from odoo.tools import date_utils
from odoo import _

class ImportFbaShipments(ActionHandler):

    def __init__(self, connector, log_book, start_time=None, end_time=None, operation="get_draft_shipments", **kwargs):
        """

        :param connector:
        :param log_book:
        :param start_time:
        :param end_time:
        :param operation: get_draft_shipments/get_shipped_shipments/get_scraped_shipments
        :param kwargs:
        """
        super(ImportFbaShipments, self).__init__(connector, log_book, start_time, end_time, **kwargs)

        default_start_time = datetime.now() - relativedelta(months=3)
        if not start_time or default_start_time < start_time:
            self._data_start_time = default_start_time

        # 默认读取状态为待配货的发货单
        self._operation = "get_draft_shipments"

        if operation == "get_shipped_shipments" or operation == "get_scraped_shipments":
            self._operation = operation

        # 查询条件中的shop_ids缓存
        self._shop_ids_cache = None

        self._shop_cache = {}
        self._shop_product_cache = {}
        self._shipping_method_cache = {}
        self._stock_picking_cache = {}

        self._init_cache()

    def _init_cache(self):
        shop_obj = self._connector.env["web.sale.shop"]
        shop_product_obj = self._connector.env["web.sale.shop.product"]
        stock_picking_obj = self._connector.env["stock.picking"]

        domain = [
            ("enable_exchange_data", "=", True),
            ("marketplace_id.type", "=", "amazon"),
        ]
        shops = shop_obj.search(domain)
        for shop in shops:
            key = (shop.lingxing_shop_id,)
            self._shop_cache.setdefault(key, shop)

        domain = [
            ("shop_id", "in", shops.ids),
            # ("shop_product_state", "!=", "stop"),
        ]
        shop_products = shop_product_obj.search(domain)
        for shop_product in shop_products:
            key = (shop_product.lingxing_shop_id, shop_product.seller_sku)
            if self._shop_product_cache.get(key):
                detail_error_message = "Found more than one record for MSKU, %s, in shop, %s in shop product database.  " \
                                       "You must archive all useless shop products." % (shop_product.seller_sku, shop_product.shop_name)
                self._connector._raise_connector_error(detail_error_message)
            self._shop_product_cache.setdefault(key, shop_product)

        domain = [
            ("lx_shipment_sn", "!=", False),
            ("create_date", ">=", self._data_start_time),
        ]
        stock_pickings = stock_picking_obj.search(domain)
        for line in stock_pickings:
            key = (line.lx_shipment_sn,)
            self._stock_picking_cache.setdefault(key, line)

        domain = [
        ]
        shipping_methods = self._connector.env["web.sale.shipping.method"].search(domain)
        for line in shipping_methods:
            key = (line.name,)
            self._shipping_method_cache.setdefault(key, line)

    def prepare_req_body(self):

        if not self._shop_ids_cache:
            web_shop_obj = self._connector.env["web.sale.shop"]
            domain = [
                ("enable_exchange_data", "=", True),
                ("marketplace_id.type", "=", "amazon"),
            ]
            shop_list = web_shop_obj.search(domain, order="lingxing_shop_id")
            self._shop_ids_cache = shop_list.ids

        if self._operation == "get_shipped_shipments":
            req_body = {
                "sid": self._shop_ids_cache,
                "time_type": 0,
                "start_date": self._data_start_time.strftime('%Y-%m-%d %H:%M:%S'),
                "offset": self._result_offset,
                "length": self._result_records_limit,
            }
        elif self._operation == "get_scraped_shipments":
            req_body = {
                "sid": self._shop_ids_cache,
                "time_type": 2,
                "start_date": self._data_start_time.strftime('%Y-%m-%d %H:%M:%S'),
                "offset": self._result_offset,
                "length": self._result_records_limit,
            }
        else:
            # 默认读取所有 待配货的发货单
            req_body = {
                "sid": self._shop_ids_cache,
                "status": -1,
                "offset": self._result_offset,
                "length": self._result_records_limit,
            }

        self._has_more_request_data = False

        return req_body

    def set_result(self, response_result):
        """
        重载本方法
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

    def process_response_result(self):
        """
        self._response_result 有可能是ResponseResult，也有可能是List
        对于特定的Handler，需要对应相应的类型进行处理
        :return: 全部成功，返回True, 出现任何错误，都返回False
        """
        process_success = True

        stock_picking = None

        for result in self._response_result.data["list"]:
            detail_action_state = "success"
            detail_error_message = False
            detail_ext_message = False

            # 对每一行数据都捕捉错误，记录LOG
            try:
                # if result["shipment_sn"] != "SP230224001":
                #     detail_action_state = "warning"
                #     detail_error_message = "Debug Purpose"
                #     detail_ext_message = False
                #     self._add_process_result("ignored", result["id"])
                #     continue

                # 如果备注里有 准备配货/准备发货 文字，才认为需要通过Odoo系统来推送领星的入库单。
                # 否则，如果状态是 -1(待配货)，3（作废）则不新建Odoo出库单。
                # 如果不是 -1,3, 则直接新建一张状态为Done的出库单，并且不发生实际的出库。也不推送领星入库单。
                #
                if self._is_ready(result["remark"]):
                    key = (result["shipment_sn"],)
                    stock_picking = self._stock_picking_cache.get(key)
                    if stock_picking:
                        stock_picking, detail_action_state, detail_error_message, detail_ext_message = self._update_stock_picking(
                            result)
                    else:
                        # 只对待发货、已发货的领星发货单创建Odoo 发货单
                        stock_picking, detail_action_state, detail_error_message, detail_ext_message = self._create_stock_picking(
                            result)
                else:
                    if result["status"] in [1,2]:
                        key = (result["shipment_sn"],)
                        stock_picking = self._stock_picking_cache.get(key)
                        if stock_picking:
                            stock_picking, detail_action_state, detail_error_message, detail_ext_message = self._update_stock_picking(result, without_actual_move=True)
                        else:
                            stock_picking, detail_action_state, detail_error_message, detail_ext_message = self._create_stock_picking(result, without_actual_move=True)
                    else:
                        # result["status"] in [-1,0,3] 不导入
                        detail_action_state = "ignored"
                        # detail_error_message = "尚未备注‘准备配货’的待配货出库单，暂时不导入"
                        detail_error_message = _("Will not import shipments in state [to_packing,to_shipping,cancel] without word, 'ready', in remark. SN: %s") \
                            % result["shipment_sn"]
                        detail_ext_message = False

                if detail_action_state == "warning":
                    self._add_process_result("warning", result["id"])
                elif detail_action_state == "ignored":
                    self._add_process_result("ignored", result["id"])
                else:
                    self._add_process_result("updated", result["id"])
                    detail_ext_message = "Data updated."

            except ConnectionError as error:
                detail_action_state = "failed"
                detail_ext_message = str(error)
            except Exception as error:
                detail_action_state = "failed"
                detail_error_message = _("Some error occurred while processing shipment data: %s.") % (result["shipment_sn"])
                detail_ext_message = str(error)
            finally:
                if detail_action_state == "failed":
                    self._add_process_result("failed", result["id"])
                    process_success = False
                # 添加明细行日志
                self._add_log_line(
                    code_ref=result["id"],
                    name_ref=result["shipment_sn"],
                    action_state=detail_action_state,
                    err_msg=detail_error_message,
                    ext_msg=detail_ext_message,
                    res_id=stock_picking.id if stock_picking else False,
                )

        return process_success

    def _is_ready(self, remark):
        # 从remark中判断该出库单是否可以准备配货
        keyword_list = ["ready", "准备配货", "准备发货"]
        remark = remark.lower()

        for keyword in keyword_list:
            if remark.find(keyword) >= 0:
                return True
        return False

    def _create_stock_picking(self, result, without_actual_move=False):
        if len(result["relate_list"]) > 0:
            key = (result["relate_list"][0]["sid"],)
            shop = self._shop_cache.get(key)
        else:
            detail_action_state = "ignored"
            detail_error_message = _("There is no products in LX Shipment. \nShipment SN: %s") \
                                   % (result["shipment_sn"])
            detail_ext_message = False
            return None, detail_action_state, detail_error_message, detail_ext_message

        # 创建新的product_vals 用于创建或更新产品信息
        model_vals = {}
        model_vals["company_id"] = shop.company_id.id
        model_vals["partner_id"] = shop.partner_id.id
        model_vals["move_type"] = "direct"
        model_vals["location_id"] = shop.company_id.warehouse_id.lot_stock_id.id
        model_vals["location_dest_id"] = shop.partner_id.property_stock_customer.id
        model_vals["picking_type_id"] = shop.company_id.warehouse_id.out_type_id.id
        if result["shipment_time"] == "":
            model_vals["scheduled_date"] = parse(result["create_time"])
        else:
            model_vals["scheduled_date"] = parse(result["shipment_time"])
        model_vals["date"] = parse(result["create_time"])
        model_vals["lx_logistics_channel_name"] = result["logistics_channel_name"]
        model_vals["lx_shipment_id"] = result["id"]
        model_vals["name"] = result["shipment_sn"]
        model_vals["lx_shipment_sn"] = result["shipment_sn"]
        if result["delivery_date"] != "":
            model_vals["delivery_date"] = parse(result["delivery_date"])
        model_vals["lx_state"] = str(result["status"])
        model_vals["lx_update_time"] = parse(result["update_time"])
        model_vals["lx_remark"] = result["remark"]
        model_vals["lx_warehouse_id"] = result["wid"]

        fba_shipment_id_list = []
        for line in result["relate_list"]:
            if line["shipment_id"] not in fba_shipment_id_list:
                fba_shipment_id_list.append(line["shipment_id"])
        model_vals["origin"] = ",".join(fba_shipment_id_list)

        if result["logistics_channel_name"] and result["logistics_channel_name"] != None:
            key = (result["logistics_channel_name"],)
            shipping_method = self._shipping_method_cache.get(key)
            if shipping_method:
                model_vals["shipping_method"] = shipping_method.id

        stock_picking = self._connector.env["stock.picking"].create(model_vals)

        model_lines = result["relate_list"]

        line_list = []
        for line in model_lines:
            line_vals = self._prepare_stock_move_vals(stock_picking, result, line, without_actual_move=False)
            line_list.append(line_vals)

        self._connector.env["stock.move"].create(line_list)

        if self._is_ready(result["remark"]):
            self._create_lx_stock_picking(stock_picking)

        picking_state = self._confirm_stock_picking(stock_picking, result)
        if picking_state == "draft":
            detail_action_state = "created"
            detail_error_message = _("Odoo picking, %s, is in draft state.") % (result["shipment_sn"])
            detail_ext_message = False
        elif picking_state == "done":
            detail_action_state = "created"
            detail_error_message = _("Odoo picking, %s, is completed.") % (result["shipment_sn"])
            detail_ext_message = False
        elif picking_state == "cancel":
            detail_action_state = "created"
            detail_error_message = _("Odoo picking, %s, has been canceled.") % (result["shipment_sn"])
            detail_ext_message = False
        else:
            detail_action_state = "warning"
            detail_error_message = _(
                "LX Shipment state is done, but Odoo picking can not be completed because stock is not enough, please complete related MOs. \nShipment SN: %s") \
                                   % (result["shipment_sn"])
            detail_ext_message = False

        return stock_picking, detail_action_state, detail_error_message, detail_ext_message

    def _prepare_stock_move_vals(self, stock_picking, result, line, without_actual_move=False):
        key = (line["sid"],)
        shop = self._shop_cache.get(key)

        line_vals = {}
        line_vals["date"] = stock_picking.scheduled_date
        line_vals["company_id"] = stock_picking.company_id.id

        key = (line.get("sid"), line.get("msku"))
        shop_product = self._shop_product_cache.get(key)

        if shop_product:
            if shop_product.product_id:
                line_vals["product_id"] = shop_product.product_id.id
                line_vals["name"] = shop_product.seller_sku
                line_vals["description_picking"] = shop_product.seller_sku
            else:
                detail_error_message = _("Product, %s, in shop, %s, has not been paired.") \
                                       % (line.get("msku"), shop.name)
                self._connector._raise_connector_error(detail_error_message)
        else:
            detail_error_message = _("Product, %s, in shop, %s, is not found or has been stopped selling.") \
                                   % (line.get("msku"), shop.name)
            self._connector._raise_connector_error(detail_error_message)

        line_vals["product_uom_qty"] = line["num"]
        line_vals["product_uom"] = shop_product.product_id.uom_id.id
        line_vals["location_id"] = stock_picking.location_id.id
        line_vals["location_dest_id"] = stock_picking.location_dest_id.id
        line_vals["partner_id"] = stock_picking.partner_id.id
        line_vals["picking_id"] = stock_picking.id

        if result["status"] in [3, ]:
            line_vals["state"] = "cancel"
        else:
            line_vals["state"] = "draft"

        # 对于备注里没有“准备发货”等文字的发货单，并且状态为已发货或已完成的，则直接将move的状态设置为confirmed
        if without_actual_move and result["status"] in [1, 2]:
            line_vals["state"] = "done"

        line_vals["price_unit"] = shop_product.product_id.standard_price
        line_vals["shop_product_id"] = shop_product.id
        line_vals["lx_shipment_line_id"] = line["id"]
        line_vals["fba_shipment_id"] = line["shipment_id"]

        return line_vals

    def _update_stock_picking(self, result, without_actual_move=False):
        key = (result["shipment_sn"],)
        stock_picking = self._stock_picking_cache.get(key)

        # if (result["status"] in [-1, 0] and stock_picking.state != "draft") \
        #         or (result["status"] in [1, ] and stock_picking.state not in ["done"]):
        if result["status"] in [-1] and stock_picking.state != "draft":
            # 如果因为某些原因，领星的发货单仍然是待配货状态，但Odoo的发货单却不是草稿状态
            # 则先把Odoo的发货单状态设置为草稿。
            if stock_picking.state == "done":
                stock_picking.move_lines.state = "assigned"
            stock_picking.action_cancel()
            stock_picking.is_locked = False
            stock_picking.move_lines.state = "draft"

        model_vals = {}

        # 首先是不管什么状态都可以更新的数据：
        model_vals["lx_logistics_channel_name"] = result["logistics_channel_name"]
        if result["delivery_date"] != "":
            model_vals["delivery_date"] = parse(result["delivery_date"])
        model_vals["lx_state"] = str(result["status"])
        model_vals["lx_update_time"] = result["update_time"]
        model_vals["lx_remark"] = result["remark"]
        model_vals["lx_warehouse_id"] = result["wid"]

        fba_shipment_id_list = []
        for line in result["relate_list"]:
            if line["shipment_id"] not in fba_shipment_id_list:
                fba_shipment_id_list.append(line["shipment_id"])
        model_vals["origin"] = ",".join(fba_shipment_id_list)

        if result["logistics_channel_name"] and \
            (result["logistics_channel_name"] is not None or result["logistics_channel_name"] != ""):
            key = (result["logistics_channel_name"],)
            shipping_method = self._shipping_method_cache.get(key)
            if shipping_method:
                model_vals["shipping_method"] = shipping_method.id

        if stock_picking.state not in ["cancel", "done"]:
            # 取消、完成状态下的picking不允许保存scheduled_date
            if result["shipment_time"] == "":
                model_vals["scheduled_date"] = parse(result["create_time"])
            else:
                model_vals["scheduled_date"] = parse(result["shipment_time"])

        # 先保存stock_picking的基本数据
        model_vals = AHTools.get_changed_vals(stock_picking, model_vals)
        if len(model_vals) > 0:
            stock_picking.write(model_vals)

        if stock_picking.state == "draft":
            # Odoo发货单只有是草稿状态，才可以更新数量信息。
            model_lines = result["relate_list"]

            move_lines = stock_picking.move_lines

            for line in model_lines:
                move_line = move_lines.filtered(lambda r: r.lx_shipment_line_id == line["id"])
                # 修改数量
                if move_line:
                    line_vals = {}
                    line_vals["product_uom_qty"] = line["num"]
                    line_vals["fba_shipment_id"] = line["shipment_id"]
                    line_vals = AHTools.get_changed_vals(move_line, line_vals)
                    if len(line_vals) > 0:
                        move_line.update(line_vals)
                else:
                    line_vals = self._prepare_stock_move_vals(stock_picking, result, line, without_actual_move)
                    self._connector.env["stock.move"].create(line_vals)

                # 领星发货单中删除的行，在Odoo中，数量设置为0
                lx_line_ids = []
                for line in model_lines:
                    lx_line_ids.append(line["id"])
                move_lines_to_delete = move_lines.filtered(lambda r: r.lx_shipment_line_id not in lx_line_ids)
                move_lines_to_delete.write({"product_uom_qty": 0})
                move_lines_to_delete.move_line_ids.unlink()

            if without_actual_move and result["status"] in [1,2]:
                move_lines.write({"state": "done"})

        if self._is_ready(result["remark"]):
            self._create_lx_stock_picking(stock_picking)

        picking_state = self._confirm_stock_picking(stock_picking, result)
        if picking_state == "draft":
            detail_action_state = "updated"
            detail_error_message = _("Odoo picking, %s, is in draft state.") % (result["shipment_sn"])
            detail_ext_message = False
        elif picking_state == "done":
            detail_action_state = "updated"
            detail_error_message = _("Odoo picking, %s, is completed.") % (result["shipment_sn"])
            detail_ext_message = False
        elif picking_state == "cancel":
            detail_action_state = "updated"
            detail_error_message = _("Odoo picking, %s, has been canceled.") % (result["shipment_sn"])
            detail_ext_message = False
        else:
            detail_action_state = "warning"
            detail_error_message = _(
                "LX Shipment state is done, but Odoo picking can not be completed because stock is not enough, please complete related MOs. \nShipment SN: %s") \
                                   % (result["shipment_sn"])
            detail_ext_message = False

        return stock_picking, detail_action_state, detail_error_message, detail_ext_message

    def _confirm_stock_picking(self, stock_picking, result):
        """
            根据result中的状态，对stock_picking进行确认、完成、取消等操作。
        :param stock_picking:
        :param result:
        :return: 返回stock_picking的状态：
        """
        if result["status"] in [-1]:
            # 没有状态变化
            pass
        elif result["status"] in [0, 1, 2] and stock_picking.state in ["done", "cancel"]:
            # 没有状态变化
            pass
        elif result["status"] in [0, 1, 2] and stock_picking.state not in ["done", "cancel"]:
            # 领星已经发货，则对Odoo的发货单进行确认，分配库存，完成操作。
            # 但是如果库存不够，则暂时不能做action_done的操作。
            stock_picking.action_assign()
            if all(move.state == "assigned" for move in stock_picking.move_lines):
                stock_picking.move_lines._set_quantities_to_reservation()
                stock_picking._action_done()
        elif result["status"] == 3:
            if stock_picking.state == "cancel":
                pass
            elif stock_picking.state == "done":
                stock_picking.move_lines.state = "assigned"
                stock_picking.action_cancel()
            else:
                stock_picking.action_cancel()

        return stock_picking.state

    def _create_lx_stock_picking(self, stock_pickings):
        stock_pickings = stock_pickings.filtered(lambda r: r.state == "draft")
        for picking in stock_pickings:
            lx_picking_in_vals = {
                "company_id": picking.company_id.id,
                "related_shipment_sn": picking.lx_shipment_sn,
                "lx_warehouse_id": picking.lx_warehouse_id,
                "lx_picking_type": "2",
                "stock_picking_id": picking.id,
                "is_synchronized": False,
            }

            lx_picking_out_vals = {
                "company_id": picking.company_id.id,
                "related_shipment_sn": picking.lx_shipment_sn,
                "lx_warehouse_id": picking.lx_warehouse_id,
                "lx_picking_type": "14",
                "stock_picking_id": picking.id,
                "is_synchronized": False,
            }

            move_lines = picking.move_lines

            lx_move_in_vals_list = []
            lx_move_out_vals_list = []

            for line in move_lines:
                lx_stock_move_ids = line.lx_stock_move_ids
                move_qty = line.product_uom_qty
                existing_qty = sum(lx_stock_move_ids.mapped("product_qty"))
                new_qty = move_qty - existing_qty

                if new_qty == 0:
                    continue
                elif new_qty > 0:
                    lx_move_vals = {
                        "company_id": line.company_id.id,
                        "product_id": line.product_id.id,
                        "shop_product_id": line.shop_product_id.id,
                        "price_unit": line.price_unit,
                        "stock_move_id": line.id,
                        "product_qty": new_qty,
                    }
                    lx_move_in_vals_list.append(lx_move_vals)
                elif new_qty < 0:
                    lx_move_vals = {
                        "company_id": line.company_id.id,
                        "product_id": line.product_id.id,
                        "shop_product_id": line.shop_product_id.id,
                        "price_unit": line.price_unit,
                        "stock_move_id": line.id,
                        "product_qty": new_qty,
                    }
                    lx_move_out_vals_list.append(lx_move_vals)

            if len(lx_move_in_vals_list) > 0:
                lx_picking = stock_pickings.env["web.sale.lx.stock.picking"].create(lx_picking_in_vals)
                for lx_move_vals in lx_move_in_vals_list:
                    lx_move_vals.setdefault("lx_stock_picking_id", lx_picking.id)
                stock_pickings.env["web.sale.lx.stock.move"].create(lx_move_in_vals_list)

            if len(lx_move_out_vals_list) > 0:
                lx_picking = stock_pickings.env["web.sale.lx.stock.picking"].create(lx_picking_out_vals)
                for lx_move_vals in lx_move_out_vals_list:
                    lx_move_vals.setdefault("lx_stock_picking_id", lx_picking.id)
                stock_pickings.env["web.sale.lx.stock.move"].create(lx_move_out_vals_list)

