# Copyright 2020-2022 Max Share Technologies
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)
import calendar
import json
from time import gmtime, strftime, time, sleep
from datetime import datetime, timedelta, date

from dateutil.parser import parse
from dateutil.tz import tzlocal

from odoo import _, fields
from dateutil.relativedelta import *
from dateutil.rrule import *

import sys

import logging

_logger = logging.getLogger(__name__)

class ActionHandlerTools(object):

    @staticmethod
    def cint(value):
        try:
            value = int(value)
        except Exception as error:
            value = 0
        return value

    @staticmethod
    def cfloat(value):
        try:
            value = float(value)
        except Exception as error:
            value = 0.00
        return value


class ActionHandler(object):
    def __init__(self, connector, log_book, start_time=None, end_time=None, **kwargs):
        self._connector = connector
        self._log_book = log_book
        self._data_start_time = start_time
        self._data_end_time = end_time

        # 还有更多的参数，默认为True
        self._has_more_request_data = True

        # 还有更多的数据要返回
        self._has_more_result_data = False

        # 请求参数中，如果有数据要分页的，则使用_request_page_length来控制分页，例如shop列表或订单列表
        self._request_page_limit = 10
        self._request_offset = 0
        # 请求参数数据的总数量，默认为负数
        self._request_total = -1

        # 读取结果中，如果有数据要分页的，则使用_result_page_length来控制分页，例如下载一批订单。
        self._result_page_limit = 1000
        self._result_offset = 0

        # 返回的结果
        self._response_result = None

        # 返回的结果数量
        self._result_length = 0
        # 返回结果应有的总数量
        self._result_total = 0

        self._log_line_vals = []

        self._ids_created = []
        self._ids_updated = []
        self._ids_failed = []
        self._ids_ignored = []
        self._ids_warning = []

    def _add_process_result(self, process_state, res_id):
        if process_state == "created":
            self._ids_created.append(res_id)
        elif process_state == "updated":
            self._ids_updated.append(res_id)
        elif process_state == "failed":
            self._ids_failed.append(res_id)
        elif process_state == "warning":
            self._ids_warning.append(res_id)
        else:
            self._ids_ignored.append(res_id)

    def _add_log_line(self, code_ref=None, name_ref=None, action_state=None,
                      err_msg=None, ext_msg=None, res_id=None):
        log_line_val = self._log_book._prepare_log_line(
            code_ref=code_ref,
            name_ref=name_ref,
            action_state=action_state,
            error_message=err_msg,
            ext_message=ext_msg,
            model_id=self._connector.related_model_id.id,
            res_id=res_id
        )
        self._log_line_vals.append(log_line_val)

    def pop_log_line_vals(self):
        log_line_vals = self._log_line_vals
        self._log_line_vals = []
        return log_line_vals

    def get_success_ids(self):
        return self._ids_created + self._ids_updated

    def get_success_count(self):
        return len(self._ids_created) + len(self._ids_updated)

    def get_ignore_count(self):
        return len(self._ids_ignored)

    def get_fail_count(self):
        return len(self._ids_failed)

    def get_warning_count(self):
        return len(self._ids_warning)

    def get_total_count(self):
        return len(self._ids_created) + len(self._ids_updated) + \
               len(self._ids_ignored) + len(self._ids_failed) + len(self._ids_warning)

    def has_next_request(self):
        if self._has_more_request_data or self._has_more_result_data:
            return True
        else:
            return False

    def set_result(self, response_result):
        self._response_result = response_result

        if isinstance(self._response_result, list):
            # 如果返回的是列表，则列表每个元素是一个ResponseResult, 此时是发送了multi_request以后的返回值。
            self._result_length = len(self._response_result)
            self._result_total = self._result_length
        else:
            # 如果返回的是ResponseResult, 此时是发送了single_request以后的返回值。
            self._result_total = self._response_result.total
            if isinstance(self._response_result.data, list):
                self._result_length = len(self._response_result.data)

        if self._result_offset + self._result_length < self._result_total:
            self._has_more_result_data = True
            self._result_offset += self._result_length
        else:
            self._has_more_result_data = False
            self._result_offset = 0

    def prepare_req_body(self):
        raise Exception("method(prepare_req_body) must be implemented by yourself.")

    def process_response_result(self):
        raise Exception("method(process_response_result) must be implemented by yourself.")




