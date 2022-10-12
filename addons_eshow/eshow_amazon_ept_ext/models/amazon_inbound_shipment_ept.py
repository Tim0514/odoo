# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

"""
Added class, methods and fields to process to create or update inbound shipment.
"""

import base64
import os
import time
import zipfile
import logging
from datetime import datetime
import dateutil.parser
from odoo import models, fields, api, _
from odoo.addons.iap.tools import iap_tools
from odoo.exceptions import UserError
try:
    from _collections import defaultdict
except ImportError:
    pass

class InboundShipmentEpt(models.Model):
    """
    Added class to process to create or update inbound shipment.
    """
    _inherit = "amazon.inbound.shipment.ept"

    amazon_product_id = fields.Many2one('amazon.product.ept',
                                        related='odoo_shipment_line_ids.amazon_product_id', string='Amazon Product')
