# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

"""
Added class and
"""

import html
import math
import time
from datetime import datetime, timedelta

from odoo import models, fields, api, _
from odoo.addons.iap.tools import iap_tools
from odoo.exceptions import UserError

PRODUCT_PRODUCT = 'product.product'
AMAZON_PRODUCT_EPT = 'amazon.product.ept'
FEED_SUBMISSION_HISTORY = 'feed.submission.history'
STOCK_HEIGHTS = "Stock Height"
DATE_YMDHMS = "%Y-%m-%d %H:%M:%S"

class AmazonProductEpt(models.Model):
    """
    Added class to manage amazon product in odoo.
    """
    _inherit = "amazon.product.ept"




    def name_get(self):
        """
        获取的产品名称格式为[seller_sku] name
        """
        result = []
        for product in self.sudo():
            name = '[%s] %s' % (product.seller_sku, product.name)
            result.append((product.id, name))
        return result