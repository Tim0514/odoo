# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'EShow EMark',
    'summary': '给打印的报表增加电子图章',
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
        'base',
        'purchase',
    ],
    'data': [
        'views/res_company_views.xml',
    ],
}
