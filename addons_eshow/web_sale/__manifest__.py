# Copyright 2021-2025 Tim Wang
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl-3.0).

{
    "name": "EShow Web Sale",
    "author": "Tim Wang",
    "version": "14.0.0.0.1",
    "summary": "Use this module to manage web sale data.",
    "website": "https://max-share.com",
    "category": "EShow/EShow",
    "depends": ["base", "product", "mrp_mps"],
    "data": [
        "data/marketplace.xml",
        "data/shipping_schedule.xml",
        "security/web_sale.xml",
        "security/ir.model.access.csv",
        "views/marketplace_views.xml",
        "views/shipping_method_views.xml",
        "views/shop_views.xml",
        "views/shop_warehouse_views.xml",
        "views/shop_product_view.xml",
        "views/shop_inventory_view.xml",
        "views/shop_product_weekly_stat_view.xml",
        "views/shipping_schedule_view.xml",
        "views/shipping_schedule_group_view.xml",
        "views/web_sale_view.xml",
        "wizard/shipping_schedule_wizard.xml",
    ],
    'assets': {
        'web.assets_backend': [
            'web_sale/static/src/js/client_action.js',
            'web_sale/static/src/scss/client_action.scss',
        ],
        'web.assets_qweb': [
            'web_sale/static/src/xml/qweb_templates.xml',
        ],
    },

    "demo": [],
    "license": "LGPL-3",
    "installable": True,
    "application": True,
}
