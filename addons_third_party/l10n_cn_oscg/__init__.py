# -*- coding: utf-8 -*-

from odoo import api, SUPERUSER_ID

def _auto_set_cn_default(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    # 1. 安装和设置中国会计科目表
    module_ids = env['ir.module.module'].search([('name', 'in', ['l10n_cn_small_business','l10n_cn_standard']), ('state', '=', 'installed')])
    module_ids.sudo().button_uninstall()
    chart_template_id = env.ref('l10n_cn_oscg.l10n_chart_oscg', raise_if_not_found=False)
    chart_template_id._load(13.0, 13.0, env.company)
    
    # 2. 修改中文时间显示格式
    zh_CN = env.ref('base.lang_zh_CN', raise_if_not_found=False)
    zh_CN.write({'date_format': '%Y/%m/%d','time_format':'%H:%M:%S'})
    
    # 3. Partner国家默认为中国，语言默认为中文
    partner_country = env.ref('base.field_res_partner__country_id', raise_if_not_found=False)
    partner_lang = env.ref('base.field_res_partner__lang', raise_if_not_found=False)
    cn = env.ref('base.cn', raise_if_not_found=False)
    env['ir.default'].search(['|',('field_id','=',partner_lang.id),('field_id','=',partner_country.id)]).unlink()
    env['ir.default'].create([
        {'field_id': partner_country.id, 'json_value': cn.id},
        {'field_id': partner_lang.id, 'json_value': '"zh_CN"'}
       ])
       
    # 4. Price小数位数默认设置为4位，数量小数位数默认设置为2位
    env.ref('product.decimal_price', raise_if_not_found=False).write({'digits': 4})
    env.ref('product.decimal_product_uom', raise_if_not_found=False).write({'digits': 2})
    
    # 5. 人民币汇率默认设置为1.0 ，美元默认为6.9，欧元为 7.8. 汇率转换小数默认设置为4位
    env.ref('base.CNY', raise_if_not_found=False).write({'rounding': 0.0001})
    env.ref('base.EUR', raise_if_not_found=False).write({'rounding': 0.0001})
    env.ref('base.USD', raise_if_not_found=False).write({'rounding': 0.0001})
