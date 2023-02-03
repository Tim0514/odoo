# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models, tools

import logging
import threading

_logger = logging.getLogger(__name__)


class ShippingScheduleWizard(models.TransientModel):
    _name = 'web.sale.shipping.schedule.wizard'
    _description = 'Regenerate Shipping Schedule Manually'

    def _regenerate_shipping_schedule(self):
        with api.Environment.manage():
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

            company = self.env["res.company"].browse([1])

            self.env['web.sale.shipping.schedule'].with_context(allowed_company_ids=company.ids).run_scheduler(
                use_new_cursor=self._cr.dbname,
                company_id=company.id)
            # for company in self.env.user.company_ids:
            #     cids = (self.env.user.company_id | self.env.user.company_ids).ids
            #     self.env['web.sale.shipping.schedule'].with_context(allowed_company_ids=cids).run_scheduler(
            #         use_new_cursor=self._cr.dbname,
            #         company_id=company.id)
            new_cr.close()
            return {}

    def regenerate_shipping_schedule(self):
        self._regenerate_shipping_schedule()
        # threaded_regeneration = threading.Thread(target=self._regenerate_shipping_schedule, args=())
        # threaded_regeneration.start()
        return {'type': 'ir.actions.client', 'tag': 'reload'}
