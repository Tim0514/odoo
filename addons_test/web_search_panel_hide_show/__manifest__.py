# -*- coding: utf-8 -*-
{
    'name': "Search Panel Hide & Show",

    'summary': """
        Enable search panel hide & show by a toggle button.
        -- 通过切换按钮启用搜索面板的隐藏和显示
        """,

    'description': """
      Enable search panel hide & show by a toggle button.
    """,

    'images': ['static/description/01.png'],

    'author': "yao",
    'website': "low_design@163.com",


    'category': 'Extra Tools',
    'version': '14.0.1.1.0',
    'license': 'OPL-1',

    'depends': ['base'],


    'data': [
    ],

    'qweb': [
    ],

    "assets": {
        "web.report_assets_common": [
        ],
        "web.assets_common": [
        ],
        "web.assets_backend": [
            "web_search_panel_hide_show/static/src/css/search_panel_hide_show.css",
            "web_search_panel_hide_show/static/src/js/search_panel_hide_show.js",
        ],
        "web.assets_tests": [
        ],
        "web.qunit_suite_tests": [
        ],
        "web.assets_qweb": [
            "web_search_panel_hide_show/static/src/xml/search_panel.xml",
        ],
    },

    'price': '0',
    'currency': 'EUR',
}
