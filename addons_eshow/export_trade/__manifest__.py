# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'Export Trade',
    'summary': '出口贸易相关操作',
    'description': """
    """,
    'version': '15.0.1.0.0',
    'category': 'EShow/EShow',
    'website': 'http://www.max-share.com/',
    'author': 'Tim Wang',
    'license': 'AGPL-3',
    'application': True,
    'installable': True,
    'depends': [
        'base',
        'sale',
        'stock',
    ],
    'data': [
        'data/customs_declaration_data.xml',
        'security/ir.model.access.csv',
        'views/stock_move_view.xml',
        'views/customs_declaration_view.xml',
    ],
}
