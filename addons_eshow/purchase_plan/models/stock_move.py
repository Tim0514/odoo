# Copyright 2018-2019 ForgeFlow, S.L.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0)

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StockMove(models.Model):
    _inherit = "stock.move"

    created_purchase_plan_id = fields.Many2one(
        comodel_name="purchase.plan",
        string="Created Purchase Plan",
        ondelete="set null",
        readonly=True,
        copy=False,
        index=True,
    )

    @api.model
    def _prepare_merge_moves_distinct_fields(self):
        distinct_fields = super(StockMove, self)._prepare_merge_moves_distinct_fields()
        distinct_fields += ["created_purchase_plan_id"]
        return distinct_fields

    @api.model
    def _prepare_merge_move_sort_method(self, move):
        move.ensure_one()
        keys_sorted = super(StockMove, self)._prepare_merge_move_sort_method(move)
        keys_sorted += [
            move.created_purchase_plan_id.id,
        ]
        return keys_sorted

    def _action_cancel(self):
        for move in self:
            if move.created_purchase_plan_id:
                try:
                    activity_type_id = self.env.ref("mail.mail_activity_data_todo").id
                except ValueError:
                    activity_type_id = False
                pr_line = move.created_purchase_plan_id
                self.env["mail.activity"].sudo().create(
                    {
                        "activity_type_id": activity_type_id,
                        "note": _(
                            "A sale/manufacturing order that generated this "
                            "purchase plan has been cancelled/deleted. "
                            "Check if an action is needed."
                        ),
                        "user_id": pr_line.product_id.responsible_id.id,
                        "res_id": pr_line.id,
                        "res_model_id": self.env.ref(
                            "purchase_plan.model_purchase_plan"
                        ).id,
                    }
                )
        return super(StockMove, self)._action_cancel()
