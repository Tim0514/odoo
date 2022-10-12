# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta
from collections import namedtuple, OrderedDict, defaultdict
from odoo import models, api, fields
from odoo.tools import float_compare, float_round
from odoo.exceptions import ValidationError


class ReportBomStructure(models.AbstractModel):
    _inherit = 'report.mrp.report_bom_structure'

    def _check_bom_recursion(self, bom, bom_products):
        """检查BoM是否存在父子循环
        """
        def set_parent_flag(bom2, bom_products2, flag):
            if bom2.product_id:
                bom_products2[bom2.product_id] = flag
            else:
                for p in bom2.product_tmpl_id.product_variant_ids:
                    bom_products2[p] = flag

        bom.ensure_one()
        set_parent_flag(bom, bom_products, 1)
        for line in bom.bom_line_ids:
            if bom_products.get(line.product_id, False):
                raise ValidationError("BoM (id=%s) 的儿子产品 %s 存在父子循环！" % (bom.id, line.product_id.name))
            if line.child_bom_id:
                self._check_bom_recursion(line.child_bom_id, bom_products)
        set_parent_flag(bom, bom_products, 0)

    @api.model
    def _get_report_data(self, bom_id, searchQty=0, searchVariant=False):
        bom = self.env['mrp.bom'].browse(bom_id)
        bom_products={}
        self._check_bom_recursion(bom, bom_products)
        
        return super(ReportBomStructure, self)._get_report_data(bom_id, searchQty, searchVariant)
