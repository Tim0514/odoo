# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
from odoo import models, fields, api


class LogBookLine(models.Model):
    _name = "eshow.log.book.line"
    _description = "Log Book Line"

    log_book_id = fields.Many2one('eshow.log.book', ondelete="cascade")
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="log_book_id.company_id",
        string='Company', store=True, readonly=True)

    code_ref = fields.Char("Reference")
    name_ref = fields.Char("Name")
    action_state = fields.Selection(
        selection=[('in-progress', 'In Progress'), ('success', 'Success'), ('fail', 'Fail'), ('warning', 'Warning')],
        default='in-progress')
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
