# Copyright 2021-2025 Tim Wang
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl-3.0).

{
    "name": "Lingxing Connector",
    "author": "Tim Wang",
    "version": "14.0.0.0.1",
    "summary": "Use this module to connect Lingxing Server.",
    "website": "https://max-share.com",
    "category": "EShow/EShow",
    "depends": ["base", "product", "web_sale", "eshow_common_connector_lib"],
    "data": [
        "data/lingxing_connector_data.xml",
        "data/lingxing_connector_cron.xml",
        "security/ir.model.access.csv",
        "views/marketplace_views.xml",
        "views/shop_views.xml",
        "views/product_views.xml",
        "views/lingxing_connector_views.xml",
        "wizard/lingxing_connector_wizard.xml",
    ],
    "demo": [],
    "assets": {
        "web.report_assets_common": [
        ],
        "web.assets_common": [
        ],
        "web.assets_backend": [
            "lingxing_connector/static/src/js/web_shop_list_controller.js",
            "lingxing_connector/static/src/js/web_shop_list_view.js",
            "lingxing_connector/static/src/js/product_list_controller.js",
            "lingxing_connector/static/src/js/product_list_view.js",
        ],
        "web.assets_tests": [
        ],
        "web.qunit_suite_tests": [
        ],
        "web.assets_qweb": [
            "lingxing_connector/static/src/xml/web_shop.xml",
            "lingxing_connector/static/src/xml/product.xml",
        ],
    },

    "license": "LGPL-3",
    "installable": True,
    "application": True,
}
