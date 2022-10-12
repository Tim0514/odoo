# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'EShow Amazon Ept Ext',
    'summary': 'EShow对Amazon Ept模块针对本公司业务需求进行的扩展',
    'description': """
    """,
    'version': '15.0.1.0.0',
    'category': 'EShow/EShow',
    'website': 'http://www.max-share.com/',
    'author': 'Tim Wang',
    'license': 'AGPL-3',
    'application': False,
    'installable': True,
    'depends': [
        'amazon_ept',
    ],
    'data': [
        'views/inbound_shipment_plan.xml',
        'views/inbound_shipment_ept.xml',
        'views/product_view.xml',
    ],
}
