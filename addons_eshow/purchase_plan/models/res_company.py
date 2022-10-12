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
    _inherit = "res.company"

    use_purchase_plan = fields.Boolean(
        string="Use Purchase Plan",
        default=True,
        help="Use Purchase Plan instead of Purchase Order while running procurement.",
    )

