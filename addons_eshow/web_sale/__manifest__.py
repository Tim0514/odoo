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
        "data/mrp_mps_data.xml",
        "security/web_sale.xml",
        "security/ir.model.access.csv",
        "views/web_sale_view.xml",
        "views/res_partner_views.xml",
        "views/shop_product_view.xml",
        "views/shop_sale_data_view.xml",
        "views/mrp_production_schedule_master_view.xml",
        "wizard/mrp_production_schedule_master_compute.xml",
    ],
    "demo": [],
    "license": "LGPL-3",
    "installable": True,
    "application": True,
}
