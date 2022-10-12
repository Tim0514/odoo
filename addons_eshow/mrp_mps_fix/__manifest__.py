# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'EShow MRP MPS修正',
    'summary': 'MRP MPS修正',
    'description': """
        1）MPS运算时，通过设置GroupId将不同计算期间的补货按计算期间分开，不要保存到一起去。
        2）（在Odoo15中已经禁用）解决MPS翻页的BUG
    """,
    'version': '14.0.1.0.0',
    'category': 'EShow/EShow',
    'website': 'http://www.max-share.com/',
    'author': 'Tim Wang',
    'license': 'AGPL-3',
    'application': False,
    'installable': True,
    'depends': [
        'mrp_mps',
    ],
    'data': [
        # "views/mrp_mps_templates.xml",
    ],
}
