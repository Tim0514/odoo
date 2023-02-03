# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
from time import time

from odoo import models, fields, api, registry
from odoo import _
from datetime import datetime


class LogBook(models.Model):
    _name = "eshow.log.book"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = 'id desc'
    _description = "Log book for Connectors"

    @api.model
    def _company_get(self):
        return self.env["res.company"].browse(self.env.company.id)

    company_id = fields.Many2one(comodel_name="res.company", string="Company", required=True, default=_company_get)

    name = fields.Char("Reference", readonly=True)
    log_module = fields.Selection(
        [
            ('lingxing_connector', _('Lingxing Connector')),
        ],
        string="Module which create the log."
    )
    operation_name = fields.Char("Operation", readonly=True)
    start_date = fields.Datetime("Start Time")
    complete_date = fields.Datetime("Complete Time")
    action_state = fields.Selection(
        selection=[('in-progress', 'In Progress'), ('success', 'Success'), ('fail', 'Fail'), ('warning', 'Warning')],
        default='in-progress')
    total_record_count = fields.Integer("Total Record Count")
    success_record_count = fields.Integer("Successful Record Count")
    fail_record_count = fields.Integer("Failed Record Count")
    warning_record_count = fields.Integer("Warning Record Count")
    ignore_record_count = fields.Integer("Ignore Record Count")

    error_message = fields.Text("Error Message")
    ext_message = fields.Text("Extend Message")

    attachment_id = fields.Many2one('ir.attachment', string="Attachment")
    file_name = fields.Char("File Name")

    log_book_lines = fields.One2many('eshow.log.book.line', 'log_book_id')


    @api.model
    def create(self, vals):
        """
        To generate a sequence for a logbook.
        """
        seq = self.env['ir.sequence'].next_by_code('eshow.log.book') or '/'
        vals['name'] = seq

        return super(LogBook, self).create(vals)

    def init_log_book(self, log_module, operation_name):
        log_book_id = self.sudo().create({"log_module": log_module,
                                   "operation_name": operation_name,
                                   "start_date": datetime.now(),
                                   })
        self._cr.commit()
        return log_book_id[0]

    def update_log_book_result(
            self, action_state,
            total_record_count=0, success_record_count=0, fail_record_count=0,
            ignore_record_count=0, warning_record_count=0,
            error_message=None, ext_message=None):
        self.sudo().write(
            {
                "complete_date": datetime.now(),
                "action_state": action_state,
                "total_record_count": total_record_count,
                "success_record_count": success_record_count,
                "fail_record_count": fail_record_count,
                "ignore_record_count": ignore_record_count,
                "warning_record_count": warning_record_count,
                "error_message": error_message,
                "ext_message": ext_message,
            }
        )
        # self._cr.commit()

    def _prepare_log_line(self, code_ref, name_ref, action_state, error_message, ext_message, model_id, res_id):

        if not isinstance(model_id, int):
            if model_id:
                model_id = model_id.id
            else:
                model_id = False

        if not isinstance(res_id, int):
            if res_id:
                res_id = res_id.id
            else:
                res_id = False

        vals = {
            'log_book_id': self.id if self.id else False,
            'code_ref': code_ref,
            'name_ref': name_ref,
            'action_state': action_state,
            'error_message': error_message,
            'ext_message': ext_message,
            'model_id': model_id,
            'res_id': res_id,
            }
        return vals

    def add_log_line(self, code_ref, name_ref, action_state, error_message, ext_message, model_id, res_id):
        vals = self._prepare_log_line(
            code_ref=code_ref, name_ref=name_ref, action_state=action_state,
            error_message=error_message, ext_message=ext_message, model_id=model_id, res_id=res_id)
        log_line = self.sudo().log_book_lines.create(vals)
        # log_line._cr.commit()
        return log_line

    def add_log_lines(self, log_line_list):
        log_lines = self.sudo().log_book_lines.create(log_line_list)
        # log_lines._cr.commit()
        return log_lines
