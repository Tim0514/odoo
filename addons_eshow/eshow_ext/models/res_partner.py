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
class Partner(models.Model):
    _inherit = "res.partner"

    short_name = fields.Char(string='简称', store=True, index=True)
    default_contact_person = fields.Char(string='默认联系人', store=True)
    sale_order_notes = fields.Html(string='销售订单备注', store=True)
    purchase_order_notes = fields.Html(string='采购订单备注', store=True)
