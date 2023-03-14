# Copyright 2018-2019 ForgeFlow, S.L.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PurchasePlanMakePurchaseOrder(models.TransientModel):
    _name = "purchase.plan.make.purchase.order"
    _description = "Purchase Plan Make Purchase Order"

    merge_to_po = fields.Boolean(
        string="Merge to PO",
        default=True,
        help="If checked, odoo will merge data to PO lines with same product_id and date_planned.",
    )

    supplier_id = fields.Many2one(
        comodel_name="res.partner",
        string="Supplier",
        domain=[("is_company", "=", True)],
        context={"res_partner_search_mode": "supplier", "default_is_company": True},
        help="If fill this field, odoo will create RFQ for all plans using this supplier.",
    )

    purchase_order_id = fields.Many2one(
        comodel_name="purchase.order",
        string="Purchase Order",
        domain=[("state", "=", "draft")],
        help="If fill this field, odoo will add data to this PO and merge data to PO lines with same product_id and date_planned.",
    )

    item_ids = fields.One2many(
        comodel_name="purchase.plan.make.purchase.order.item",
        inverse_name="wiz_id",
        string="Items",
    )

    @api.model
    def _prepare_item(self, purchase_plan):
        return {
            "purchase_plan_id": purchase_plan.id,
            # "product_id": purchase_plan.product_id.id,
            "name": purchase_plan.product_id.name,
            "product_qty": purchase_plan.product_qty - purchase_plan.purchased_qty,
            # "product_uom_id": purchase_plan.product_uom_id.id,
            "supplier_id": purchase_plan.supplier_id.id,
            "propagate_cancel": purchase_plan.propagate_cancel,
        }

    @api.model
    def _check_valid_purchase_plan(self, purchase_plan_ids):
        picking_type = False
        company_id = False

        for plan in self.env["purchase.plan"].browse(purchase_plan_ids):
            if plan.state == "done":
                raise UserError(_("The purchase has already been completed."))

            plan_company_id = plan.company_id and plan.company_id.id or False
            if company_id is not False and plan_company_id != company_id:
                raise UserError(_("You have to select lines from the same company."))
            else:
                company_id = plan_company_id

            line_picking_type = plan.picking_type_id or False
            if not line_picking_type:
                raise UserError(_("You have to enter a Picking Type."))
            if picking_type is not False and line_picking_type != picking_type:
                raise UserError(
                    _("You have to select lines from the same Picking Type.")
                )
            else:
                picking_type = line_picking_type

    @api.model
    def check_group(self, request_plans):
        if len(list(set(request_plans.mapped("group_id")))) > 1:
            raise UserError(
                _(
                    "You cannot create a single purchase order from "
                    "purchase plans that have different procurement group."
                )
            )

    @api.model
    def get_items(self, purchase_plan_ids):
        self._check_valid_purchase_plan(purchase_plan_ids)
        purchase_plan_obj = self.env["purchase.plan"]
        items = []
        purchase_plans = purchase_plan_obj.browse(purchase_plan_ids)
        # self.check_group(request_lines)
        for plan in purchase_plans:
            items.append([0, 0, self._prepare_item(plan)])
        return items

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        active_model = self.env.context.get("active_model", False)
        purchase_plan_ids = []
        purchase_plan_ids += self.env.context.get("active_ids", [])

        if not purchase_plan_ids:
            return res

        res["item_ids"] = self.get_items(purchase_plan_ids)

        purchase_plans = self.env["purchase.plan"].browse(purchase_plan_ids)
        supplier_ids = purchase_plans.mapped("supplier_id").ids
        if len(supplier_ids) == 1:
            res["supplier_id"] = supplier_ids[0]
        return res

    @api.model
    def _prepare_purchase_order(self, picking_type, group_id, company, origin, partner=False):
        supplier = self.supplier_id or partner
        data = {
            "origin": origin,
            "partner_id": supplier.id,
            "fiscal_position_id": supplier.property_account_position_id
                                  and supplier.property_account_position_id.id
                                  or False,
            "picking_type_id": picking_type.id,
            "company_id": company.id,
            "group_id": group_id.id,
        }
        return data

    @api.model
    def _get_purchase_line_onchange_fields(self):
        return ["product_uom", "price_unit", "name", "taxes_id"]

    @api.model
    def _execute_purchase_line_onchange(self, vals):
        cls = self.env["purchase.order.line"]
        onchanges_dict = {
            "onchange_product_id": self._get_purchase_line_onchange_fields()
        }
        for onchange_method, changed_fields in onchanges_dict.items():
            if any(f not in vals for f in changed_fields):
                obj = cls.new(vals)
                getattr(obj, onchange_method)()
                for field in changed_fields:
                    vals[field] = obj._fields[field].convert_to_write(obj[field], obj)

    @api.model
    def _prepare_purchase_order_line(self, po, item):
        if not item.product_id:
            raise UserError(_("Please select a product for all lines"))
        product = item.product_id

        qty = item.purchase_plan_id.calc_new_po_qty(item.product_id, item.product_uom_id,
                                                    item.product_qty, item.supplier_id, po_line=None)

        # # Keep the standard product UOM for purchase order so we should
        # # convert the product quantity to this UOM
        # qty = item.product_uom_id._compute_quantity(
        #     item.product_qty, product.uom_po_id or product.uom_id
        # )
        #
        # # Suggest the supplier min qty as it's done in Odoo core
        # min_qty = item.purchase_plan_id._get_supplier_min_qty(product, po.partner_id)
        #
        # qty = max(qty, min_qty)

        date_required = item.purchase_plan_id.date_required

        if item.keep_description:
            name = item.name
        else:
            name = self._get_purchase_line_name(product)
        vals = {
            "name": name,
            "order_id": po.id,
            "product_id": product.id,
            "product_uom": product.uom_po_id.id or product.uom_id.id,
            "price_unit": 0.0,
            "product_qty": qty,
            # "account_analytic_id": item.purchase_plan_id.analytic_account_id.id,
            "purchase_plan_ids": [(4, item.purchase_plan_id.id)],
            "date_planned": datetime(
                date_required.year, date_required.month, date_required.day
            ),
            "move_dest_ids": [(4, x.id) for x in item.purchase_plan_id.move_dest_ids],
            "propagate_cancel": item.purchase_plan_id.propagate_cancel,

        }

        self._execute_purchase_line_onchange(vals)
        return vals

    @api.model
    def _get_purchase_line_name(self, product):
        product_lang = product.with_context(
            {"lang": self.supplier_id.lang, "partner_id": self.supplier_id.id}
        )
        name = product_lang.display_name
        if product_lang.description_purchase:
            name += "\n" + product_lang.description_purchase
        return name

    @api.model
    def _get_order_search_domain(self, item, purchase_plan):
        domain = [
            ("company_id", "=", purchase_plan.company_id.id),
            ("picking_type_id", "=", purchase_plan.picking_type_id.id),
            ("state", "=", "draft"),
            ("partner_id", "=", item.supplier_id.id),
        ]

        if purchase_plan.group_id:
            domain.append(("group_id", "=", purchase_plan.group_id.id), )

        return domain

    @api.model
    def _get_order_line_search_domain(self, order, item):
        vals = self._prepare_purchase_order_line(order, item)
        date_required = item.purchase_plan_id.date_required
        order_line_data = [
            ("order_id", "=", order.id),
            ("product_id", "=", item.product_id.id or False),
            ("product_uom", "=", vals["product_uom"]),
            ("date_planned", "=", datetime(date_required.year, date_required.month, date_required.day)),
        ]
        if item.keep_description:
            name = item.name
            order_line_data.append(("name", "=", name))

        return order_line_data

    # 生成采购询价单
    def make_purchase_order(self):
        res = []
        po_obj = self.env["purchase.order"]
        po_line_obj = self.env["purchase.order.line"]
        purchase_plan_obj = self.env["purchase.plan"]

        purchase_order_dict = {}

        if self.supplier_id:
            # 如果指定了供应商，则把所有计划的都改成指定的供应商
            for item in self.item_ids:
                item.supplier_id = self.supplier_id

        if self.purchase_order_id:
            # 如果指定了采购订单，则要检查采购订单的补货组是否和所有的采购计划补货组相同。
            for item in self.item_ids:
                purchase_plan = item.purchase_plan_id
                if self.purchase_order_id.group_id != purchase_plan.group_id:
                    raise UserError(
                        _("Group Ids are different between selected PO and purchase plans.")
                    )

        has_ignored_plan = False

        for item in self.item_ids:
            purchase_plan = item.purchase_plan_id
            purchase_order_domain = self._get_order_search_domain(item, purchase_plan)

            if item.product_qty <= 0.0:
                raise UserError(_("Enter a positive quantity."))

            available_qty = item._get_available_qty()
            if item.product_qty < available_qty:
                # 已有订单已经可以满足需求，不需要再采购
                item.purchase_plan_id.no_need_purchase = True
                has_ignored_plan = True
                continue

            if self.purchase_order_id:
                # 如果选择了指定的采购订单合并
                order_to_use = self.purchase_order_id
            elif purchase_order_dict.get(str(purchase_order_domain), False):
                # 缓存中有该订单，则直接使用。
                order_to_use = purchase_order_dict.get(str(purchase_order_domain))
            else:
                # 如果采购订单的缓存中没有该订单，则需要查找现有订单或者新建采购订单。
                purchase_order = po_obj.search(purchase_order_domain)
                if purchase_order:
                    purchase_order = purchase_order[0]
                else:
                    po_data = self._prepare_purchase_order(
                        purchase_plan.picking_type_id,
                        purchase_plan.group_id,
                        purchase_plan.company_id,
                        purchase_plan.origin,
                        partner=purchase_plan.supplier_id,
                    )
                    purchase_order = po_obj.create(po_data)
                purchase_order_dict[str(purchase_order_domain)] = purchase_order
                order_to_use = purchase_order

            # Look for any other PO line in the selected PO with same
            # product and UoM to sum quantities instead of creating a new
            # po line
            domain = self._get_order_line_search_domain(order_to_use, item)
            available_po_lines = po_line_obj.search(domain)

            if available_po_lines:
                po_line = available_po_lines[0]
                po_line.purchase_plan_ids = [(4, purchase_plan.id)]
                po_line.move_dest_ids |= purchase_plan.move_dest_ids
                po_line.product_qty = purchase_plan.calc_new_po_qty(item.product_id, item.product_uom_id,
                                                                    item.product_qty, item.supplier_id, po_line=po_line)
                po_line._onchange_quantity()
                # The onchange quantity is altering the scheduled date of the PO
                # lines. We do not want that:
                date_required = purchase_plan.date_required
                po_line.date_planned = datetime(
                    date_required.year, date_required.month, date_required.day
                )
            else:
                po_line_data = self._prepare_purchase_order_line(order_to_use, item)
                if item.keep_description:
                    po_line_data["name"] = item.name
                po_line = po_line_obj.create(po_line_data)

            res.append(order_to_use.id)

        if has_ignored_plan:
            next_action = {
                "domain": [("id", "in", res)],
                "name": _("RFQ"),
                "view_mode": "tree,form",
                "res_model": "purchase.order",
                "views": [(False, "list"), (False, "form")],
                # "views": [(False, "tree"), (False, "form")],   # odoo 有个bug, 在 views中， 列表视图得用list, 不能用tree
                "context": False,
                "type": "ir.actions.act_window",
                "target": "current",
            }
            notification = {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Warning'),
                    'message': _('POs have been created, but some plans are ignored.'),
                    'sticky': True,
                    'type': 'warning',
                    'next': next_action,
                }
            }
        else:
            next_action = {
                "domain": [("id", "in", res)],
                "name": _("RFQ"),
                "view_mode": "tree,form",
                "res_model": "purchase.order",
                "views": [(False, "list"), (False, "form")],
                # "views": [(False, "tree"), (False, "form")],   # odoo 有个bug, 在 views中， 列表视图得用list, 不能用tree
                "context": False,
                "type": "ir.actions.act_window",
            }
            notification = {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('POs have been created.'),
                    'sticky': True,
                    'type': 'success',
                    'next': next_action,
                }
            }
        return notification

class PurchasePlanMakePurchaseOrderItem(models.TransientModel):
    _name = "purchase.plan.make.purchase.order.item"
    _description = "Purchase Plan Make Purchase Order Item"

    wiz_id = fields.Many2one(
        comodel_name="purchase.plan.make.purchase.order",
        string="Wizard",
        required=True,
        ondelete="cascade",
    )

    purchase_plan_id = fields.Many2one(
        string="Purchase Plan",
        comodel_name="purchase.plan",
    )

    purchase_plan_name = fields.Char(
        string="Reference",
        related="purchase_plan_id.name",
    )

    product_id = fields.Many2one(
        string="Product",
        # comodel_name="product.product",
        related="purchase_plan_id.product_id",
    )

    name = fields.Char(string="Description", required=True)

    supplier_id = fields.Many2one(
        string="Supplier",
        comodel_name="res.partner",
        required=True,
        domain=[("is_company", "=", True)],
        context={"res_partner_search_mode": "supplier", "default_is_company": True},
    )

    product_qty = fields.Float(
        string="Quantity to purchase", digits="Product Unit of Measure", required=True,
    )

    product_uom_id = fields.Many2one(
        string="UoM",
        # comodel_name="uom.uom",
        related="purchase_plan_id.product_uom_id",
    )

    keep_description = fields.Boolean(
        string="Copy descriptions to new PO",
        default=False,
        help="Set true if you want to keep the "
             "descriptions provided in the "
             "wizard in the new PO.",
        store=True,
    )

    propagate_cancel = fields.Boolean('Propagate cancellation', default=True)

    def _get_available_qty(self):
        """
        获取需要采购的产品的可用数量之和(虚拟可用库存+尚未确认的采购订单数量+尚未转采购的采购计划数量）
        :return: 虚拟可用库存+尚未确认的采购订单数量
        """
        self.ensure_one()
        product_id = self.product_id
        purchase_plan = self.purchase_plan_id
        product_id = product_id.with_context(location=purchase_plan.picking_type_id.default_location_dest_id.id)
        available_qty = product_id.virtual_available

        # 读取还没有生成入库单的采购订单，用于统计可用数量
        domain = [
            ("company_id", "=", purchase_plan.company_id.id),
            ("partner_id", "=", self.supplier_id.id),
            ("product_id", "=", product_id.id),
            ("state", "not in", ["purchase", "done", "cancel"]),
        ]
        po_line = self.env["purchase.order.line"].search(domain)
        purchasing_qty = sum(po_line.mapped("product_uom_qty"))

        # 读取还没有生成采购单的采购计划，用于统计可用数量
        domain = [
            ("company_id", "=", purchase_plan.company_id.id),
            ("product_id", "=", product_id.id),
            ("state", "not in", ["done", "ignored"]),
        ]
        po_line = self.env["purchase.plan"].search(domain)
        to_purchase_qty = sum(po_line.mapped("product_qty")) - sum(po_line.mapped("purchased_qty"))

        return available_qty + to_purchase_qty + purchasing_qty



    # @api.onchange("product_id")
    # def onchange_product_id(self):
    #     if self.product_id:
    #         if not self.keep_description:
    #             name = self.product_id.name
    #         code = self.product_id.code
    #         sup_info_id = self.env["product.supplierinfo"].search(
    #             [
    #                 "|",
    #                 ("product_id", "=", self.product_id.id),
    #                 ("product_tmpl_id", "=", self.product_id.product_tmpl_id.id),
    #                 ("name", "=", self.wiz_id.supplier_id.id),
    #             ]
    #         )
    #         if sup_info_id:
    #             p_code = sup_info_id[0].product_code
    #             p_name = sup_info_id[0].product_name
    #             name = "[{}] {}".format(
    #                 p_code if p_code else code, p_name if p_name else name
    #             )
    #         else:
    #             if code:
    #                 name = "[{}] {}".format(
    #                     code, self.name if self.keep_description else name
    #                 )
    #         if self.product_id.description_purchase and not self.keep_description:
    #             name += "\n" + self.product_id.description_purchase
    #         self.product_uom_id = self.product_id.uom_id.id
    #         if name:
    #             self.name = name
