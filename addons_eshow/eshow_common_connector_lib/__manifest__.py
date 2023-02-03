# Copyright 2021-2025 Tim Wang
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl-3.0).

{
    "name": "EShow Common Connector Libraries",
    "author": "Tim Wang",
    "version": "14.0.0.0.1",
    "summary": "Base module for connectors.",
    "website": "https://max-share.com",
    "category": "EShow/EShow",
    "depends": ["base", "mail", ],
    "data": [
        "data/log_book_data.xml",
        "security/common_connector.xml",
        "security/ir.model.access.csv",
        "views/common_connector_view.xml",
        "views/log_book_view.xml",
    ],
    "demo": [],
    "assets": {
        "web.report_assets_common": [
        ],
        "web.assets_common": [
        ],
        "web.assets_backend": [
        ],
        "web.assets_tests": [
        ],
        "web.qunit_suite_tests": [
        ],
        "web.assets_qweb": [
        ],
    },
    "license": "LGPL-3",
    "installable": True,
    "application": True,
}
