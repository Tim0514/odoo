# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import re

from odoo import api, fields, models, tools, _


_logger = logging.getLogger(__name__)


class ProductProduct(models.Model):
    _inherit = "product.product"

    # Default Code 增加唯一性约束
    default_code = fields.Char('Internal Reference', index=True, copy=False)

    # 有BOM的产品补货提前期
    # 需要生产的产品，在进行补货操作时，系统仅考虑了制造提前期，未考虑原材料采购需要的时间。
    # 因此，增加此字段，用于人工设定一个合理的产品制造的补货提前期。
    # 在执行手动立即补货的操作时，生成的制造订单完工日期为  当前日期+bom_material_delay
    # 在执行MPS运算时，总提前期为 该产品各个路线规则的提前期+bom_material_delay
    manuf_procure_delay = fields.Float('制造产品补货提前期', store=True, copy=True)

    # 体积
    volume = fields.Float('Volume', digits='Volume', compute='_compute_volume', store=True, readonly=True)

    length = fields.Float('Length', digits='Length', store=True)
    width = fields.Float('Width', digits='Length', store=True)
    height = fields.Float('Height', digits='Length', store=True)

    volume_weight_5000 = fields.Float('Volume Weight 5000', digits='Stock Weight', readonly=True,
                                      compute='_compute_volume_weight_5000', store=True)
    volume_weight_6000 = fields.Float('Volume Weight 6000', digits='Stock Weight', readonly=True,
                                      compute='_compute_volume_weight_6000', store=True)
    actual_weight = fields.Float('Actual Weight', digits='Stock Weight')

    weight = fields.Float('Shipping Weight', digits='Stock Weight', readonly=True,
                                   compute='_compute_weight', store=True)


    customs_declare_currency_id = fields.Many2one(
        'res.currency', 'Customs Declaration Currency',
        compute='_compute_customs_declare_currency_id',)

    maxshare_price = fields.Float('MaxShare Price', digits='Product Price', store=False, readonly=True,
                                        compute='_compute_maxshare_price',
                                        help='Price For Max Share (Cost * Max Share Price Rate)')
    export_declare_price = fields.Float('Export Declare Price(USD)', digits='Product Price', store=False, readonly=True,
                                        compute='_compute_export_declare_price',
                                        help='Price For Export Custom Declaration (Cost * Max Share Price Rate * Export Declare Price Rate * USD Exchange Rate)')
    destination_declare_price = fields.Float('Destination Declare Price(USD)', digits='Product Price', store=False, readonly=True,
                                        compute='_compute_destination_declare_price',
                                        help='Price For Destination Custom Declaration (Cost * Destination Declare Price Rate * USD Exchange Rate')

    _sql_constraints = [
        ('default_code_uniq1', 'unique(default_code)', 'Internal Reference must be unique'),
    ]

    @api.depends('length', 'width', 'height')
    def _compute_volume(self):
        product_length_in_feet_param = self.env['ir.config_parameter'].sudo().get_param(
            'product.volume_in_cubic_feet')
        for product in self:
            if product_length_in_feet_param == '1':
                # 默认单位为英尺，立方英尺
                product.volume = product.length * product.width * product.height
            else:
                # 默认单位为毫米，立方米
                product.volume = product.length * product.width * product.height / pow(10, 3 * 3)

    @api.depends('volume')
    def _compute_volume_weight_5000(self):
        product_length_in_feet_param = self.env['ir.config_parameter'].sudo().get_param(
            'product.volume_in_cubic_feet')

        product_weight_in_lbs_param = self.env['ir.config_parameter'].sudo().get_param('product.weight_in_lbs')

        for product in self:
            if product_weight_in_lbs_param == '1':
                # 默认重量单位为磅
                if product_length_in_feet_param == '1':
                    # 默认单位为英尺，立方英尺
                    product.volume_weight_5000 = product.volume / 35.3147248 * pow(10, 6) / 5000 * 2.2046226
                else:
                    product.volume_weight_5000 = product.volume * pow(10, 6) / 5000 * 2.2046226
            else:
                # 默认重量单位为公斤
                if product_length_in_feet_param == '1':
                    # 默认单位为英尺，立方英尺
                    product.volume_weight_5000 = product.volume / 35.3147248 * pow(10, 6) / 5000
                else:
                    product.volume_weight_5000 = product.volume * pow(10, 6) / 5000

    @api.depends('volume')
    def _compute_volume_weight_6000(self):
        product_length_in_feet_param = self.env['ir.config_parameter'].sudo().get_param(
            'product.volume_in_cubic_feet')

        product_weight_in_lbs_param = self.env['ir.config_parameter'].sudo().get_param('product.weight_in_lbs')

        for product in self:
            if product_weight_in_lbs_param == '1':
                # 默认重量单位为磅
                if product_length_in_feet_param == '1':
                    # 默认单位为英尺，立方英尺
                    product.volume_weight_6000 = product.volume / 35.3147248 * pow(10, 6) / 6000 * 2.2046226
                else:
                    product.volume_weight_6000 = product.volume * pow(10, 6) / 6000 * 2.2046226
            else:
                # 默认重量单位为公斤
                if product_length_in_feet_param == '1':
                    # 默认单位为英尺，立方英尺
                    product.volume_weight_6000 = product.volume / 35.3147248 * pow(10, 6) / 6000
                else:
                    product.volume_weight_6000 = product.volume * pow(10, 6) / 6000

    @api.depends('weight', 'volume_weight_5000', 'volume_weight_6000')
    def _compute_weight(self):
        for product in self:
            if product.actual_weight >= product.volume_weight_6000:
                product.weight = product.actual_weight
            else:
                product.weight = product.volume_weight_6000

    def _compute_customs_declare_currency_id(self):
        customs_declare_currency_id = self.env['res.currency'].with_context(
            active_test=False).search([('name', '=', 'USD')], limit=1)

        if customs_declare_currency_id:
            customs_declare_currency_id = customs_declare_currency_id[0]

        for product in self:
            product.customs_declare_currency_id = customs_declare_currency_id

    @api.depends_context('company')
    @api.depends('standard_price')
    def _compute_maxshare_price(self):
        maxshare_price_rate = float(self.env['ir.config_parameter'].sudo().get_param('eshow_ext.maxshare_price_rate'))

        for product in self:
            product.maxshare_price = product.standard_price * maxshare_price_rate
            product.list_price = product.maxshare_price

            # 反写回template的价格
            template = product.product_tmpl_id
            if len(template.product_variant_ids) == 1:
                template.maxshare_price = product.maxshare_price
                template.list_price = template.maxshare_price

    @api.depends_context('company')
    @api.depends('standard_price')
    def _compute_export_declare_price(self):
        maxshare_price_rate = float(self.env['ir.config_parameter'].sudo().get_param('eshow_ext.maxshare_price_rate'))
        export_declare_price_rate = float(self.env['ir.config_parameter'].sudo().get_param('eshow_ext.export_declare_price_rate'))

        for product in self:
            standard_price_1 = self.price_compute(price_type='standard_price', uom=False, currency=self.customs_declare_currency_id,
                                                  company=None)
            product.export_declare_price = standard_price_1[product.id] * maxshare_price_rate * export_declare_price_rate

            # 反写回template的价格
            template = product.product_tmpl_id
            if len(template.product_variant_ids) == 1:
                template.export_declare_price = product.export_declare_price

    @api.depends_context('company')
    @api.depends('standard_price')
    def _compute_destination_declare_price(self):
        destination_declare_price_rate = float(self.env['ir.config_parameter'].sudo().get_param('eshow_ext.destination_declare_price_rate'))

        for product in self:
            standard_price_1 = self.price_compute(price_type='standard_price', uom=False, currency=self.customs_declare_currency_id,
                                                  company=None)
            product.destination_declare_price = standard_price_1[product.id] * destination_declare_price_rate

            # 反写回template的价格
            template = product.product_tmpl_id
            if len(template.product_variant_ids) == 1:
                template.destination_declare_price = product.destination_declare_price

    def _compute_is_product_variant(self):
        if (not self.product_tmpl_id.attribute_line_ids) and len(self.product_tmpl_id.attribute_line_ids) > 0\
                and len(self.product_template_attribute_value_ids) > 0:
            self.is_product_variant = True
        else:
            self.is_product_variant = False

    """
        Product中的同名方法，company传入有Bug.
        改用Template的方法。
    """
    def price_compute(self, price_type, uom=False, currency=False, company=None):
        # TDE FIXME: delegate to template or not ? fields are reencoded here ...
        # compatibility about context keys used a bit everywhere in the code
        if not uom and self._context.get('uom'):
            uom = self.env['uom.uom'].browse(self._context['uom'])
        if not currency and self._context.get('currency'):
            currency = self.env['res.currency'].browse(self._context['currency'])

        templates = self
        if price_type == 'standard_price':
            # standard_price field can only be seen by users in base.group_user
            # Thus, in order to compute the sale price from the cost for users not in this group
            # We fetch the standard price as the superuser
            templates = self.with_company(company).sudo()
        if not company:
            company = self.env.company
        date = self.env.context.get('date') or fields.Date.today()

        prices = dict.fromkeys(self.ids, 0.0)
        for template in templates:
            prices[template.id] = template[price_type] or 0.0
            # yes, there can be attribute values for product template if it's not a variant YET
            # (see field product.attribute create_variant)
            if price_type == 'list_price' and self._context.get('current_attributes_price_extra'):
                # we have a list of price_extra that comes from the attribute values, we need to sum all that
                prices[template.id] += sum(self._context.get('current_attributes_price_extra'))

            if uom:
                prices[template.id] = template.uom_id._compute_price(prices[template.id], uom)

            # Convert from current user company currency to asked one
            # This is right cause a field cannot be in more than one currency
            if currency:
                prices[template.id] = template.currency_id._convert(prices[template.id], currency, company, date)

        return prices

    """
        Timwang modified 2021/8/27
        从ProductTemplate里面复制一个方法过来
        如果没有这个方法, 导入视图时会报错.
    """
    def action_product_tmpl_forecast_report(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id('stock.stock_replenishment_product_product_action')
        return action
