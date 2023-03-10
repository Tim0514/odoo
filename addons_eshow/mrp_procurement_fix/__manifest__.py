# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'EShow MRP补货Bug修正',
    'summary': 'MRP补货Bug修正',
    'description': """
        1）基于“制造”规则产生MO时候（_run_manufacture），系统没有处理规则的“补货组的传播”字段（group_propagation_option）。
        该字段设置是否应该传播 group_id 到 MO。代码文件 odoo\addons\mrp\models\stock_rule.py   方法 def _prepare_mo_vals 中，
        应该增加字段 group_propagation_option 的处理，将前一级的补货组(group_id) 带入MO的补货组（procurement_group_id）。
        2）外协生产时候，系统基于外协采购入库单，自动创建外协MO，外协MO的补货组（字段 procurement_group_id）是外协采购入库单的单号。
        当外协采购入库单有多个明细行，每个明细行创建一个补货组，一个MO，如此，系统创建了多个同名（都是外协采购入库单的单号）的补货组。
        参考代码 odoo\addons\mrp_subcontracting\models\stock_picking.py  方法 def _prepare_subcontract_mo_vals 。
        这样导致了一个问题，那就是，如果MO缺料，系统自动生成PO采购时候，这些不同MO的即使是同一个原料，系统也会创建不同的PO（不同补货组的缺料需求会分成不同PO）。
        本模块修改此Bug：外协采购入库单在创建MO的补货组的时候，应该先查一下同名补货组是否存在，存在则不要创建新补货组。
        3）实践中发现，用户导入的BoM表，经常出现父子循环，导致BoM结构显示时候报错，错误现象：http://kw.oscg.cn/forum/1/question/bom-1135。
        本模块在显示BoM结构之前先检查BoM是否存在循环产品，存在则报错提示。
    """,
    'version': '14.0.1.0.0',
    'category': 'EShow/EShow',
    'website': 'http://www.oscg.cn/',
    'author': 'OSCG',
    'license': 'AGPL-3',
    'application': False,
    'installable': True,
    'depends': [
        'mrp_subcontracting',
    ],
    'data': [
        'views/mrp_production_views.xml',
        'views/stock_picking_views.xml',
    ],

}
