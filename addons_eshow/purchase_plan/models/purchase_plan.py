# Copyright 2022 Tim Wang
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta
import math

_STATES = [
    ("draft", "Draft"),
    ("in_process", "In Process"),
    ("done", "Done"),
    ("cancelled", "Cancelled"),
]

class PurchasePlan(models.Model):
    _name = "purchase.plan"
    _description = "Purchase Plan"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "supplier_name, date_start"

    @api.model
    def _get_company(self):
        return self.env["res.company"].browse(self.env.company.id)

    @api.model
    def _get_default_requested_by(self):
        return self.env["res.users"].browse(self.env.uid)

    @api.model
    def _get_default_picking_type(self):
        type_obj = self.env["stock.picking.type"]
        company_id = self.env.context.get("company_id") or self.env.company.id
        types = type_obj.search(
            [("code", "=", "incoming"), ("warehouse_id.company_id", "=", company_id)]
        )
        if not types:
            types = type_obj.search(
                [("code", "=", "incoming"), ("warehouse_id", "=", False)]
            )
        return types[:1]

    name = fields.Char(
        string="Reference",
        required=True,
        default=lambda self: _("New"),
    )

    supplier_id = fields.Many2one(
        string="Preferred supplier",
        comodel_name="res.partner",
        compute="_compute_supplier_id",
        store=True,
        readonly=False,
    )

    supplier_name = fields.Char(
        string="Supplier Name",
        related="supplier_id.name",
        store=True,
    )

    product_id = fields.Many2one(
        string="Product",
        comodel_name="product.product",
        required=True,
        store=True,
    )

    product_default_code = fields.Char(
        string="Product Default Code",
        related="product_id.default_code",
        readonly=True,
    )

    origin = fields.Char(string="Source Document")

    date_create = fields.Date(
        string="Creat Date",
        help="Date when the user initiated the plan.",
        default=fields.Date.context_today,
    )

    date_start = fields.Date(
        string="Start Date",
        help="Date when the user need to place the order.",
        required=False,
        compute="_compute_date_start",
        store=True,
    )

    date_required = fields.Date(
        string="Require Date",
        help="Date when the material need to be arrived.",
        required=True,
        store=True,
        default=fields.Date.context_today,
    )

    requested_by = fields.Many2one(
        comodel_name="res.users",
        string="Requested by",
        required=True,
        copy=False,
        default=_get_default_requested_by,
        index=True,
    )

    assigned_to = fields.Many2one(
        comodel_name="res.users",
        string="Approver",
        domain=lambda self: [
            (
                "groups_id",
                "in",
                self.env.ref("purchase.group_purchase_manager").id,
            )
        ],
        index=True,
    )

    description = fields.Text(string="Description")

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        default=_get_company,
    )

    product_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        string="UoM",
    )

    product_qty = fields.Float(
        string="Require Qty", digits="Product Unit of Measure"
    )

    state = fields.Selection(
        selection=_STATES,
        string="Status",
        index=True,
        required=True,
        copy=False,
        default="draft",
        compute="_compute_state",
        store=True,
    )

    is_editable = fields.Boolean(
        string="Is Editable", compute="_compute_is_editable", readonly=True
    )

    group_id = fields.Many2one(
        comodel_name="procurement.group",
        string="Procurement Group",
        copy=False,
        index=True,
    )

    orderpoint_id = fields.Many2one(
        comodel_name="stock.warehouse.orderpoint", string="Orderpoint"
    )

    picking_type_id = fields.Many2one(
        comodel_name="stock.picking.type",
        string="Deliver To",
        required=True,
        default=_get_default_picking_type,
    )

    move_dest_ids = fields.One2many(
        comodel_name="stock.move",
        inverse_name="created_purchase_plan_id",
        string="Downstream Moves",
    )

    purchased_qty = fields.Float(
        string="RFQ/PO Qty",
        digits="Product Unit of Measure",
        compute="_compute_purchased_qty",
    )

    purchase_lines = fields.Many2many(
        comodel_name="purchase.order.line",
        relation="purchase_plan_purchase_order_line_rel",
        column1="purchase_plan_id",
        column2="purchase_order_line_id",
        string="Purchase Order Lines",
        readonly=True,
        copy=False,
    )

    purchase_state = fields.Selection(
        compute="_compute_purchase_state",
        string="RFQ/PO Status",
        selection=lambda self: self.env["purchase.order"]._fields["state"].selection,
        store=True,
        copy=False,
    )

    propagate_cancel = fields.Boolean('Propagate cancellation', default=False)


    @api.model
    def _get_default_name(self):
        return self.env["ir.sequence"].next_by_code("purchase.plan")

    @api.depends("state")
    def _compute_is_editable(self):
        for rec in self:
            if rec.state in ("done", "cancelled"):
                rec.is_editable = False
            else:
                rec.is_editable = True

    def action_view_purchase_order(self):
        action = self.env.ref("purchase.purchase_rfq").sudo().read()[0]
        lines = self.mapped("purchase_lines.order_id")
        if len(lines) > 1:
            action["domain"] = [("id", "in", lines.ids)]
        elif lines:
            action["views"] = [
                (self.env.ref("purchase.purchase_order_form").id, "form")
            ]
            action["res_id"] = lines.id
        return action

    def copy(self, default=None):
        default = dict(default or {})
        self.ensure_one()
        default.update({"state": "draft", "name": self._get_default_name()})
        return super(PurchasePlan, self).copy(default)

    @api.model
    def _get_partner_id(self, plan):
        user_id = plan.assigned_to or self.env.user
        return user_id.partner_id.id

    @api.model
    def create(self, vals):
        if vals.get("name", _("New")) == _("New"):
            vals["name"] = self._get_default_name()
        plan = super(PurchasePlan, self).create(vals)
        if vals.get("assigned_to"):
            partner_id = self._get_partner_id(plan)
            plan.message_subscribe(partner_ids=[partner_id])
        return plan

    def write(self, vals):
        res = super(PurchasePlan, self).write(vals)
        for plan in self:
            if vals.get("assigned_to"):
                partner_id = self._get_partner_id(plan)
                plan.message_subscribe(partner_ids=[partner_id])
        return res

    def _can_be_deleted(self):
        self.ensure_one()
        return self.state in ("draft", "cancelled")

    def unlink(self):
        for plan in self:
            if not plan._can_be_deleted():
                raise UserError(
                    _("You cannot delete a purchase plan which is not draft or cancelled.")
                )
        return super(PurchasePlan, self).unlink()

    def button_cancel(self):
        self.write({"state": "cancelled"})

    def button_uncancel(self):
        self.write({"state": "draft"})

    @api.depends("product_id", "product_id.seller_ids")
    def _compute_supplier_id(self):
        for rec in self:
            rec.supplier_id = False
            if rec.product_id:
                if rec.product_id.seller_ids:
                    rec.supplier_id = rec.product_id.seller_ids[0].name

    @api.onchange("product_id")
    def onchange_product_id(self):
        if self.product_id:
            # name = self.product_id.name
            # if self.product_id.code:
            #     name = "[{}] {}".format(name, self.product_id.code)
            # if self.product_id.description_purchase:
            #     name += "\n" + self.product_id.description_purchase
            self.product_uom_id = self.product_id.uom_id.id
            self.product_qty = 1
            # self.name = name

    def _compute_purchased_qty(self):
        for rec in self:
            rec.purchased_qty = 0.0
            for line in rec.purchase_lines.filtered(lambda x: x.state != "cancel"):
                if rec.product_uom_id and line.product_uom != rec.product_uom_id:
                    rec.purchased_qty += line.product_uom._compute_quantity(
                        line.product_qty, rec.product_uom_id
                    )
                else:
                    rec.purchased_qty += line.product_qty

    @api.depends("date_required", "product_qty", "product_id", "product_id.seller_ids",)
    def _compute_date_start(self):
        for req in self:
            purchase_delay = 0
            product = req.product_id

            if product:
                seller = product.with_company(req.company_id)._select_seller(
                    partner_id=req.supplier_id,
                    quantity=req.product_qty,
                    date=req.date_start,
                    uom_id=req.product_uom_id)

                if seller:
                    purchase_delay = seller.delay

                req.date_start = req.date_required - relativedelta(days=purchase_delay or 0)

    @api.depends("purchase_lines.state", "purchase_lines.order_id.state")
    def _compute_purchase_state(self):
        for rec in self:
            temp_purchase_state = False
            if rec.purchase_lines:
                if any(po_line.state == "draft" for po_line in rec.purchase_lines):
                    temp_purchase_state = "draft"
                elif any(po_line.state == "sent" for po_line in rec.purchase_lines):
                    temp_purchase_state = "sent"
                elif any(po_line.state == "to approve" for po_line in rec.purchase_lines):
                    temp_purchase_state = "to approve"
                elif any(po_line.state == "purchase" for po_line in rec.purchase_lines):
                    temp_purchase_state = "purchase"
                elif any(po_line.state == "done" for po_line in rec.purchase_lines):
                    temp_purchase_state = "done"
                elif all(po_line.state == "cancel" for po_line in rec.purchase_lines):
                    temp_purchase_state = "cancel"
                else:
                    temp_purchase_state = "cancel"
            rec.purchase_state = temp_purchase_state

    @api.depends("product_qty", "purchase_state", "purchased_qty")
    def _compute_state(self):
        for rec in self:
            if rec.product_qty <= rec.purchased_qty:
                rec.state = "done"
            elif rec.purchased_qty == 0:
                rec.state = "draft"
            else:
                rec.state = "in_process"

    @api.model
    def _get_supplier_min_qty(self, product, partner_id=False):
        seller_min_qty = 0.0
        if partner_id:
            # 如果指定了供应商，则从该供应商的数据中取
            seller = product.seller_ids.filtered(lambda r: r.name == partner_id).sorted(
                key=lambda r: r.min_qty
            )
        else:
            # 如果没有指定供应商，则从该产品的所有供应商中取最小的。
            seller = product.seller_ids.sorted(key=lambda r: r.min_qty)
        if seller:
            seller_min_qty = seller[0].min_qty
        return seller_min_qty

    @api.model
    def calc_new_po_qty(self, product, purchase_plan_uom, new_qty, supplier, po_line=None):

        # 得到采购计量单位
        if po_line:
            purchase_uom = po_line.product_uom
        else:
            purchase_uom = product.uom_po_id

        # if new_qty > purchase_plan.product_qty - purchase_plan.purchased_qty:
        #     new_qty = purchase_plan.product_qty - purchase_plan.purchased_qty

        # # Recompute quantity by adding existing running procurements.
        # if new_po_line:
        #     rl_qty = po_line.product_uom_qty
        # else:
        #     rl_qty = purchase_plan.product_uom_id._compute_quantity(new_qty, purchase_uom)


        # 将需求数量转为采购数量
        purchase_qty = purchase_plan_uom._compute_quantity(new_qty, purchase_uom)

        # 如果有采购订单，则计算新的采购数量
        if po_line:
            purchase_qty += po_line.product_qty

        # 得到供应商最小采购数量
        supplierinfo_min_qty = self._get_supplier_min_qty(product, supplier)
        purchase_qty = max(purchase_qty, supplierinfo_min_qty)

        # 根据最小包装数，凑整箱。
        if product.minimum_package_qty != 1 and product.minimum_package_qty != 0.0:
            purchase_qty = math.ceil(purchase_qty / product.minimum_package_qty) * product.minimum_package_qty

        return purchase_qty

