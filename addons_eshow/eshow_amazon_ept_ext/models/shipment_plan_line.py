# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
Added class inbound shipment plan line and method to prepare dict to update shipment in amazon
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class InboundShipmentPlanLine(models.Model):
    """
    Added class to prepare dict and process to update shipment in amazon.
    """
    _inherit = "inbound.shipment.plan.line"

    @api.onchange('amazon_product_id')
    def onchange_instance_id(self):
        """
        This will set the case quantity
        """
        for line in self:
            if line.odoo_product_id:
                line.quantity_in_case = line.odoo_product_id.minimum_package_qty
            else:
                line.quantity_in_case = 0
            if not line.quantity or line.quantity == 0:
                line.quantity = line.quantity_in_case


