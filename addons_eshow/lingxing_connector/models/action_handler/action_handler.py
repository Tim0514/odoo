# Copyright 2020-2022 Max Share Technologies
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)
import calendar
import json
from time import gmtime, strftime, time, sleep
from datetime import datetime, timedelta, date

from dateutil.parser import parse
from dateutil.tz import tzlocal
from pytz import timezone
from odoo import _, fields
from dateutil.relativedelta import *
from dateutil.rrule import *

import sys

import logging

_logger = logging.getLogger(__name__)

class AHTools(object):

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

    @staticmethod
    def get_utc_datetime(src_datetime, src_timezone):
        """
        将日期或者是日期字符串转换为aware的日期(带时区)
        :param src_datetime: 日期或者是日期字符串
        :param src_timezone: src_datetime 的时区
        :return:
        """
        if not src_datetime or src_datetime == "":
            return None
        datetime_val = AHTools.get_aware_datetime(src_datetime, src_timezone)
        tz = timezone("UTC")
        datetime_val = datetime_val.astimezone(tz).replace(tzinfo=None)
        return datetime_val

    @staticmethod
    def get_aware_datetime(src_datetime, src_timezone):
        """
        将Naive类型的日期或者是日期字符串转换为aware的日期(带时区)
        :param src_datetime: 日期或者是日期字符串
        :param src_timezone:
        :return:
        """
        if not src_datetime or src_datetime == "":
            return None
        if isinstance(src_datetime, str):
            src_datetime = parse(src_datetime)
        tz=timezone(src_timezone)
        if src_datetime.tzinfo:
            datetime_val = src_datetime.astimezone(tz)
        else:
            datetime_val = tz.localize(src_datetime)
        return datetime_val

    @staticmethod
    def get_changed_vals(model_data, model_vals):
        model_data.ensure_one()
        new_model_vals = {}
        for key in model_vals:
            if model_data[key]:
                field = model_data._fields.get(key)
                if field.type == 'many2one' and model_data[key].id != model_vals[key]:
                    new_model_vals.setdefault(key, model_vals[key])
                elif field.type not in ('many2one', 'one2many', 'many2many') and model_data[key] != model_vals[key]:
                    new_model_vals.setdefault(key, model_vals[key])

        return new_model_vals

    @staticmethod
    def get_local_datetime_str(src_datetime, src_timezone):
        if not src_datetime or src_datetime == "":
            return None
        datetime_val = AHTools.get_aware_datetime(src_datetime, src_timezone)
        return datetime_val.isoformat()


class ActionHandler(object):
    def __init__(self, connector, log_book, start_time=None, end_time=None, **kwargs):
        self._connector = connector
        self._log_book = log_book
        self._data_start_time = start_time
        self._data_end_time = end_time

        # 是否还有更多的请求参数
        # （除了offset以外其他参数也会变化，例如需要上传产品，每次请求只能上传1条，需要多次上传。），
        # 例如按店铺列表，请求不同店铺的Listing数据。
        # 一定要注意，初始必须为True，否则connector不会调用prepare_req_body方法
        # prepare_req_body方法中，当参数被使用完，或者参数只有一组，一定要设置为False, 否则会死循环。
        self._has_more_request_data = True

        # 是否还有更多的数据要返回（按页返回数据，例如下载一批订单。）
        self._has_more_result_data = False
        # 每次返回数据的最大数量。
        self._result_records_limit = 1000
        # 当前请求返回数据的偏移量
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
        self._ids_deleted = []

    def _add_process_result(self, process_state, res_id):
        if process_state == "created":
            self._ids_created.append(res_id)
        elif process_state == "updated":
            self._ids_updated.append(res_id)
        elif process_state == "deleted":
            self._ids_deleted.append(res_id)
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
        return self._ids_created + self._ids_updated + self._ids_warning

    def get_success_count(self):
        return len(self._ids_created) + len(self._ids_updated) + len(self)

    def get_ignore_count(self):
        return len(self._ids_ignored)

    def get_create_count(self):
        return len(self._ids_created)

    def get_fail_count(self):
        return len(self._ids_failed)

    def get_delete_count(self):
        return len(self._ids_deleted)

    def get_update_count(self):
        return len(self._ids_updated)

    def get_warning_count(self):
        return len(self._ids_warning)

    def get_total_count(self):
        return len(self._ids_created) + len(self._ids_updated) + len(self._ids_deleted) + \
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
            if isinstance(self._response_result.data, list):
                self._result_length = len(self._response_result.data)
                self._result_total = self._response_result.total
            elif "list" in self._response_result.data:
                self._result_length = len(self._response_result.data["list"])
                self._result_total = self._response_result.data["total"]
                if isinstance(self._result_total, str):
                    self._result_total = int(self._result_total)
            else:
                self._result_total = self._response_result.total
                self._result_length = self._result_total

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




