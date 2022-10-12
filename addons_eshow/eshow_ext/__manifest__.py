# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'EShow 扩展',
    'summary': 'EShow对各个模块的自定义设置和字段扩展',
    'description': """
        res.partner
        1) 增加简称，默认联系人，修改相关界面。
        
        stock.warehouse
        1) 缩写码(Code)改成8位
                
        stock.rule
        1）查询列表显示Rule名称
        
        product.template, product.product
        1) 增加长宽高，体积重量，发运重量，茂翔结算价，出口申报价(美金)，目的国申报价(美金),等字段。
        2) default_code添加唯一性限制,翻译名称改为 物料编码
        3) 调整界面显示，default_code调整到产品名称前面，增加 Shipping的页面卡
        
        product.attribute
        1) 增加属性缩写码, code字段
        2）调整界面显示
    """,
    'version': '14.0.1.0.0',
    'category': 'EShow/EShow',
    'website': 'http://www.max-share.com/',
    'author': 'Tim Wang',
    'license': 'AGPL-3',
    'application': False,
    'installable': True,
    'depends': [
        'base', 'product', 'mrp', 'purchase_stock', 'eshow_emark',
    ],
    'data': [
        'views/product_views.xml',
        'views/stock_rule_views.xml',
        'views/mrp_bom_views.xml',
        'views/mrp_bom_line_views.xml',
        'views/res_partner_views.xml',
        'views/stock_picking_views.xml',
        'views/product_attribute_views.xml',
        'views/stock_orderpoint_views.xml',
        'views/res_config_settings_views.xml',
        'views/stock_move_views.xml',
        'views/sale_views.xml',
        'report/report_templates.xml',
        'report/report_invoice.xml',
        'report/purchase_report_templates.xml',
        'data/product_data.xml',
    ],
}
