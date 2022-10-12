# -*- coding: utf-8 -*-

{
    "name": "采购预付款",
    "version": "0.1",
    "license": 'AGPL-3',
    "depends": [
        "purchase",
        "account_advance_payment",
    ],
    "author": "OSCG",
    "description": """采购预付款
采购订单上增加预付款的页签
    """,
    "website": "http://www.oscg.cn",
    "category": "Accounting & Finance",
    "sequence": 32,
    "data": [
        "views/purchase_order_view.xml",
    ],
    "demo": [],
    'test': [],
    "auto_install": False,
    "installable": True,
    "application": False,
}
