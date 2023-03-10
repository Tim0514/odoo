# -*- coding: utf-8 -*-
from odoo import api, fields, models, SUPERUSER_ID, _
from collections import namedtuple, OrderedDict, defaultdict
from odoo import SUPERUSER_ID, models, api, fields
from odoo.tools import float_compare, float_round

from odoo.addons.stock.models.stock_rule import ProcurementException

import logging
_logger = logging.getLogger(__name__)


class StockRule(models.Model):
    _inherit = 'stock.rule'

    """
    增加传播组的设置
    """
    def _prepare_mo_vals(self, product_id, product_qty, product_uom, location_id, name, origin, company_id, values, bom):
        mo_vals = super(StockRule, self)._prepare_mo_vals(product_id, product_qty, product_uom, location_id, name, origin, company_id, values, bom)

        gpo = self.group_propagation_option
        group_id = (gpo == 'fixed' and self.group_id.id) or \
                (gpo == 'propagate' and values.get('group_id')) or False

        if group_id and not isinstance(group_id, int):
            group_id = group_id.id

        mo_vals.update({
            'procurement_group_id': group_id,
        })
        return mo_vals

    """
        timwang add at 2023/1/9
        修改stock/stock_rule.py中的同名方法

        free_qty是产品的当前真实可用库存
        virtual_available 是考虑了未完成的入出库后计算的可用库存
        由于我们在实际使用中，在作业类型中的出库类作业（交货单，制造单，内部调拨，外包）设置了预约方式为”人工“。
        因此，不会自动锁定库存，这会造成产品的free_qty不变。
        原_run_pull方法中，读取可用库存使用的是product.free_qty字段。如果相同原材料需要多次被领用，则无法产生相关的采购。
        这样就不对了。因此此将之改为product.virtual_available。
        
        由于mrp/stock_rule.py对该方法进行了继承，因此这里对两个文件中的代码进行了覆盖。

        _run_pull_1 是 mrp/stock_rule.py 中的 _run_pull

        _run_pull_2 是 mrp/stock_rule.py 中的 _run_pull, 其中的product.free_qty改为product.virtual_available

    """
    @api.model
    def _run_pull(self, procurements):
        self._run_pull_1(procurements)
        return self._run_pull_2(procurements)

    @api.model
    def _run_pull_1(self, procurements):
        # Override to correctly assign the move generated from the pull
        # in its production order (pbm_sam only)
        for procurement, rule in procurements:
            warehouse_id = rule.warehouse_id
            if not warehouse_id:
                warehouse_id = rule.location_id.warehouse_id
            if rule.picking_type_id == warehouse_id.sam_type_id:
                if float_compare(procurement.product_qty, 0, precision_rounding=procurement.product_uom.rounding) < 0:
                    procurement.values['group_id'] = procurement.values['group_id'].stock_move_ids.filtered(
                        lambda m: m.state not in ['done', 'cancel']).move_orig_ids.group_id[:1]
                    continue
                manu_type_id = warehouse_id.manu_type_id
                if manu_type_id:
                    name = manu_type_id.sequence_id.next_by_id()
                else:
                    name = self.env['ir.sequence'].next_by_code('mrp.production') or _('New')
                # Create now the procurement group that will be assigned to the new MO
                # This ensure that the outgoing move PostProduction -> Stock is linked to its MO
                # rather than the original record (MO or SO)
                group = procurement.values.get('group_id')
                if group:
                    procurement.values['group_id'] = group.copy({'name': name})
                else:
                    procurement.values['group_id'] = self.env["procurement.group"].create({'name': name})

        """ 此处注释掉。避免调用父类的代码。"""
        # return super()._run_pull(procurements)

    @api.model
    def _run_pull_2(self, procurements):
        moves_values_by_company = defaultdict(list)
        mtso_products_by_locations = defaultdict(list)

        # To handle the `mts_else_mto` procure method, we do a preliminary loop to
        # isolate the products we would need to read the forecasted quantity,
        # in order to to batch the read. We also make a sanitary check on the
        # `location_src_id` field.
        for procurement, rule in procurements:
            if not rule.location_src_id:
                msg = _('No source location defined on stock rule: %s!') % (rule.name, )
                raise ProcurementException([(procurement, msg)])

            if rule.procure_method == 'mts_else_mto':
                mtso_products_by_locations[rule.location_src_id].append(procurement.product_id.id)

        # Get the forecasted quantity for the `mts_else_mto` procurement.
        forecasted_qties_by_loc = {}
        for location, product_ids in mtso_products_by_locations.items():
            products = self.env['product.product'].browse(product_ids).with_context(location=location.id)
            """旧代码，注释掉"""
            # forecasted_qties_by_loc[location] = {product.id: product.free_qty for product in products}
            """新代码"""
            forecasted_qties_by_loc[location] = {product.id: product.virtual_available for product in products}

        # Prepare the move values, adapt the `procure_method` if needed.
        procurements = sorted(procurements, key=lambda proc: float_compare(proc[0].product_qty, 0.0, precision_rounding=proc[0].product_uom.rounding) > 0)
        for procurement, rule in procurements:
            procure_method = rule.procure_method
            if rule.procure_method == 'mts_else_mto':
                qty_needed = procurement.product_uom._compute_quantity(procurement.product_qty, procurement.product_id.uom_id)
                if float_compare(qty_needed, 0, precision_rounding=procurement.product_id.uom_id.rounding) <= 0:
                    procure_method = 'make_to_order'
                    for move in procurement.values.get('group_id', self.env['procurement.group']).stock_move_ids:
                        if move.rule_id == rule and float_compare(move.product_uom_qty, 0, precision_rounding=move.product_uom.rounding) > 0:
                            procure_method = move.procure_method
                            break
                    forecasted_qties_by_loc[rule.location_src_id][procurement.product_id.id] -= qty_needed
                elif float_compare(qty_needed, forecasted_qties_by_loc[rule.location_src_id][procurement.product_id.id],
                                   precision_rounding=procurement.product_id.uom_id.rounding) > 0:
                    procure_method = 'make_to_order'
                else:
                    forecasted_qties_by_loc[rule.location_src_id][procurement.product_id.id] -= qty_needed
                    procure_method = 'make_to_stock'

            move_values = rule._get_stock_move_values(*procurement)
            move_values['procure_method'] = procure_method
            moves_values_by_company[procurement.company_id.id].append(move_values)

        for company_id, moves_values in moves_values_by_company.items():
            # create the move as SUPERUSER because the current user may not have the rights to do it (mto product launched by a sale for example)
            moves = self.env['stock.move'].with_user(SUPERUSER_ID).sudo().with_company(company_id).create(moves_values)
            # Since action_confirm launch following procurement_group we should activate it.
            moves._action_confirm()
        return True

    def get_existing_productions(self, procurement):
        domain = [
            ("company_id", "=", procurement.company_id.id),
            ("product_id", "=", procurement.product_id.id),
            ("date_planned_finished", "=", procurement.values["date_planned"]),
            ("state", "=", "confirmed"),
        ]
        gpo = self.group_propagation_option
        group_id = (gpo == 'fixed' and self.group_id.id) or \
                   (gpo == 'propagate' and procurement.values.get("group_id")) or False
        if group_id:
            domain.append(("procurement_group_id", "=", group_id))

        existing_productions = self.env["mrp.production"].search(domain)
        return existing_productions

    @api.model
    def _run_manufacture(self, procurements):
        super(StockRule, self)._run_manufacture(procurements)

        # 进行制造订单合并的操作
        for procurement, rule in procurements:
            existing_productions = self.get_existing_productions(procurement)
            if len(existing_productions) > 1:
                existing_productions._merge_productions()
