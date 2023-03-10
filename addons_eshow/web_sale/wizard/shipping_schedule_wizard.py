# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models, tools

import logging
import threading
from odoo import api, fields, models, _, SUPERUSER_ID, registry

_logger = logging.getLogger(__name__)


class ShippingScheduleWizard(models.TransientModel):
    _name = 'web.sale.shipping.schedule.wizard'
    _description = 'Regenerate Shipping Schedule Manually'

    def _regenerate_shipping_schedule(self, only_new_products=False):
        # As this function is in a new thread, I need to open a new cursor, because the old one may be closed
        new_cr = self.pool.cursor()
        self = self.with_env(self.env(cr=new_cr))
        scheduler_cron = self.sudo().env.ref('web_sale.ir_cron_regenerate_shipping_schedule_action')
        # Avoid to run the scheduler multiple times in the same time
        try:
            with tools.mute_logger('odoo.sql_db'):
                self._cr.execute("SELECT id FROM ir_cron WHERE id = %s FOR UPDATE NOWAIT", (scheduler_cron.id,))
        except Exception:
            _logger.info('Attempt to Regenerate Shipping Schedule aborted, as already running')
            self._cr.rollback()
            self._cr.close()
            return {}
        new_cr.close()

        # company = self.env["res.company"].browse([1])
        #
        # self.env['web.sale.shipping.schedule'].with_context(allowed_company_ids=company.ids).run_scheduler(
        #     use_new_cursor=self._cr.dbname,
        #     company_id=company.id)

        self.env['web.sale.shipping.schedule'].run_scheduler(use_new_cursor=True, only_new_products=only_new_products)

        return {}

    def refresh_sale_data(self):
        self.env['web.sale.shipping.schedule']._refresh_sale_data()

        next_action = {
           'type': 'ir.actions.act_window_close'
        }

        notification = {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Notification'),
                'message': _('Sale data have been refresh'),
                'sticky': True,
                'type': 'success',
                'next': next_action,
            }
        }
        return notification

    def generate_shipping_schedule_all(self):
        self._regenerate_shipping_schedule(only_new_products=False)

        next_action = {
           'type': 'ir.actions.act_window_close'
        }

        notification = {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Notification'),
                'message': _('Shipping Schedule have been created'),
                'sticky': True,
                'type': 'success',
                'next': next_action,
            }
        }
        return notification


    def generate_shipping_schedule_new_products(self):
        self._regenerate_shipping_schedule(only_new_products=True)

        # return {'type': 'ir.actions.client', 'tag': 'reload'}

        next_action = {
           'type': 'ir.actions.act_window_close'
        }

        notification = {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Notification'),
                'message': _('Shipping Schedule have been created'),
                'sticky': True,
                'type': 'success',
                'next': next_action,
            }
        }
        return notification
