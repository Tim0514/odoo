# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import collections
import datetime
import hashlib
import pytz
import threading
import re

import requests
from lxml import etree
from random import randint
from werkzeug import urls

from odoo import api, fields, models, tools, SUPERUSER_ID, _
from odoo.modules import get_module_resource
from odoo.osv.expression import get_unaccent_wrapper
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)

class Company(models.Model):
    _inherit = "res.company"


    
    def do_clean_company_data(self):
        """
            删除数据库中某一个公司的数据
            1. 备份至少2个数据库，以防出错。
            2. 在测试库中执行get_remove_company_data_sql方法得到所有包含该公司数据的表的sql删除语句
            3. 用navicat软件在测试库中测试全部的sql语句，调整顺序，去掉view视图。
            4. 将调整后的sql语句在Odoo中执行。
            5. 测试没有问题后，再到正式库中执行。
        """
        self.ensure_one()
        company_id = self.id

        sql_list = self._get_remove_company_data_sql()

        for sql in sql_list:
            _logger.info("Start to execute sql: %s at %s" % (sql, datetime.datetime.now().strftime("%Y-%m-%d %HH:%MM:%SS")))
            self.env.cr.execute(sql)
            self.env.cr.commit()
            _logger.info("Stop to execute sql: %s at %s" % (sql, datetime.datetime.now().strftime("%Y-%m-%d %HH:%MM:%SS")))

        self.unlink()
        sql_ext1 = "delete from resource_calendar where company_id is null;"
        sql_ext2 = "delete from stock_location where company_id is null and id > 100;"
        self.env.cr.execute(sql_ext1)
        self.env.cr.execute(sql_ext2)

        return

    def _get_remove_company_data_sql(self):
        company_id = self.id

        models_to_delete_data, models_with_company_data_dict = self._get_models_to_remove_company_data()

        sql_list = []
        for model_name in models_to_delete_data:
            model = self.env.get(model_name, False)
            sql = "delete from %s where %s = %s" % (model._table, models_with_company_data_dict[model_name]["field_name"], str(company_id))
            sql_list.append(sql)

        # 将上面得到的sql语句，在navicat中测试
        sql_list = [
            "delete from account_tax_repartition_line where company_id = %s" % company_id,
            "delete from account_tax where company_id = %s" % company_id,
            "delete from account_reconcile_model where company_id = %s" % company_id,
            "delete from account_payment_method_line a using account_journal b where a.journal_id = b.id and b.company_id = %s" % company_id,
            "delete from account_move_line where company_id = %s" % company_id,
            "delete from account_move where company_id = %s" % company_id,
            "delete from account_bank_statement where company_id = %s" % company_id,
            "delete from account_journal where company_id = %s" % company_id,
            "delete from account_account where company_id = %s" % company_id,
            "delete from stock_move_line where company_id = %s" % company_id,
            "delete from stock_move where company_id = %s" % company_id,
            "delete from stock_picking where company_id = %s" % company_id,
            "delete from stock_rule where company_id = %s" % company_id,
            "delete from stock_picking_type where company_id = %s" % company_id,
            "delete from stock_quant where company_id = %s" % company_id,
            "delete from stock_package_level where company_id = %s" % company_id,
            "delete from stock_quant_package where company_id = %s" % company_id,
            "delete from stock_valuation_layer where company_id = %s" % company_id,
            "delete from sale_order_line where company_id = %s" % company_id,
            "delete from sale_order where company_id = %s" % company_id,
            "delete from stock_warehouse_orderpoint where company_id = %s" % company_id,
            "delete from stock_warehouse where company_id = %s" % company_id,
            "delete from stock_location_route where company_id = %s" % company_id,
            "delete from res_partner where company_id = %s" % company_id,
            "delete from product_supplierinfo where company_id = %s" % company_id,
            "delete from product_pricelist where company_id = %s" % company_id,
            "delete from ir_sequence where company_id = %s" % company_id,
            "delete from ir_property where company_id = %s" % company_id,
            "delete from ir_attachment where company_id = %s" % company_id,
        ]

        return sql_list


    def _get_models_to_remove_company_data(self):

        self.ensure_one()
        company_id = self.id
        field_obj = self.env["ir.model.fields"]

        domain = [
            ("name", "=like", "%company_id"),
            ("relation", "=", "res.company"),
            ("ttype", "=", "many2one"),
            ("model", "not in", ["res.company", "res.config.settings"]),
        ]

        fields = field_obj.search(domain, order="id desc")
        models_with_company_data_dict = {}
        models_without_company_data = {}
        models_error = {}
        for company_field in fields:
            model_name = company_field.model
            model = self.env.get(model_name, False)
            if model is not None:
                domain2 = [
                    (company_field.name, "=", company_id),
                ]
                count = 0
                try:
                    exclude_models = [
                        "account.aged.payable",
                        "account.aged.receivable",
                        "account.aged.partner",
                        "account.multicurrency.revaluation",
                        "resource.mixin",
                    ]
                    if model._name not in exclude_models:
                        count = model.sudo().search_count(domain2)
                except Exception as error:
                    models_error.setdefault(model._name, error)
                    pass
                if count > 0:
                    models_with_company_data_dict.setdefault(model._name, {"field_name": company_field.name, "count": count})
                else:
                    models_without_company_data.setdefault(model._name, {"field_name": company_field.name})

        models_to_delete_data = sorted(list(models_with_company_data_dict.keys()), reverse=True)

        return models_to_delete_data, models_with_company_data_dict

        # domain = [
        #     ("name", "ilike", "company_id"),
        #     ("relation", "=", "res.company"),
        #     ("ttype", "=", "many2one"),
        #     ("on_delete", "=", "restrict"),
        #     ("model", "!=", "res.company"),
        # ]
        # fields = field_obj.search(domain, order="id desc")
        # for company_field in fields:
        #     model_name = company_field.model
        #     model = self.env.get(model_name, False)
        #     if model is not None:
        #         sql = "delete from %s where %s = %s" % (model._table, company_field.name, str(company_id))
        #         self.env.cr.execute(sql)
        #
        # domain = [
        #     ("name", "ilike", "company_id"),
        #     ("relation", "=", "res.company"),
        #     ("ttype", "=", "many2many"),
        #     ("model", "!=", "res.company"),
        # ]
        # fields = field_obj.search(domain, order="id desc")
        # for company_field in fields:
        #     model_name = company_field.model
        #     model = self.env.get(model_name, False)
        #     if model is not None:
        #         sel = "delete from %s where %s = %s" % (company_field.relation_table, company_field.column2, str(company_id))
        #         self.env.cr.execute(sql)
        #
        # domain = [
        #     ("name", "ilike", "company_id"),
        #     ("relation", "=", "res.company"),
        #     ("ttype", "=", "many2one"),
        #     ("on_delete", "!=", "restrict"),
        #     ("model", "!=", "res.company"),
        # ]
        # fields = field_obj.search(domain, order="id desc")
        # for company_field in fields:
        #     model_name = company_field.model
        #     model = self.env.get(model_name, False)
        #     if model is not None:
        #         sql = "delete from %s where %s = %s" % (model._table, company_field.name, str(company_id))
        #         self.env.cr.execute(sql)
