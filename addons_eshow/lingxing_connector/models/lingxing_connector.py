# Copyright 2020-2022 Max Share Technologies
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)

from time import gmtime, strftime, time, sleep
from datetime import datetime
from odoo import _, fields, api, registry, SUPERUSER_ID

import threading
from typing import Any, Optional

import asyncio

from odoo.exceptions import UserError
from . import action_handler

from odoo import _, exceptions, models
from odoo.tools import OrderedSet
# sys.path.append("..")
from ..openapi.openapi import OpenApiBase
from ..openapi.openapi import ResponseResult
import logging

_logger = logging.getLogger(__name__)

# 当前环境为测试环境，还是生产环境
is_production_enviroment = True

TEST_DOMAIN = "https://openapisandbox.lingxing.com"
TEST_APP_ID = "ak_tQgtvwh74dIq1"
TEST_APP_SECRET = "0OZhqsg22MK0/25CEiTQDg=="

PRODUCTION_DOMAIN = "https://openapi.lingxing.com"
PRODUCTION_APP_ID = "ak_f6yeEe7UTPh9g"
PRODUCTION_APP_SECRET = "3jKW34DKf8cUbA8xaaUqIg=="

if is_production_enviroment:
    ACCESS_DOMAIN = PRODUCTION_DOMAIN
    APP_ID = PRODUCTION_APP_ID
    APP_SECRET = PRODUCTION_APP_SECRET
else:
    ACCESS_DOMAIN = TEST_DOMAIN
    APP_ID = TEST_APP_ID
    APP_SECRET = TEST_APP_SECRET


class ConnectorError(Exception):
    """
    Main Exception class
    """
    # Allows quick access to the response object.
    # Do not rely on this attribute, always check if its not None.
    request_action = None
    response_result = None


class SameActionRunningError(Exception):
    """
    This error will be occured when same action is already running.
    """
    request_action = None


class ActionLock(object):
    # 当前正在运行的同步动作，用于防止相同的操作被同时执行。导致数据错误。
    _running_actions = {}

    def __init__(self, action_name):
        self.action_name = action_name

    def __enter__(self):
        self._set_action_start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._set_action_complete()
        # print "type: ", exc_type
        # print "val: ", exc_val
        # print "tb: ", exc_tb

    def _set_action_start(self):
        action_name = self.action_name
        lock = threading.Lock()
        with lock:
            if action_name in ActionLock._running_actions:
                if ActionLock._running_actions[action_name]:
                    error = SameActionRunningError("Same action is running, please try again later.")
                    error.request_action = action_name
                    raise error
            else:
                ActionLock._running_actions[action_name] = True
        return True

    def _set_action_complete(self):
        action_name = self.action_name
        lock = threading.Lock()
        with lock:
            ActionLock._running_actions[action_name] = False
        return True


class LingxingConnector(models.Model):
    _name = "connector.lingxing"
    _description = "Lingxing Connector"
    _order = "name"

    # 访问Lingxing服务器的令牌
    _access_token = None
    _refresh_token = None
    _expires_in = None
    _last_refresh_token_time = None
    _force_refresh_token = False

    name = fields.Char("Name", index=True)
    action_description = fields.Char("Description")
    route = fields.Char("Route")
    method = fields.Char("Method")
    max_concurrency = fields.Integer("Max Concurrency", default=1)
    related_model_id = fields.Many2one("ir.model", string="Related Model")
    action_type = fields.Selection([("export", "Export"), ("import", "Import")], string="Action Type")
    start_time = fields.Datetime("Start Time", default=fields.Datetime.to_datetime("2000-01-01 00:00:00"))
    end_time = fields.Datetime("End Time", default=fields.Datetime.to_datetime("2000-01-01 00:00:00"))
    last_sync_time = fields.Datetime("Last Sync Time")
    last_sync_result = fields.Selection([("fail", "Fail"), ("success", "Success")], string="Last Sync Result")
    last_success_sync_time = fields.Datetime("Last Success Sync Time")

    action_handler_name = fields.Char("Action Handler Class Name")

    def __init__(self, *args, **kwargs):
        super(LingxingConnector, self).__init__(*args, **kwargs)

    def _raise_connector_error(self, message, response_result: ResponseResult = None, error=None):
        """ Build an error log from an error response, if any, and raise it. """
        error_log = message
        if response_result:
            error_log += "\n %s: %s" % (
                response_result.code,
                response_result.message
            )
        if error:
            error_log += "\n Error Stack: %s" % str(error)

        error = ConnectorError(error_log)
        error.request_action = self.name
        error.response_result = response_result

        raise error

    def _set_force_refresh_token(self, force_refresh_token):
        LingxingConnector._force_refresh_token = force_refresh_token

    def _get_force_refresh_token(self):
        return LingxingConnector._force_refresh_token

    async def _refresh_access_token(self):
        try:
            current_time = time()

            if self._get_force_refresh_token() or (not LingxingConnector._access_token) \
                    or (not LingxingConnector._last_refresh_token_time) \
                    or current_time - LingxingConnector._last_refresh_token_time > 6000:
                op_api = OpenApiBase(ACCESS_DOMAIN, APP_ID, APP_SECRET)
                response_data = await op_api.generate_access_token()
                LingxingConnector._access_token = response_data.access_token
                LingxingConnector._refresh_token = response_data.refresh_token
                LingxingConnector._expires_in = response_data.expires_in
                LingxingConnector._last_refresh_token_time = current_time
                self._set_force_refresh_token(False)

            return LingxingConnector._access_token

        except Exception as error:
            self._raise_connector_error(
                "Error Obtain Token From Lingxing Server",
                error=error
            )

    def _make_single_request(
            self,
            req_params: Optional[dict] = None,
            req_body: Optional[dict] = None,
            **kwargs) -> ResponseResult:
        """
        发送单次请求，通常用于下载数据。
        如果出现重复下载的情况，则多次调用此方法。
        :param req_params:
        :param req_body:
        :param kwargs:
        :return:
        """

        # 获取接口路径和Method
        request_action = self.name
        route = self.route
        method = self.method

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # 刷新Token
            loop.run_until_complete(self._refresh_access_token())

            op_api = OpenApiBase(ACCESS_DOMAIN, APP_ID, APP_SECRET)

            task1 = loop.create_task(
                op_api.request(LingxingConnector._access_token, route, method, req_params, req_body, **kwargs)
            )

            loop.run_until_complete(task1)
            sleep(1)
            response = task1.result()

            if response.code != 0:
                self._raise_connector_error(
                    "Error occured when synchronizing with Lingxing Server.",
                    response_result=response,
                )
            else:
                return response

        except ConnectorError as error:
            raise error
        except BaseException as error:
            self._raise_connector_error(
                "Error Connecting To Lingxing Server",
                error=error
            )

    def _make_multi_request(
            self,
            req_params: Optional[dict] = None,
            req_body_list: Optional[list] = None,
            **kwargs) -> list[ResponseResult]:
        """
        发送多次请求，通常用于上传数据。
        :param req_params:
        :param req_body_list: req_body的列表
        :param kwargs:
        :return:
        """

        # 获取接口路径和Method
        request_action = self.name
        route = self.route
        method = self.method
        max_concurrency = self.max_concurrency

        # 返回值列表
        result_list = []

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # 刷新Token
            loop.run_until_complete(self._refresh_access_token())

            op_api = OpenApiBase(ACCESS_DOMAIN, APP_ID, APP_SECRET)

            # 总请求数
            total_requests = len(req_body_list)

            async def _run_multi_tasks(tasks):
                rtn = await asyncio.wait(tasks, return_when=asyncio.tasks.ALL_COMPLETED)
                await asyncio.sleep(2)
                return rtn

            i = 0
            while i < total_requests:
                j = 0
                tasks = []
                while j < max_concurrency and (i + j) < total_requests:
                    req_body = req_body_list[i + j]
                    task = loop.create_task(
                        op_api.request(LingxingConnector._access_token, route, method, req_params, req_body,
                                       **kwargs),
                        name="%s" % (str(100000 + i + j))
                    )
                    tasks.append(task)
                    j = j + 1
                task_result_set, result_list_pending = loop.run_until_complete(_run_multi_tasks(tasks))

                # 返回的task_result_set是无序的集合，需要转换成有序的列表
                task_result_dict = {}
                task_result_list = []
                for task_result in task_result_set:
                    task_result_dict[task_result.get_name()] = task_result
                sort_keys = sorted(task_result_dict.keys())
                for key in sort_keys:
                    task_result = task_result_dict[key]
                    task_result_list.append(task_result)

                result_list_temp = []
                for task_result in task_result_list:
                    if task_result.exception():
                        # 如果任务本身发生错误，无法正确返回response_result，则创建一个
                        response_result = ResponseResult()
                        response_result.code = 999999
                        response_result.message = "Odoo Side Error"
                        response_result.error_details = str(task_result.exception())
                        result_list_temp.append(response_result)
                    else:
                        result_list_temp.append(task_result.result())
                result_list = result_list + result_list_temp
                i = i + j

            loop.close()

            return result_list

        except ConnectorError as error:
            raise error
        except BaseException as error:
            self._raise_connector_error(
                "Error Connecting To Lingxing Server",
                error=error
            )

    def _get_model_id(self, model_name):
        model_id = self.env['ir.model']
        return model_id.search([('model', '=', model_name)])

    def _get_data_sync_time_dict(self):
        """
        获取同步数据行的相关同步时间
        :param request_action:
        :param model_name:
        :param action_type: 需要返回导出时间，还是导入时间
        :return: {res_id:sync_time}
        """
        request_action = self.name
        model_id = self.related_model_id.id
        action_type = self.action_type

        data_sync_info_obj = self.env["connector.data.sync.info"]
        domain = [("operation_name", "=", request_action), ("model_id", "=", model_id)]
        data_info_list = data_sync_info_obj.search(domain, order="res_id")

        data_info_dict = {}
        for data_info in data_info_list:
            if action_type == "import":
                data_info_dict[data_info.res_id] = data_info.last_import_time
            else:
                data_info_dict[data_info.res_id] = data_info.last_export_time
        return data_info_dict

    def _update_data_sync_time(self, res_ids=Optional[list], sync_time=fields.Datetime.now()):
        """
        更新相关记录的导入或导出时间
        :param request_action:
        :param model_name:
        :param action_type:
        :param sync_time:
        :param res_ids: 模型数据的ID列表
        :return:
        """

        request_action = self.name
        action_type = self.action_type
        model_id = self.related_model_id.id

        data_sync_info_obj = self.env["connector.data.sync.info"]
        domain = [("operation_name", "=", request_action), ("model_id", "=", model_id), ("res_id", "in", res_ids)]

        # 首先读取出已有的记录
        existing_records = data_sync_info_obj.search(domain, order="res_id")

        if action_type == "import":
            existing_records.sudo().write({"last_import_time": sync_time})
        else:
            existing_records.sudo().write({"last_export_time": sync_time})

        existing_res_ids = existing_records.mapped("res_id")

        res_ids_to_add = list(set(res_ids) - set(existing_res_ids))

        # 需要添加的记录
        records_to_add: list[dict] = []

        for res_id in res_ids_to_add:
            if action_type == "import":
                records_to_add.append(
                    {
                        "operation_name": request_action,
                        "model_id": model_id,
                        "res_id": res_id,
                        "last_import_time": sync_time,
                        "last_export_time": False,
                    })
            else:
                records_to_add.append(
                    {
                        "operation_name": request_action,
                        "model_id": model_id,
                        "res_id": res_id,
                        "last_import_time": False,
                        "last_export_time": sync_time,
                    })

        data_sync_info_obj.sudo().create(records_to_add)

    def _get_last_action_time(self):
        """
            从log book 中读取最后一次成功操作的时间，如果没有找到，则默认2010年1月1日
        :return:
        """
        last_action_time = datetime.strptime('2010-01-01', '%Y-%m-%d')
        log_book = self.env["eshow.log.book"]
        log_book = log_book.search(
            [
                ("log_module", "=", "lingxing_connector"),
                ("operation_name", "=", self.name),
                ("action_state", "=", "success"),
            ],
            order="start_date desc",
            limit=1
        )
        if log_book:
            last_action_time = log_book[0].start_date
        return last_action_time

    def _init_log_book(self):
        log_book = self.env["eshow.log.book"].init_log_book('lingxing_connector', self.name)
        return log_book

    def _compute_date_range(self, current_time=False, start_time=False, end_time=False):
        """
        根据传入的日期，计算需要执行的日期范围
        :param current_time:
        :param start_time:
        :param end_time:
        :return: 开始时间，结束时间，开始时间字符串，结束时间字符串
        """
        if not current_time:
            current_time = fields.Datetime.now()

        # 如果没有传入start_time, 则取上次执行成功的时间
        if not start_time:
            if self.last_success_sync_time:
                start_time = self.last_success_sync_time
            else:
                start_time = datetime.strptime("2000-01-01 00:00:00", '%Y-%m-%d %H:%M:%S')

        # 如果没有传入end_time, 则取本次同步时间
        if not end_time:
            end_time = current_time

        start_time_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
        end_time_str = end_time.strftime('%Y-%m-%d %H:%M:%S')

        return start_time, end_time, start_time_str, end_time_str

    def _set_action_result(self, action_state, action_start_time=False, start_time=False, end_time=False):
        self = self.sudo()
        if not action_start_time:
            action_start_time = fields.Datetime.now()

        if action_state == "fail":
            self.last_sync_result = action_state
            self.last_sync_time = action_start_time
        else:
            self.last_sync_result = action_state
            self.last_sync_time = action_start_time
            self.last_success_sync_time = action_start_time
            self.start_time = start_time
            self.end_time = end_time

    def do_sync_action(self, start_time=False, end_time=False, **kwargs):
        """
        :param start_time: 导入的数据的更新时间从start_time开始，如果为False则使用数据库记录的end_time
        :param end_time: 导入的数据的更新时间到end_time结束，如果为False则使用当前时间
        :return: log_book
        """
        self = self.with_user(SUPERUSER_ID)

        # 初始化log_book

        log_book_cr = registry(self._cr.dbname).cursor()
        env = api.Environment(log_book_cr, SUPERUSER_ID, {})
        log_book = env["eshow.log.book"].init_log_book('lingxing_connector', self.name)

        # action_state 默认为“success”, 如果中间发生错误则改为“error”
        action_state = "success"
        error_message = False
        ext_message = False

        total_record_count = 0
        create_record_count = 0
        update_record_count = 0
        delete_record_count = 0
        fail_record_count = 0
        ignore_record_count = 0
        warning_record_count = 0

        req_body = None
        try:
            with ActionLock(self.name):
                # action_start_time 用于参数的 各种end_time
                action_start_time = fields.Datetime.now()

                # 得到需要数据的开始时间和结束时间
                start_time, end_time, start_time_str, end_time_str = self._compute_date_range(action_start_time,
                                                                                              start_time,
                                                                                              end_time)

                handler_modul_name, handler_class_name = self.action_handler_name.split('.')
                action_handler_obj = getattr(action_handler, handler_modul_name)
                action_handler_obj = getattr(action_handler_obj, handler_class_name)
                action_handler_obj = action_handler_obj(self, log_book, start_time, end_time, **kwargs)

                # 循环请求数据，直到所有数据都完成下载
                while action_handler_obj.has_next_request():

                    req_body = action_handler_obj.prepare_req_body()

                    # 请求数据
                    if isinstance(req_body, list):
                        response_result = self._make_multi_request(req_body_list=req_body)
                    else:
                        response_result = self._make_single_request(req_body=req_body)

                    # print("Request Complete, data length: %s." % len(response_result.data))

                    action_handler_obj.set_result(response_result)

                    process_success = action_handler_obj.process_response_result()

                    # print("Process Complete.")

                    # 只记录有问题的日志行
                    log_lines = action_handler_obj.pop_log_line_vals()
                    # log_lines = list(filter(lambda v: v["action_state"] != "success", log_lines))
                    log_book.add_log_lines(log_lines)

                    if not process_success:
                        action_state = "fail"

                    # 将数据行的更新时间写入同步成功的data_sync_info表中
                    self._update_data_sync_time(
                        res_ids=action_handler_obj.get_success_ids(),
                        sync_time=action_start_time
                    )

                    self.env.cr.commit()

                    # print("Commit Complete.")

                # 计算成功和失败的数量
                total_record_count = action_handler_obj.get_total_count()
                create_record_count = action_handler_obj.get_create_count()
                update_record_count = action_handler_obj.get_update_count()
                delete_record_count = action_handler_obj.get_delete_count()
                ignore_record_count = action_handler_obj.get_ignore_count()
                fail_record_count = action_handler_obj.get_fail_count()
                warning_record_count = action_handler_obj.get_warning_count()

                self._set_action_result(action_state=action_state, action_start_time=action_start_time,
                                        start_time=start_time, end_time=end_time)

                # print("start: %s, end: %s" % (str(action_start_time), str(datetime.now())))

                if action_state == "fail":
                    error_message = "See error in line data."

        except ConnectorError as error:
            _logger.exception(error)

            if error.response_result and error.response_result.code == 2001005:
                self._set_force_refresh_token(True)

            action_state = "fail"
            error_message = str(error)
            ext_message = str(req_body)
        except Exception as error:
            _logger.exception(error)
            action_state = "fail"
            error_message = str(error)
            ext_message = str(req_body)
        finally:
            # 记录Log Book 的日志
            log_book.update_log_book_result(
                action_state,
                total_record_count=total_record_count,
                create_record_count=create_record_count,
                update_record_count=update_record_count,
                delete_record_count=delete_record_count,
                fail_record_count=fail_record_count,
                ignore_record_count=ignore_record_count,
                warning_record_count=warning_record_count,
                error_message=error_message,
                ext_message=ext_message
            )

            try:
                log_book_cr.commit()
                log_book_cr.close()
            except Exception as error:
                pass

            return log_book

    @api.model
    def run_scheduler(self, action_names=False, use_new_cursor=False, company_id=False, **kwargs):
        """ Call the scheduler. This function is intended to be run for all the companies at the same time, so
        we run functions as SUPERUSER to avoid intercompanies and access rights issues. """
        try:
            if use_new_cursor:
                cr = registry(self._cr.dbname).cursor()
                self = self.with_env(self.env(cr=cr))  # TDE FIXME

            if not action_names and not isinstance(action_names, str) and not isinstance(action_names, list):
                raise UserError(_("Action name is required to run the connector scheduler."))
            elif isinstance(action_names, str):
                action_names = [action_names]

            for action_name in action_names:
                connector = self.search([("name", "=", action_name)])
                if not connector:
                    raise UserError(_("Action, %s, is not found to run the connector scheduler." % action_name))

                connector.do_sync_action(start_time=False, end_time=False,
                                         use_new_cursor=use_new_cursor, company_id=company_id, **kwargs)

            if use_new_cursor:
                self._cr.commit()
                self._cr.close()
        finally:
            if use_new_cursor:
                try:
                    self._cr.close()
                except Exception:
                    pass
        return {}

