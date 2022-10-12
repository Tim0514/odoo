# Copyright 2018-2020 ForgeFlow, S.L.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)

from odoo import api, fields, models


class StockRule(models.Model):
    _inherit = "stock.rule"

    @api.model
    def _prepare_purchase_plan(self, origin, procurement):
        gpo = self.group_propagation_option
        group_id = (
                (gpo == "fixed" and self.group_id.id)
                or (gpo == "propagate" and procurement.values["group_id"].id)
                or False
        )
        procurement_uom_po_qty = procurement.product_uom._compute_quantity(
            procurement.product_qty, procurement.product_id.uom_po_id
        )

        return {
            "origin": origin,
            "company_id": procurement.company_id.id,
            "group_id": group_id or False,
            "picking_type_id": self.picking_type_id.id,
            "product_id": procurement.product_id.id,
            "date_required": "date_planned" in procurement.values
                             and procurement.values["date_planned"]
                             or fields.Datetime.now(),
            "product_uom_id": procurement.product_id.uom_po_id.id,
            "product_qty": procurement_uom_po_qty,
            "move_dest_ids": [
                (4, x.id) for x in procurement.values.get("move_dest_ids", [])
            ],
            "orderpoint_id": procurement.values.get("orderpoint_id", False)
                             and procurement.values.get("orderpoint_id").id,

        }

    @api.model
    def _make_purchase_plan_get_domain(self, procurement):
        """
        This method is to be implemented by other modules that can
        provide a criteria to select the appropriate purchase plan to be
        extended.
        :return: False
        """
        domain = (
            ("state", "=", "draft"),
            ("company_id", "=", procurement.company_id.id),
            ("product_id", "=", procurement.product_id.id),
            ('picking_type_id', '=', self.picking_type_id.id),
            ("date_required", "=", "date_planned" in procurement.values
             and procurement.values["date_planned"]),
        )

        gpo = self.group_propagation_option
        group_id = (
                (gpo == "fixed" and self.group_id.id)
                or (gpo == "propagate" and procurement.values["group_id"].id)
                or False
        )
        if group_id:
            domain += (("group_id", "=", group_id),)


        return domain

    def is_create_purchase_plan_allowed(self, procurement):
        """
        Tell if current procurement order should
        create a purchase request or not.
        :return: boolean
        """
        # use_purchase_plan = self.env['ir.config_parameter'].sudo().get_param('purchase.use_purchase_plan')
        use_purchase_plan = procurement[1].company_id.use_purchase_plan

        return (
                procurement[1].action == "buy"
                and use_purchase_plan
        )

    def _run_buy(self, procurements):
        indexes_to_pop = []
        for i, procurement in enumerate(procurements):
            if self.is_create_purchase_plan_allowed(procurement):
                self.create_purchase_plan(procurement)
                indexes_to_pop.append(i)
        if indexes_to_pop:
            indexes_to_pop.reverse()
            for index in indexes_to_pop:
                procurements.pop(index)
        if not procurements:
            return
        return super(StockRule, self)._run_buy(procurements)


    """
        timwang modified at 2019/8/21
        每次创建请购单明细时，先查找是否有产品ID,交货期一样的明细数据,如果有的话，就合并，没有就新增
    """
    def create_purchase_plan(self, procurement_group):
        """
        Create a purchase plan containing procurement order product.
        """
        procurement = procurement_group[0]
        rule = procurement_group[1]
        purchase_plan_model = self.env["purchase.plan"]

        cache = {}
        pl = self.env["purchase.plan"]
        domain = rule._make_purchase_plan_get_domain(procurement)
        if domain in cache:
            pl = cache[domain]
        elif domain:
            pl = self.env["purchase.plan"].search([dom for dom in domain])
            pl = pl[0] if pl else False
            cache[domain] = pl

        if not pl:
            # 如果没有可合并的采购计划，则新增一个。
            purchase_plan_data = rule._prepare_purchase_plan(
                procurement.origin, procurement
            )
            pl = purchase_plan_model.create(purchase_plan_data)
            cache[domain] = pl
        else:
            # 如果有可合并的采购计划，则合并。

            # 将需求数量的单位转换成采购单位
            procurement_uom_po_qty = procurement.product_uom._compute_quantity(
                procurement.product_qty, procurement.product_id.uom_po_id
            )

            origin = pl.origin

            if procurement.origin:
                if not pl.origin or procurement.origin not in pl.origin.split(", "):
                    if pl.origin:
                        origin = pl.origin + ", " + procurement.origin
                    else:
                        origin = procurement.origin

            move_dest_ids = procurement.values.get("move_dest_ids", [])

            # timwang commented
            # 这里添加了补货领料单的move_dest_ids的时候，系统速度变得非常慢。
            pl.write({"product_qty": pl.product_qty + procurement_uom_po_qty,
                      "origin": origin,
                      "move_dest_ids": [(4, m.id) for m in move_dest_ids]
                      })
