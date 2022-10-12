# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

"""
This will perform the amazon inbound shipment plan operations
"""

from odoo import models, fields, api, _
from odoo.addons.iap.tools import iap_tools
from odoo.exceptions import UserError
from dateutil import relativedelta

INBOUND_SHIPMENT_PLAN_EPT = 'inbound.shipment.plan.ept'
COMMON_LOG_LINES_EPT = 'common.log.lines.ept'
AMAZON_INBOUND_SHIPMENT_EPT = 'amazon.inbound.shipment.ept'

class InboundShipmentPlanEpt(models.Model):
    _inherit = "inbound.shipment.plan.ept"

    estimated_date_of_arrival = fields.Date('Estimated Date of Arrival', compute='_compute_estimated_date_of_arrival',
                                            readonly=True, states={'draft': [('readonly', False)]})

    ship_from_address_id = fields.Many2one('res.partner', string='Ship From Address', readonly=True,
                                           states={'draft': [('readonly', False)]})

    @api.depends('warehouse_id')
    def _compute_estimated_date_of_arrival(self):
        location_route_obj = self.env['stock.location.route']

        for odoo_shipment_plan in self:
            warehouse = odoo_shipment_plan.instance_id.warehouse_id or False

            if warehouse:
                location_routes = location_route_obj.search([('supplied_wh_id', '=', warehouse.id), (
                    'supplier_wh_id', '=', odoo_shipment_plan.warehouse_id.id)])
                if not location_routes:
                    odoo_shipment_plan.estimated_date_of_arrival = fields.Date.today()
                else:
                    location_routes = location_routes[0]

                    lead_days = sum(location_routes.rule_ids.filtered(lambda r: r.action in ['pull', 'pull_push']).mapped('delay'))

                    # lead_days,dummy = location_routes.rule_ids._get_lead_days(False)
                    lead_days_date = fields.Date.today() + relativedelta.relativedelta(days=lead_days)
                    odoo_shipment_plan.estimated_date_of_arrival = lead_days_date
            else:
                odoo_shipment_plan.estimated_date_of_arrival = fields.Date.today()

    @api.model
    def create_procurements(self, odoo_shipments, job=False):
        """
        重载本方法，设置到货时间为estimated_date_of_arrival
        """
        """
        This method will process shipments and create procurements
        param odoo_shipments : list of odoo shipments
        param job : log record
        """
        proc_group_obj = self.env['procurement.group']
        picking_obj = self.env['stock.picking']
        location_route_obj = self.env['stock.location.route']
        log_book_obj = self.env['common.log.book.ept']
        log_line_obj = self.env[COMMON_LOG_LINES_EPT]
        group_wh_dict = {}
        model_id = log_line_obj.get_model_id(AMAZON_INBOUND_SHIPMENT_EPT)
        for shipment in odoo_shipments:
            proc_group = proc_group_obj.create({'odoo_shipment_id': shipment.id, 'name': shipment.name})
            fulfill_center = shipment.fulfill_center_id
            ship_plan = shipment.shipment_plan_id
            fulfillment_center = self.env['amazon.fulfillment.center'].search(
                [('center_code', '=', fulfill_center),
                 ('seller_id', '=', ship_plan.instance_id.seller_id.id)])
            fulfillment_center = fulfillment_center and fulfillment_center[0]
            warehouse = fulfillment_center and fulfillment_center.warehouse_id or \
                        ship_plan.instance_id.fba_warehouse_id or ship_plan.instance_id.warehouse_id or False

            if not warehouse:
                if not job:
                    job = log_book_obj.create({'module': 'amazon_ept', 'type': 'export'})
                error_value = 'No any warehouse found related to fulfillment center %s. Please set ' \
                              'fulfillment center %s in warehouse || shipment %s.' % (
                                  fulfill_center, fulfill_center, shipment.name)
                log_line_obj.create_log_lines(error_value, model_id, shipment, job)
                continue
            location_routes = location_route_obj.search([('supplied_wh_id', '=', warehouse.id), (
                'supplier_wh_id', '=', ship_plan.warehouse_id.id)])
            if not location_routes:
                if not job:
                    job = log_book_obj.create({'module': 'amazon_ept', 'type': 'export'})
                error_value = 'Location routes are not found. Please configure routes in warehouse ' \
                              'properly || warehouse %s & shipment %s.' % (warehouse.name, shipment.name)
                log_line_obj.create_log_lines(error_value, model_id, shipment, job)
                continue
            location_routes = location_routes[0]
            group_wh_dict.update({proc_group: warehouse})
            for line in shipment.odoo_shipment_line_ids:
                qty = line.quantity
                amazon_product = line.amazon_product_id
                datas = {'route_ids': location_routes,
                         'group_id': proc_group,
                         'company_id': ship_plan.instance_id.company_id.id,
                         'warehouse_id': warehouse,
                         'priority': '1'}

                # Timwang added on 2022/4/20
                # 加上到货时间
                datas.update({'date_planned': ship_plan.estimated_date_of_arrival})

                proc_group_obj.run([self.env['procurement.group'].Procurement(
                    amazon_product.product_id, qty, amazon_product.product_id.uom_id,
                    warehouse.lot_stock_id, amazon_product.product_id.name, shipment.name,
                    ship_plan.instance_id.company_id, datas)])
        if group_wh_dict:
            for group, warehouse in group_wh_dict.items():
                picking = picking_obj.search([('group_id', '=', group.id),
                                              ('picking_type_id.warehouse_id', '=', warehouse.id)])
                if picking:
                    picking.write({'is_fba_wh_picking': True})
        for shipment in odoo_shipments:
            pickings = shipment.mapped('picking_ids').filtered(
                lambda pick: not pick.is_fba_wh_picking and pick.state not in ['done', 'cancel'])
            for picking in pickings:
                picking.action_assign()
        return True

    @api.onchange('warehouse_id')
    def onchange_warehouse_id(self):
        # 禁止带入南京公司仓库
        """
        This will set the ship address based on warehouse
        """
        # if self.warehouse_id:
        #     self.ship_from_address_id = self.warehouse_id.partner_id and \
        #                                 self.warehouse_id.partner_id.id