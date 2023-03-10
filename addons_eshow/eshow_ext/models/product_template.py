# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import itertools
import logging
from collections import defaultdict

from odoo import api, fields, models, tools, _, SUPERUSER_ID
from odoo.exceptions import ValidationError, RedirectWarning, UserError
from odoo.osv import expression

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = "product.template"
    _order = "default_code, name"

    # Default Code 增加唯一性约束, 必填
    default_code = fields.Char(
        'Internal Reference', compute='_compute_default_code',
        inverse='_set_default_code', store=True, copy=False, index=True)

    # 项目编号
    project_no = fields.Char(
        'Project No', store=True, copy=True)

    # 最小包装数
    minimum_package_qty = fields.Float(string="最小包装数(MPQ)", default=1, help="产品每箱的最小数量，用于采购或发货。")


    # 有BOM的产品补货提前期
    # 需要生产的产品，在进行补货操作时，系统仅考虑了制造提前期，未考虑原材料采购需要的时间。
    # 因此，增加此字段，用于人工设定一个合理的产品制造的补货提前期。
    # 在执行手动立即补货的操作时，生成的制造订单完工日期为  当前日期+produce_delay+manuf_procure_delay
    # 在执行MPS运算时，总提前期为 该产品各个路线规则的提前期+produce_delay+manuf_procure_delay
    manuf_procure_delay = fields.Integer('产成品补货提前期', compute='_compute_manuf_procure_delay',
        inverse='_set_manuf_procure_delay', store=True, copy=True, default=28)

    # Volume改为只读
    volume = fields.Float(
        'Volume', compute='_compute_volume', inverse='_set_volume', digits='Volume', store=True, readonly='true')

    length = fields.Float(
        'Length', compute='_compute_length', inverse='_set_length', digits='Length', store=True)
    length_uom_name = fields.Char(string='Length unit of measure label', compute='_compute_length_uom_name')

    width = fields.Float(
        'Width', compute='_compute_width', digits='Length',
        inverse='_set_width', store=True)
    width_uom_name = fields.Char(string='Width unit of measure label', compute='_compute_width_uom_name')

    height = fields.Float(
        'Height', compute='_compute_height', digits='Length',
        inverse='_set_height', store=True)
    height_uom_name = fields.Char(string='Height unit of measure label', compute='_compute_height_uom_name')

    volume_weight_5000 = fields.Float(
        'Volume Weight 5000', compute='_compute_volume_weight_5000', digits='Stock Weight',
        inverse='_set_volume_weight_5000', store=True, readonly=True)

    volume_weight_6000 = fields.Float(
        'Volume Weight 6000', compute='_compute_volume_weight_6000', digits='Stock Weight',
        inverse='_set_volume_weight_6000', store=True, readonly=True)

    weight = fields.Float(
        'Shipping Weight', compute='_compute_weight', digits='Stock Weight',
        inverse='_set_weight', store=True, readonly=True)

    actual_weight = fields.Float(
        'Actual Weight', compute='_compute_actual_weight', digits='Stock Weight',
        inverse='_set_actual_weight', store=True)

    customs_declare_currency_id = fields.Many2one(
        'res.currency', 'Customs Declaration Currency',
        compute='_compute_customs_declare_currency_id', inverse='_set_customs_declare_currency_id')

    maxshare_price = fields.Float('MaxShare Price', digits='Product Price', store=False, readonly=True,
                                    compute='_compute_maxshare_price', inverse='_set_maxshare_price',
                                    help='Price For Max Share (Cost * Max Share Price Rate)')
    export_declare_price = fields.Float('Export Declare Price(USD)', digits='Product Price', store=False, readonly=True,
                                        compute='_compute_export_declare_price', inverse='_set_export_declare_price',
                                        help='Price For Export Custom Declaration (Cost * Max Share Price Rate * Export Declare Price Rate * USD Exchange Rate)')
    destination_declare_price = fields.Float('Destination Declare Price(USD)', digits='Product Price', store=False, readonly=True,
                                             compute='_compute_destination_declare_price', inverse='_set_destination_declare_price',
                                             help='Price For Destination Custom Declaration (Cost * Destination Declare Price Rate * USD Exchange Rate')

    # 自动设置List Price
    list_price = fields.Float(
        'Sales Price', default=1.0,
        store=True,
        compute='_compute_list_price',
        digits='Product Price',
        help="Price at which the product is sold to customers.",
    )

    standard_price = fields.Float(
        'Cost', compute='_compute_standard_price',
        store=True,
        inverse='_set_standard_price', search='_search_standard_price',
        digits='Product Price', groups="base.group_user",
        help="""In Standard Price & AVCO: value of the product (automatically computed in AVCO).
        In FIFO: value of the next unit that will leave the stock (automatically computed).
        Used to value the product when the purchase cost is not known (e.g. inventory adjustment).
        Used to compute margins on sale orders.""")

    _sql_constraints = [
        ('default_code_uniq', 'unique(company_id, default_code)', 'Internal Reference must be unique'),
        # ('barcode_uniq', 'unique(barcode)', "A barcode can only be assigned to one product !"),
    ]

    @api.depends('product_variant_ids', 'product_variant_ids.default_code')
    def _compute_default_code(self):
        unique_variants = self.filtered(lambda template: len(template.product_variant_ids) == 1)
        for template in unique_variants:
            template.default_code = template.product_variant_ids.default_code
        # timwang modified at 2021/8/26
        # 注释下面的语句，防止有变体的产品把模板的default_code置空
        # for template in (self - unique_variants):
        #     template.default_code = False

    @api.depends('product_variant_ids', 'product_variant_ids.default_code')
    def _compute_manuf_procure_delay(self):
        unique_variants = self.filtered(lambda template: len(template.product_variant_ids) == 1)
        for template in unique_variants:
            template.manuf_procure_delay = template.product_variant_ids.manuf_procure_delay
        for template in (self - unique_variants):
            template.manuf_procure_delay = False

    def _set_manuf_procure_delay(self):
        for template in self:
            if len(template.product_variant_ids) == 1:
                template.product_variant_ids.manuf_procure_delay = template.manuf_procure_delay

    @api.depends('product_variant_ids', 'product_variant_ids.length')
    def _compute_length(self):
        unique_variants = self.filtered(lambda template: len(template.product_variant_ids) == 1)
        for template in unique_variants:
            template.length = template.product_variant_ids.length
        for template in (self - unique_variants):
            template.length = 0.0

    def _set_length(self):
        for template in self:
            if len(template.product_variant_ids) == 1:
                template.product_variant_ids.length = template.length

    @api.depends('product_variant_ids', 'product_variant_ids.width')
    def _compute_width(self):
        unique_variants = self.filtered(lambda template: len(template.product_variant_ids) == 1)
        for template in unique_variants:
            template.width = template.product_variant_ids.width
        for template in (self - unique_variants):
            template.width = 0.0

    def _set_width(self):
        for template in self:
            if len(template.product_variant_ids) == 1:
                template.product_variant_ids.width = template.width
                
    @api.depends('product_variant_ids', 'product_variant_ids.height')
    def _compute_height(self):
        unique_variants = self.filtered(lambda template: len(template.product_variant_ids) == 1)
        for template in unique_variants:
            template.height = template.product_variant_ids.height
        for template in (self - unique_variants):
            template.height = 0.0

    def _set_height(self):
        for template in self:
            if len(template.product_variant_ids) == 1:
                template.product_variant_ids.height = template.height
                
    @api.depends('product_variant_ids', 'product_variant_ids.volume_weight_5000')
    def _compute_volume_weight_5000(self):
        unique_variants = self.filtered(lambda template: len(template.product_variant_ids) == 1)
        for template in unique_variants:
            template.volume_weight_5000 = template.product_variant_ids.volume_weight_5000
        for template in (self - unique_variants):
            template.volume_weight_5000 = 0.0

    def _set_volume_weight_5000(self):
        for template in self:
            if len(template.product_variant_ids) == 1:
                template.product_variant_ids.volume_weight_5000 = template.volume_weight_5000

    @api.depends('product_variant_ids', 'product_variant_ids.volume_weight_6000')
    def _compute_volume_weight_6000(self):
        unique_variants = self.filtered(lambda template: len(template.product_variant_ids) == 1)
        for template in unique_variants:
            template.volume_weight_6000 = template.product_variant_ids.volume_weight_6000
        for template in (self - unique_variants):
            template.volume_weight_6000 = 0.0

    def _set_volume_weight_6000(self):
        for template in self:
            if len(template.product_variant_ids) == 1:
                template.product_variant_ids.volume_weight_6000 = template.volume_weight_6000

    @api.depends('product_variant_ids', 'product_variant_ids.actual_weight')
    def _compute_actual_weight(self):
        unique_variants = self.filtered(lambda template: len(template.product_variant_ids) == 1)
        for template in unique_variants:
            template.actual_weight = template.product_variant_ids.actual_weight
        for template in (self - unique_variants):
            template.actual_weight = 0.0

    def _set_actual_weight(self):
        for template in self:
            if len(template.product_variant_ids) == 1:
                template.product_variant_ids.actual_weight = template.actual_weight

    def _compute_length_uom_name(self):
        # uom_category = self.env['uom.category'].search("[('name', '=', 'Length / Distance'),]", limit=1)
        #
        # self.length_uom_name = uom_category.reference_uom_id.name
        self.length_uom_name = self._get_length_uom_name_from_ir_config_parameter()

    @api.depends('length_uom_name')
    def _compute_width_uom_name(self):
        self.width_uom_name = self.length_uom_name

    @api.depends('length_uom_name')
    def _compute_height_uom_name(self):
        self.height_uom_name = self.length_uom_name

    def _compute_customs_declare_currency_id(self):
        unique_variants = self.filtered(lambda template: len(template.product_variant_ids) == 1)
        for template in unique_variants:
            template.customs_declare_currency_id = template.product_variant_ids.customs_declare_currency_id
        for template in (self - unique_variants):
            template.customs_declare_currency_id = False

    def _set_customs_declare_currency_id(self):
        for template in self:
            if len(template.product_variant_ids) == 1:
                template.product_variant_ids.customs_declare_currency_id = template.customs_declare_currency_id

    @api.depends_context('company')
    @api.depends('standard_price')
    def _compute_list_price(self):
        maxshare_price_rate = float(self.env['ir.config_parameter'].sudo().get_param('eshow_ext.maxshare_price_rate'))

        unique_variants = self.filtered(lambda template: len(template.product_variant_ids) == 1)
        for template in unique_variants:
            template.list_price = template.standard_price * maxshare_price_rate
        for template in (self - unique_variants):
            template.list_price = 0.0


    @api.depends_context('company')
    @api.depends('product_variant_ids', 'product_variant_ids.maxshare_price')
    def _compute_maxshare_price(self):
        # maxshare_price_rate = float(self.env['ir.config_parameter'].sudo().get_param('eshow_ext.maxshare_price_rate'))

        unique_variants = self.filtered(lambda template: len(template.product_variant_ids) == 1)
        for template in unique_variants:
            template.maxshare_price = template.product_variant_ids.maxshare_price
        for template in (self - unique_variants):
            template.maxshare_price = 0.0

    def _set_maxshare_price(self):
        for template in self:
            if len(template.product_variant_ids) == 1:
                template.product_variant_ids.maxshare_price = template.maxshare_price
                template.product_variant_ids.list_price = template.product_variant_ids.maxshare_price

    @api.depends_context('company')
    @api.depends('product_variant_ids', 'product_variant_ids.export_declare_price')
    def _compute_export_declare_price(self):
        unique_variants = self.filtered(lambda template: len(template.product_variant_ids) == 1)
        for template in unique_variants:
            template.export_declare_price = template.product_variant_ids.export_declare_price
        for template in (self - unique_variants):
            template.export_declare_price = 0.0

    def _set_export_declare_price(self):
        for template in self:
            if len(template.product_variant_ids) == 1:
                template.product_variant_ids.export_declare_price = template.export_declare_price

    @api.depends_context('company')
    @api.depends('product_variant_ids', 'product_variant_ids.destination_declare_price')
    def _compute_destination_declare_price(self):
        unique_variants = self.filtered(lambda template: len(template.product_variant_ids) == 1)
        for template in unique_variants:
            template.destination_declare_price = template.product_variant_ids.destination_declare_price
        for template in (self - unique_variants):
            template.destination_declare_price = 0.0

    def _set_destination_declare_price(self):
        for template in self:
            if len(template.product_variant_ids) == 1:
                template.product_variant_ids.destination_declare_price = template.destination_declare_price