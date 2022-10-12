# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from collections import namedtuple

from odoo import _, _lt, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class Warehouse(models.Model):
    _inherit = "stock.warehouse"

    code = fields.Char('Short Name', required=True, size=8, help="Short name used to identify your warehouse")

    """
        重载父类方法，将货位名称改为仓库名称，而不使用仓库代码
    """
    @api.model
    def create(self, vals):
        # create view location for warehouse then create all locations

        # Timwang modified at 2021/9/13
        # 将货位名称默认为仓库名称，而不使用仓库代码
        loc_vals = {'name': vals.get('name'), 'usage': 'view',
                    'location_id': self.env.ref('stock.stock_location_locations').id}

        # loc_vals = {'name': vals.get('name'), 'usage': 'view',
        #             'location_id': self.env.ref('stock.stock_location_locations').id}

        # 继续原有的代码

        if vals.get('company_id'):
            loc_vals['company_id'] = vals.get('company_id')
        vals['view_location_id'] = self.env['stock.location'].create(loc_vals).id
        sub_locations = self._get_locations_values(vals)

        for field_name, values in sub_locations.items():
            values['location_id'] = vals['view_location_id']
            if vals.get('company_id'):
                values['company_id'] = vals.get('company_id')
            vals[field_name] = self.env['stock.location'].with_context(active_test=False).create(values).id

        # actually create WH

        # Timwang modified at 2021/9/13
        # 调用父类的父类

        # warehouse = super(Warehouse, self).create(vals)
        warehouse = super(models.Model, self).create(vals)

        # create sequences and operation types
        new_vals = warehouse._create_or_update_sequences_and_picking_types()
        warehouse.write(new_vals)  # TDE FIXME: use super ?
        # create routes and push/stock rules
        route_vals = warehouse._create_or_update_route()
        warehouse.write(route_vals)

        # Update global route with specific warehouse rule.
        warehouse._create_or_update_global_routes_rules()

        # create route selectable on the product to resupply the warehouse from another one
        warehouse.create_resupply_routes(warehouse.resupply_wh_ids)

        # update partner data if partner assigned
        if vals.get('partner_id'):
            self._update_partner_data(vals['partner_id'], vals.get('company_id'))

        self._check_multiwarehouse_group()

        return warehouse

    """
        重载父类方法，将货位名称改为仓库名称，而不使用仓库代码
    """
    def _update_name_and_code(self, new_name=False, new_code=False):
        # Timwang modified at 2021/9/13
        # 将货位名称默认为仓库名称，而不使用仓库代码

        if new_name:
            self.mapped('lot_stock_id').mapped('location_id').write({'name': new_name})

        # if new_code:
        #     self.mapped('lot_stock_id').mapped('location_id').write({'name': new_code})

        # 继续原有的代码

        if new_name:

            # TDE FIXME: replacing the route name ? not better to re-generate the route naming ?
            for warehouse in self:
                routes = warehouse.route_ids
                for route in routes:
                    route.write({'name': route.name.replace(warehouse.name, new_name, 1)})
                    for pull in route.rule_ids:
                        pull.write({'name': pull.name.replace(warehouse.name, new_name, 1)})
                if warehouse.mto_pull_id:
                    warehouse.mto_pull_id.write({'name': warehouse.mto_pull_id.name.replace(warehouse.name, new_name, 1)})
        for warehouse in self:
            sequence_data = warehouse._get_sequence_values()
            # `ir.sequence` write access is limited to system user
            if self.user_has_groups('stock.group_stock_manager'):
                warehouse = warehouse.sudo()
            warehouse.in_type_id.sequence_id.write(sequence_data['in_type_id'])
            warehouse.out_type_id.sequence_id.write(sequence_data['out_type_id'])
            warehouse.pack_type_id.sequence_id.write(sequence_data['pack_type_id'])
            warehouse.pick_type_id.sequence_id.write(sequence_data['pick_type_id'])
            warehouse.int_type_id.sequence_id.write(sequence_data['int_type_id'])
