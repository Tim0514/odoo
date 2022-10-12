# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

#
# Order Point Method:
#    - Order if the virtual stock of today is below the min of the defined order point
#

from odoo import api, models, tools

import logging
import threading

_logger = logging.getLogger(__name__)


class MrpProductionScheduleMasterCompute(models.TransientModel):
    _name = 'mrp.production.schedule.master.compute'
    _description = 'Regenerate Mrp Production Schedule Master Manually'

    def _regenerate_mrp_production_schedule_master(self):
        with api.Environment.manage():
            # As this function is in a new thread, I need to open a new cursor, because the old one may be closed
            new_cr = self.pool.cursor()
            self = self.with_env(self.env(cr=new_cr))
            scheduler_cron = self.sudo().env.ref('web_sale.ir_cron_regenerate_mrp_production_schedule_master_action')
            # Avoid to run the scheduler multiple times in the same time
            try:
                with tools.mute_logger('odoo.sql_db'):
                    self._cr.execute("SELECT id FROM ir_cron WHERE id = %s FOR UPDATE NOWAIT", (scheduler_cron.id,))
            except Exception:
                _logger.info('Attempt to Regenerate Mrp Production Schedule Master aborted, as already running')
                self._cr.rollback()
                self._cr.close()
                return {}

            for company in self.env.user.company_ids:
                cids = (self.env.user.company_id | self.env.user.company_ids).ids
                self.env['mrp.production.schedule.master'].with_context(allowed_company_ids=cids).run_scheduler(
                    use_new_cursor=self._cr.dbname,
                    company_id=company.id)
            new_cr.close()
            return {}

    def regenerate_mrp_production_schedule_master(self):
        threaded_regeneration = threading.Thread(target=self._regenerate_mrp_production_schedule_master, args=())
        threaded_regeneration.start()
        return {'type': 'ir.actions.client', 'tag': 'reload'}
