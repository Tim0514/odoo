# Copyright 2018-2019 Tim Wang
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl-3.0).

{
    "name": "EShow Purchase Plan",
    "author": "Tim Wang",
    "version": "15.0.0.0.1",
    "summary": "Use this module to have notification of purchase plan of "
    "materials and/or external services",
    "category": "EShow/EShow",
    "depends": ["purchase", "product", "purchase_stock"],
    "data": [
        "security/purchase_plan.xml",
        "security/ir.model.access.csv",
        "data/purchase_plan_sequence.xml",
        "data/purchase_plan_data.xml",
        "wizard/purchase_plan_make_purchase_order_view.xml",
        "views/purchase_plan_view.xml",
        "views/res_company_views.xml",
        "views/purchase_order_view.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
