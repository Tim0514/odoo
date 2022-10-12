# Copyright 2018-2019 ForgeFlow, S.L.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)

from odoo import _, api, exceptions, fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def _purchase_plan_confirm_message_content(self, purchase_plan, purchase_plan_dict=None):
        self.ensure_one()
        if not purchase_plan_dict:
            purchase_plan_dict = {}
        title = _("Order confirmation %s for your Plan %s") % (
            self.name,
            purchase_plan.name,
        )
        message = "<h3>%s</h3><ul>" % title
        message += _(
            "The following items from Purchase Plan %s "
            "have now been confirmed in Purchase Order %s:"
        ) % (purchase_plan.name, self.name)

        for line in purchase_plan_dict.values():
            for line_value in line.values():
                message += _(
                    "<li><b>%s</b>: Ordered quantity %s %s, Planned date %s</li>"
                ) % (
                    line_value["name"],
                    line_value["product_qty"],
                    line_value["product_uom"],
                    line_value["date_planned"],
                )
        message += "</ul>"
        return message

    def _purchase_plan_confirm_message(self):
        purchase_plan_obj = self.env["purchase.plan"]
        for po in self:
            purchase_plan_dict = {}
            for line in po.order_line:
                for purchase_plan in line.sudo().purchase_plan_ids:
                    purchase_plan_id = purchase_plan.id
                    if purchase_plan_id not in purchase_plan_dict:
                        purchase_plan_dict[purchase_plan_id] = {}
                    date_planned = "%s" % line.date_planned
                    data = {
                        "name": purchase_plan.name,
                        "product_qty": line.product_qty,
                        "product_uom": line.product_uom.name,
                        "date_planned": date_planned,
                    }
                    purchase_plan_dict[purchase_plan_id][line.id] = data
            for purchase_plan_id in purchase_plan_dict:
                purchase_plan = purchase_plan_obj.sudo().browse(purchase_plan_id)
                message = po._purchase_plan_confirm_message_content(
                    purchase_plan, purchase_plan_dict
                )
                purchase_plan.message_post(
                    body=message, subtype_id=self.env.ref("mail.mt_comment").id
                )
        return True

    def _purchase_plan_check(self):
        for po in self:
            for line in po.order_line:
                for purchase_plan in line.purchase_plan_ids:
                    if purchase_plan.sudo().purchase_state == "done":
                        raise exceptions.UserError(
                            _("Purchase Plan %s has already been completed")
                            % purchase_plan.name
                        )
        return True

    def button_confirm(self):
        self._purchase_plan_check()
        res = super(PurchaseOrder, self).button_confirm()
        self._purchase_plan_confirm_message()
        return res

class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    purchase_plan_ids = fields.Many2many(
        comodel_name="purchase.plan",
        relation="purchase_plan_purchase_order_line_rel",
        column1="purchase_order_line_id",
        column2="purchase_plan_id",
        string="Purchase Plan",
        readonly=True,
        copy=False,
    )

    def action_open_purchase_plan_tree_view(self):
        """
        :return dict: dictionary value for created view
        """
        purchase_plan_ids = []
        for line in self:
            purchase_plan_ids += line.purchase_plan_ids.ids

        domain = [("id", "in", purchase_plan_ids)]

        return {
            "name": _("Purchase Plan"),
            "type": "ir.actions.act_window",
            "res_model": "purchase.plan",
            "view_mode": "tree",
            "domain": domain,
        }
