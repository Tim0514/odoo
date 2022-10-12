# -*- coding: utf-8 -*-

{
    'name': '会计科目表 -- 开源智造提供',
    'version': '1.0',
    'category': 'Accounting/Localizations/Account Charts',
    'author': 'OSCG',
    'website': 'http://www.oscg.cn',
    'description': """
    中国会计科目表
    """,
    'depends': ['base', 'account', 'l10n_multilang'],
    'data': [
        'data/l10n_cn_oscg_chart_data.xml',
        'data/currency_rate.xml',
    ],
    'license': 'GPL-3',
    'post_init_hook': '_auto_set_cn_default',

}
