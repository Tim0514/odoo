# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
Added class to config the Amazon seller details
"""

from odoo import models, fields, api, _
from odoo.addons.iap.tools import iap_tools
from odoo.exceptions import UserError

from ..endpoint import REGISTER_ENDPOINT, VERIFY_ENDPOINT


class AmazonSellerConfig(models.TransientModel):
    """
    Added class to configure the seller details.
    """
    _inherit = 'res.config.amazon.seller'

    def test_amazon_connection(self):
        """
        Create Seller account in ERP if not created before.
        If auth_token and merchant_id found in ERP then raise UserError.
        If Amazon Seller Account is registered in IAP raise UserError.
        IF Amazon Seller Account is not registered in IAP then create it.
        This function will load Marketplaces automatically based on seller region.
        :return:
        """
        """
            Timwang modified at 2022/5/11
            判断店铺是否存在时，增加公司筛选
        """

        amazon_seller_obj = self.env['amazon.seller.ept']
        iap_account_obj = self.env['iap.account']
        seller_exist = amazon_seller_obj.search([('company_id', '=', self.company_id.id),
                                                 ('auth_token', '=', self.auth_token),
                                                 ('merchant_id', '=', self.merchant_id)])

        if seller_exist:
            raise UserError(_('Seller already exist with given Credential.'))

        account = iap_account_obj.search([('service_name', '=', 'amazon_ept')])
        if account:
            kwargs = self.prepare_marketplace_kwargs(account)
            response = iap_tools.iap_jsonrpc(VERIFY_ENDPOINT, params=kwargs, timeout=1000)
        else:
            account = iap_account_obj.create({'service_name': 'amazon_ept'})
            account._cr.commit()
            kwargs = self.prepare_marketplace_kwargs(account)
            response = iap_tools.iap_jsonrpc(REGISTER_ENDPOINT, params=kwargs, timeout=1000)

        if response.get('error', {}):
            raise UserError(_(response.get('error', {})))

        flag = response.get('result', {})
        if flag:
            company_id = self.company_id or self.env.user.company_id or False
            vals = self.prepare_amazon_seller_vals(company_id)
            if self.country_id.code in ['AE', 'DE', 'EG', 'ES', 'FR', 'GB', 'IN', 'IT', 'SA', \
                                        'TR', 'NL', 'SE']:
                vals.update({'is_european_region': True})
            else:
                vals.update({'is_european_region': False})
            try:
                seller = amazon_seller_obj.create(vals)
                if self.env.user.has_group('analytic.group_analytic_accounting'):
                    seller.create_analytic_account_and_group_records([seller])
                seller.load_marketplace()
                self.create_transaction_type(seller)

            except Exception as ex:
                raise UserError(_('Exception during instance creation.\n %s' % (str(ex))))
            action = self.env.ref(
                'amazon_ept.action_amazon_configuration', False)
            result = action.read()[0] if action else {}
            result.update({'seller_id': seller.id})
            if seller.amazon_selling in ['FBA', 'Both']:
                self.update_reimbursement_details(seller)
                seller.auto_create_stock_adjustment_configuration()
            seller.update_user_groups()

        return True
