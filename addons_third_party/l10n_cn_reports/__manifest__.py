# -*- coding: utf-8 -*-

{
    'name': '中国三大财务报表',
    'version': '1.0',
    'category': 'Localization',
    'author': 'OSCG',
    'description': """
        中国三大财务报表：资产负债表、利润表、现金流量表
    """,
    'depends': [
        'l10n_cn_oscg', 'account_reports'
    ],
    'data': [
        'data/account_financial_html_report_data.xml',
        'account_move_print.xml',
        'account_move_report.xml',
    ],
    'installable': True,
    'auto_install': True,
    'website': 'http://www.oscg.cn',
    'license': 'OEEL-1',
}
