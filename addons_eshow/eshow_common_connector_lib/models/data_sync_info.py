# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
from odoo import models, fields, api


class DataSyncInfo(models.Model):
    _name = "connector.data.sync.info"
    _description = "Data Import/Export Information"

    operation_name = fields.Char("Operation", index=True)
    model_id = fields.Many2one("ir.model", string="Model", index=True)
    res_id = fields.Integer("Record ID", index=True)
    last_import_time = fields.Datetime("Last Successfully Import Time")
    last_export_time = fields.Datetime("Last Successfully Export Time")

    _sql_constraints = [
        ('data_sync_info_uniq1', 'unique(operation_name,model_id,res_id)', 'Internal Reference must be unique'),
    ]

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
