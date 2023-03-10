# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
from odoo import models, fields, api


class LogBookLine(models.Model):
    _name = "eshow.log.book.line"
    _description = "Log Book Line"

    log_book_id = fields.Many2one('eshow.log.book', ondelete="cascade", index=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="log_book_id.company_id",
        string='Company', store=True, readonly=True, index=True)

    code_ref = fields.Char("Reference")
    name_ref = fields.Char("Name")
    action_state = fields.Selection(
        selection=[('success', 'Success'), ('created', 'Created'), ('updated', 'Updated'), ('deleted', 'Deleted'),
                   ('failed', 'Failed'), ('ignored', 'Ignored'), ('warning', 'Warning')],
        default='in-progress', index=True,)
    error_message = fields.Text("Error Message")
    ext_message = fields.Text("Extend Message")
    model_id = fields.Many2one("ir.model", string="Model")
    res_id = fields.Integer("Record ID")

    attachment_id = fields.Many2one('ir.attachment', string="Attachment")
    file_name = fields.Char("File Name")

    @api.model
    def get_model_id(self, model_name):
        """ Used to get model id.
            @param model_name: Name of model, like sale.order
            @return: It will return record of model.
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 23 September 2021 .
            Task_id: 178058
        """
        model = self.env['ir.model'].search([('model', '=', model_name)])
        if model:
            return model.id
        return False

    def search(self, args, offset=0, limit=None, order=None, count=False):
        # 重写函数,返回指定记录
        args = args or []
        params = self.env.context.get('params', False)
        domain = []
        if params:
            model = params.get("model", False)
            view_type = params.get("view_type", False)
            if model == "eshow.log.book" and view_type == "form":
                id = params.get("id", False)
                log_book = self.env[model].browse([id])
                line_filter = log_book.line_filter
                if line_filter and line_filter != "all":
                    domain.extend([('action_state', '=', log_book.line_filter)])
                    args += domain
        return super(LogBookLine, self).search(args, offset, limit, order, count)
