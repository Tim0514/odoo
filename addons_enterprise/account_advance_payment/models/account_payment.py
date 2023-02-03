# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    advance_payment = fields.Boolean('预收/预付')
    advance_move_id = fields.Many2one(comodel_name='account.move',
        string='预收/预付凭证',  readonly=True, ondelete='cascade',
        check_company=True)

    @api.onchange('advance_payment')
    def _advance_change(self):
        if self.advance_payment:
            account_id = False
            if self.partner_type=='supplier':
                account_id = self.partner_id.property_account_payable_advance_id
            if self.partner_type=='customer':
                account_id = self.partner_id.property_account_receivable_advance_id
            self.destination_account_id = account_id

    def action_post(self):
        super().action_post()
        self.filtered(lambda pay: pay.advance_payment)._create_advance_move()

    def action_draft(self):
        super().action_draft()
        self.advance_move_id.button_draft()

    def action_cancel(self):
        super().action_cancel()
        self.advance_move_id.button_cancel()

    def _create_advance_move(self):
        for pay in self:
            if not pay.advance_payment:
                continue
            if not pay.advance_move_id:
                vals = {
                    'journal_id': pay.move_id.journal_id.id,
                    'date': pay.move_id.date,
                    'ref': pay.move_id.ref,
                    'partner_id': pay.partner_id.id,

                }
                move = self.env['account.move'].create(vals)
                pay.advance_move_id = move

            line = pay.move_id.line_ids.filtered(lambda line: line.account_id == pay.destination_account_id)
            account_id = False
            if pay.partner_type=='supplier':
                account_id = pay.partner_id.property_account_payable_id
            if pay.partner_type=='customer':
                account_id = pay.partner_id.property_account_receivable_id
             
            line_vals_list = [
                # Advance payment
                {
                    'name': line.name,
                    'date_maturity': line.date,
                    'amount_currency': -line.amount_currency,
                    'currency_id': line.currency_id.id,
                    'debit': line.credit,
                    'credit': line.debit,
                    'partner_id': line.partner_id.id,
                    'account_id': line.account_id.id,
                },
                # Receivable / Payable.
                {
                    'name': line.name,
                    'date_maturity': line.date_maturity,
                    'amount_currency': line.amount_currency,
                    'currency_id': line.currency_id.id,
                    'debit': line.debit,
                    'credit': line.credit,
                    'partner_id': pay.partner_id.id,
                    'account_id': account_id.id,
                },
            ]
            
            pay.advance_move_id.line_ids = False
            pay.advance_move_id.write({'line_ids': [(0, 0, line) for line in line_vals_list]})
            pay.advance_move_id._post(soft=False)
            line2 = pay.advance_move_id.line_ids.filtered(lambda line: line.account_id == pay.destination_account_id)
            lines = line + line2
            lines.reconcile()
