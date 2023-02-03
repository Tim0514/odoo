# -*- coding: utf-8 -*-
{
    'name': "收付款表单上增加预付款功能",

    'summary': """
        提供采购预付款功能：在PO上可以添加预付款Payment，PO账单确认后，可以用预付款冲销账单应付账款
        """,
    'description': """
        【模块功能】
        1) 本模块提供采购预付款功能：在PO上可以添加预付款Payment，PO账单确认后，可以用预付款冲销账单应付账款
        2) Partner上增加预付账款科目设置
        3) account.payment表单上增加字段“是否预付款”，如果是预付款，则确认(Post)时候，自动创建会计凭证：借 应付账款，贷 预付账款
    """,

    'author': "OSCG",
    'website': "http://www.oscg.cn",

    'category': 'Accounting',
    'version': '0.5',

    'depends': ['account'],

    'data': [
        'views/res_partner_view.xml',
        'views/account_payment.xml',
    ],
    'demo': [
    ],
    "installable": True,
    "application": False
}
