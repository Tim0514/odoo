# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
Added class ActiveProductListingReportEpt and added function to request for the active
product report and get the active product from the amazon and process to sync the product
and process to create the odoo and amazon product.
"""
import base64
import csv
import os
import time
from io import StringIO
from io import BytesIO
import re
from odoo import models, fields, api, _
from odoo.addons.iap.tools import iap_tools
from odoo.exceptions import UserError
from odoo.tools.misc import xlsxwriter
from ..endpoint import DEFAULT_ENDPOINT
from .. reportTypes import ReportType

COMMON_LOG_LINES_EPT = 'common.log.lines.ept'
COMMON_LOG_BOOK_EPT = 'common.log.book.ept'
PRODUCT_PRODUCT = 'product.product'
IR_MODEL = 'ir.model'
IR_CONFIG_PARAMETER = 'ir.config_parameter'
IAP_ACCOUNT = 'iap.account'
IR_ATTACHMENT = 'ir.attachment'
DATABASE_UUID = 'database.uuid'
ACTIVE_PRODUCT_LISTING_REPORT_EPT = 'active.product.listing.report.ept'


class ActiveProductListingReportEpt(models.Model):
    """
    Added class to process for get amazon product report and process to create odoo and amazon
    product
    """
    _name = "active.product.listing.report.ept"
    _description = "Active Product"
    _inherit = ['mail.thread', 'amazon.reports']
    _order = 'id desc'

    @api.model
    @api.depends('seller_id')
    def _compute_company(self):
        """
        The below method sets company for a particular record
        """
        for record in self:
            company_id = record.seller_id.company_id.id if record.seller_id else False
            if not company_id:
                company_id = self.env.company.id
            record.company_id = company_id

    def _compute_log_count(self):
        """
        Find all stock moves associated with this report
        :return:
        """
        log_obj = self.env[COMMON_LOG_BOOK_EPT]
        model_id = self.env[IR_MODEL]._get(ACTIVE_PRODUCT_LISTING_REPORT_EPT).id
        log_ids = log_obj.search([('res_id', '=', self.id), ('model_id', '=', model_id)]).ids
        self.log_count = log_ids.__len__()

        # Set the boolean field mismatch_details as True if found any mismatch details in log lines
        if self.env[COMMON_LOG_LINES_EPT].search_count(
                [('log_book_id', 'in', log_ids), ('mismatch_details', '=', True)]):
            self.mismatch_details = True
        else:
            self.mismatch_details = False

    name = fields.Char(size=256, help='Record number')
    instance_id = fields.Many2one('amazon.instance.ept', string='Marketplace',
                                  help='Record of instance')
    report_id = fields.Char('Report ID', readonly='1', help='ID of report')
    report_request_id = fields.Char('Report Request ID', readonly='1',
                                    help='Request ID of the report')
    attachment_id = fields.Many2one(IR_ATTACHMENT, string='Attachment',
                                    help='Record of attachment')
    report_type = fields.Char(size=256, help='Type of report')
    state = fields.Selection([('draft', 'Draft'), ('_SUBMITTED_', 'SUBMITTED'), ('_IN_PROGRESS_', 'IN_PROGRESS'),
                              ('_CANCELLED_', 'CANCELLED'), ('_DONE_', 'DONE'), ('CANCELLED', 'CANCELLED'),
                              ('SUBMITTED', 'SUBMITTED'), ('DONE', 'DONE'), ('FATAL', 'FATAL'),
                              ('IN_PROGRESS', 'IN_PROGRESS'), ('IN_QUEUE', 'IN_QUEUE'),
                              ('_DONE_NO_DATA_', 'DONE_NO_DATA'), ('processed', 'PROCESSED'),
                              ('imported', 'Imported'), ('partially_processed', 'Partially Processed'),
                              ('closed', 'Closed')], string='Report Status', default='draft', help='State of record')
    seller_id = fields.Many2one('amazon.seller.ept', string='Seller', copy=False,
                                help='ID of seller')
    user_id = fields.Many2one('res.users', string="Requested User", help='ID of user')
    company_id = fields.Many2one('res.company', string="Company", copy=False,
                                 compute="_compute_company", store=True, help='ID of company')
    update_price_in_pricelist = fields.Boolean(string='Update price in pricelist?', default=False,
                                               help='Update or create product line in pricelist if ticked.')
    auto_create_product = fields.Boolean(string='Auto create product?', default=False,
                                         help='Create product in ERP if not found.')
    log_count = fields.Integer(compute="_compute_log_count", string="Log Counter",
                               help="Count number of created Stock Move")
    mismatch_details = fields.Boolean(compute="_compute_log_count", string='Mismatch details',
                                      help='True if any mismatch details found in the log line')
    report_document_id = fields.Char(string='Report Document Reference', help='Request Document ID')

    def list_of_process_logs(self):
        """
        This method will List Of Logs View in active product listing record
        :return:
        """
        model_id = self.env[IR_MODEL]._get(ACTIVE_PRODUCT_LISTING_REPORT_EPT).id
        action = {
            'domain': "[('res_id', '=', " + str(self.id) + " ),('model_id','='," + str(model_id) + ")]",
            'name': 'Active Product Logs',
            'view_mode': 'tree,form',
            'res_model': COMMON_LOG_BOOK_EPT,
            'type': 'ir.actions.act_window',
        }
        return action

    @api.model
    def create(self, vals):
        """
        The below method sets name of a particular record as per the sequence.
        """
        sequence = self.env.ref('amazon_ept.seq_active_product_list', raise_if_not_found=False)
        report_name = sequence.next_by_id() if sequence else '/'
        vals.update({'name': report_name})
        return super(ActiveProductListingReportEpt, self).create(vals)

    def request_report(self):
        """
        The below method requests the record of the report.
        """
        seller = self.instance_id.seller_id
        if not seller:
            raise UserError(_('Please select instance'))
        kwargs = self.prepare_amazon_request_report_kwargs(seller)
        marketplace_ids = tuple([self.instance_id.market_place_id])
        kwargs.update({'emipro_api': 'create_marketplace_report_sp_api',
                       'report_type': self.report_type or ReportType.GET_MERCHANT_LISTINGS_DATA,
                       'marketplace_ids': marketplace_ids,})
        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT, params=kwargs, timeout=1000)
        if response.get('error', False):
            raise UserError(_(response.get('error', {})))
        if response.get('result', {}):
            self.update_report_history(response.get('result', {}))
        return True

    def create_amazon_report_attachment(self, result):
        """
        Get Sync Product Listing Report as an attachment in Product Listing
        reports form view.
        """
        result = result.get('document', '')
        result = result.encode()
        result = base64.b64encode(result)
        file_name = "Active_Product_List_" + time.strftime("%Y_%m_%d_%H%M%S") + '.csv'
        attachment = self.env[IR_ATTACHMENT].create({
            'name': file_name,
            'datas': result,
            'res_model': 'mail.compose.message',
            'type': 'binary'
        })
        self.message_post(body=_("<b>Active Product Report Downloaded</b>"),
                          attachment_ids=attachment.ids)
        self.write({'attachment_id': attachment.id})

    def download_report(self):
        """
            @author :  Harnisha Patel
            @modified_by : Sunil Khatri \n
            @last_updated_on : 4/21/2021 \n
            Below method downloads the report in excel format.

        :return: An action containing URL of excel attachment or bool.
        """
        self.ensure_one()

        # Get filestore path of an attachment and create new excel file there.
        file_store = self.env[IR_ATTACHMENT]._filestore()
        file_name = file_store + "/Active_Product_List_" + time.strftime("%Y_%m_%d_%H%M%S") + '.xlsx'
        workbook = xlsxwriter.Workbook(file_name)
        worksheet = workbook.add_worksheet()
        header_format = workbook.add_format({'bold': True})

        # Collect data from csv attachment file and convert it to excel.
        data = StringIO(base64.b64decode(self.attachment_id.datas).decode('utf-8'))
        reader = csv.reader(data, delimiter='\t')
        for r, row in enumerate(reader):
            for c, col in enumerate(row):
                if r == 0:
                    worksheet.write(r, c, col, header_format)
                else:
                    if bool(re.match('^(?=.)([+-]?([0-9]*)(\.([0-9]+))?)$', col)):
                        col = float(col)
                    worksheet.write(r, c, col)
        workbook.close()

        # Create file pointer of excel file for reading purpose.
        excel_file = open(file_name, "rb")
        file_pointer = BytesIO(excel_file.read())
        file_pointer.seek(0)

        # Create an attachment from that file pointer.
        new_attachment = self.env[IR_ATTACHMENT].create({
            "name": "Active_Product_List_" + time.strftime("%Y_%m_%d_%H%M%S"),
            "datas": base64.b64encode(file_pointer.read()),
            "type": "binary"
        })

        # Close file pointer and file and remove file from filestore.
        file_pointer.close()
        excel_file.close()
        os.remove(file_name)

        # Download an attachment if it is created.
        if new_attachment:
            return {
                'type': 'ir.actions.act_url',
                'url': '/web/content/%s?download=true' % new_attachment.id,
                'target': 'self',
            }
        return False

    def reprocess_sync_products(self):
        """
        Added this method to reprocess for sync products.
        @modified_by : Sunil Khatri
        @modification: Delete previous log and it's log lines before reprocessing again.
        @modification_date : 22/04/2021
        """
        model_id = self.env[IR_MODEL]._get(ACTIVE_PRODUCT_LISTING_REPORT_EPT).id
        previous_logs = self.env[COMMON_LOG_BOOK_EPT].search([('res_id', '=', self.id),
                                                              ('model_id', '=', model_id)])
        if previous_logs:
            previous_logs.unlink()
        self.sync_products()

    @staticmethod
    def get_fulfillment_type(row):
        """
        The below method returns the fulfillment type value.
        :param row: dict{}
        :return:
        """
        if 'fulfilment-channel' in row.keys():
            fulfillment_channel = row.get('fulfilment-channel', '')
        else:
            fulfillment_channel = row.get('fulfillment-channel', '')
        if fulfillment_channel and fulfillment_channel == 'DEFAULT':
            return 'FBM'  # 'MFN'
        return 'FBA'  # 'AFN'

    def update_pricelist_items(self, seller_sku, price):
        """
        The below method creates or updates the price of a product in the pricelist.
        :param seller_sku: string
        :param price: float
        :return:
        """
        pricelist_item_obj = self.env['product.pricelist.item']
        product_obj = self.env['product.template']
        if self.instance_id.pricelist_id and self.update_price_in_pricelist:
            item = self.instance_id.pricelist_id.item_ids.filtered(
                lambda i: i.product_tmpl_id.default_code == seller_sku)
            if item and not item.fixed_price == float(price):
                item.fixed_price = price
            if not item:
                product = product_obj.search([('default_code', '=', seller_sku)])
                pricelist_item_obj.create({'product_tmpl_id': product.id,
                                           'min_quantity': 1,
                                           'fixed_price': price,
                                           'pricelist_id': self.instance_id.pricelist_id.id})

    def sync_products(self):
        """
        The below method syncs the products and also creates record of log if error is
        generated.
        """
        self.ensure_one()
        # check instance and attachment configured
        self.check_instance_and_attachment_configured()
        amazon_product_ept_obj = self.env['amazon.product.ept']
        product_obj = self.env[PRODUCT_PRODUCT]
        log_book_obj = self.env[COMMON_LOG_BOOK_EPT]
        comman_log_line_obj = self.env[COMMON_LOG_LINES_EPT]
        log_model_id = comman_log_line_obj.get_model_id(ACTIVE_PRODUCT_LISTING_REPORT_EPT)
        model_id = comman_log_line_obj.get_model_id(PRODUCT_PRODUCT)
        log_rec = log_book_obj.amazon_create_transaction_log('import', log_model_id, self.id)
        imp_file = StringIO(base64.b64decode(self.attachment_id.datas).decode())
        reader = csv.DictReader(imp_file, delimiter='\t')
        #get import file headers name
        headers = reader.fieldnames
        skip_header = self.read_import_file_header(headers, model_id, log_rec, comman_log_line_obj)
        if skip_header:
            raise UserError(_("The Header of this report must be in English Language,"
                              " Please contact Emipro Support for further Assistance."))
        for row in reader:
            fulfillment_type = self.get_fulfillment_type(row)
            seller_sku = row.get('seller-sku', '').strip()
            odoo_product = product_obj.search(
                ['|', ('default_code', '=ilike', seller_sku), ('barcode', '=ilike', seller_sku)])
            amazon_product_id = amazon_product_ept_obj.search_amazon_product(
                self.instance_id.id, seller_sku, fulfillment_by=fulfillment_type)
            if not amazon_product_id and not odoo_product:
                amazon_product = amazon_product_ept_obj.search(
                    ['|', ('active', '=', False), ('active', '=', True), ('seller_sku', '=', seller_sku)],
                    limit=1)
                odoo_product = amazon_product.product_id
            if amazon_product_id:
                self.create_or_update_amazon_product_ept(amazon_product_id, amazon_product_id.product_id.id,
                                                         fulfillment_type, row)
                self.amz_update_price_in_pricelist(row, amazon_product_id.product_id)
            else:
                if len(odoo_product.ids) > 1:
                    seller_sku = row.get('seller-sku', '').strip()
                    message = """Multiple product found for same sku %s in ERP """ % (seller_sku)
                    comman_log_line_obj.amazon_create_product_log_line(
                        message, model_id, False, seller_sku, fulfillment_type, log_rec, mismatch=True)
                    continue
                self.create_odoo_or_amazon_product_ept(odoo_product, fulfillment_type, row, log_rec)
        if not log_rec.log_lines:
            log_rec.unlink()
        self.write({'state': 'processed'})
        return True

    def check_instance_and_attachment_configured(self):
        """
        This method check Amazon Instance and Attachment file and Pricelist configured.
        @author : kishan sorani
        """
        if not self.attachment_id:
            raise UserError(_("There is no any report are attached with this record."))
        if not self.instance_id:
            raise UserError(_("Instance not found "))
        if not self.instance_id.pricelist_id:
            raise UserError(_("Please configure Pricelist in Amazon Marketplace"))

    def read_import_file_header(self, headers, model_id, log_rec, comman_log_line_obj):
        """
        This method read import file headers name are correct or not.
        @param : headers - list of import file headers
        @:param : model_id - object of model for created log line
        @:param : log_rec - object of common log book model
        @:param : comman_log_line_obj - object of common log lines book model
        :return: This Method return boolean(True/False).
        @author: Kishan Sorani
        """
        skip_header = False
        if self.auto_create_product and 'item-name' not in headers:
            message = 'Import file is skipped due to header item-name is incorrect or blank'
            comman_log_line_obj.amazon_create_product_log_line(message, model_id, False, False,
                                                               False, log_rec, mismatch=True)
            skip_header = True

        elif 'seller-sku' not in headers:
            message = 'Import file is skipped due to header seller-sku is incorrect or blank'
            comman_log_line_obj.amazon_create_product_log_line(message, model_id, False, False,
                                                               False, log_rec, mismatch=True)
            skip_header = True

        elif 'fulfilment-channel' not in headers and 'fulfillment-channel' not in headers:
            message = 'Import file is skipped due to header fulfilment-channel is incorrect or blank'
            comman_log_line_obj.amazon_create_product_log_line(message, model_id, False, False,
                                                               False, log_rec, mismatch=True)
            skip_header = True
        return skip_header

    def create_or_update_amazon_product_ept(self, amazon_product_id, odoo_product,
                                            fulfillment_type, row):
        """
        This method will create tha amazon product if it is exist and if amazon
        product exist that it will update that
        param amazon_product_id : amazon product id
        param odoo_product : odoo product
        param fulfillment_type : selling on
        param row : report data
        """

        amazon_product_ept_obj = self.env['amazon.product.ept']
        description = row.get('item-description', '') and row.get('item-description', '')
        name = row.get('item-name', '') and row.get('item-name', '')
        seller_sku = row.get('seller-sku', '').strip()

        if not amazon_product_id:
            amazon_product_ept_obj.create({
                'product_id': odoo_product.id,
                'instance_id': self.instance_id.id,
                'name': name,
                'long_description': description,
                'product_asin': row.get('asin1', ''),
                'seller_sku': seller_sku,
                'fulfillment_by': fulfillment_type,
                'exported_to_amazon': True
            })
        else:
            amazon_product_id.write({
                'name': name,
                'long_description': description,
                'seller_sku': seller_sku,
                'fulfillment_by': fulfillment_type,
                'product_asin': row.get('asin1', ''),
                'exported_to_amazon': True,
            })

    def create_odoo_or_amazon_product_ept(self, odoo_product, fulfillment_type, row, log_rec):
        """
        This method is used to create odoo or amazon product.
        :param odoo_product : odoo product id
        :param fulfillment_type : selling on
        :param row : report line data
        :param log_rec : log record.
        """
        product_obj = self.env[PRODUCT_PRODUCT]
        comman_log_line_obj = self.env[COMMON_LOG_LINES_EPT]
        model_id = comman_log_line_obj.get_model_id(PRODUCT_PRODUCT)
        created_product = False
        seller_sku = row.get('seller-sku', '').strip()
        if odoo_product:
            self.create_or_update_amazon_product_ept(False, odoo_product, fulfillment_type, row)
            self.amz_update_price_in_pricelist(row, odoo_product)
        else:
            if self.auto_create_product:
                if not row.get('item-name', ''):
                    message = """ Line Skipped due to product name not found of seller sku %s || Instance %s
                    """ % (seller_sku, self.instance_id.name)
                    is_mismatch = True
                else:
                    created_product = product_obj.create(
                        {'default_code': seller_sku,
                         'name': row.get('item-name', ''),
                         'type': 'product'})
                    self.create_or_update_amazon_product_ept(False, created_product, fulfillment_type, row)
                    message = """ Product created for seller sku %s || Instance %s """ % (seller_sku,
                                                                                          self.instance_id.name)
                    is_mismatch = False
                    self.amz_update_price_in_pricelist(row, created_product)
            else:
                message = """ Line Skipped due to product not found seller sku %s || Instance %s
                """ % (seller_sku, self.instance_id.name)
                is_mismatch = True
            comman_log_line_obj.amazon_create_product_log_line(message, model_id, created_product, seller_sku,
                                                               fulfillment_type, log_rec, row.get('item-name'),
                                                               mismatch=is_mismatch)
        return True

    def amz_update_price_in_pricelist(self, row, odoo_product):
        """
        Update or set Price in pricelist for configured product
        :param row: dict{}
        :param odoo_product: product.product()
        :return:
        """
        price_list_id = self.instance_id.pricelist_id
        if self.update_price_in_pricelist and row.get('price', False):
            price_list_id.set_product_price_ept(odoo_product.id, float(row.get('price')))
