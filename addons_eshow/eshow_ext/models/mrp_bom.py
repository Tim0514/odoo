# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_round

from itertools import groupby
from collections import defaultdict


class MrpBomLine(models.Model):
    _inherit = 'mrp.bom.line'

    is_main_material = fields.Boolean('是否为主原料', default=False, store=True)
