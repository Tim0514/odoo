# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

import time
from datetime import datetime, timedelta
import base64
import csv
from io import StringIO
import pytz
from dateutil import parser
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.addons.iap.tools import iap_tools
from ..endpoint import DEFAULT_ENDPOINT, DECODE_ENDPOINT

from odoo.tools.misc import xlsxwriter
from io import BytesIO
import os
import re


utc = pytz.utc
DATE_YMDHMS = "%Y-%m-%d %H:%M:%S"
DATE_YMDTHMS = "%Y-%m-%dT%H:%M:%S"
STOCK_MOVE = 'stock.move'
COMMON_LOG_BOOK_EPT = 'common.log.book.ept'
AMZ_SHIPPING_REPORT_REQUEST_HISTORY = 'shipping.report.request.history'
AMZ_SELLER_EPT = 'amazon.seller.ept'
SALE_ORDER = "sale.order"
IR_ACTION_ACT_WINDOW = 'ir.actions.act_window'
AMZ_INSTANCE_EPT = 'amazon.instance.ept'
COMMON_LOG_LINES_EPT = 'common.log.lines.ept'
RES_PARTNER = 'res.partner'
IR_MODEL = 'ir.model'
VIEW_MODE = 'tree,form'

IR_ATTACHMENT = 'ir.attachment'



class ShippingReportRequestHistory(models.Model):
    _inherit = "shipping.report.request.history"

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
        file_name = file_store + "/Shipment_report_" + time.strftime("%Y_%m_%d_%H%M%S") + '.xlsx'
        workbook = xlsxwriter.Workbook(file_name)
        worksheet = workbook.add_worksheet()
        header_format = workbook.add_format({'bold': True})

        imp_file = self.decode_amazon_encrypted_attachments_data_for_download_report(self.attachment_id)

        reader = csv.reader(imp_file, delimiter='\t')

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
            "name": "Shipment_report_" + time.strftime("%Y_%m_%d_%H%M%S"),
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

    def decode_amazon_encrypted_attachments_data_for_download_report(self, attachment_id):
        """
        This method will decode the amazon encrypted data
        """
        dbuuid = self.env['ir.config_parameter'].sudo().get_param('database.uuid')
        req = {'dbuuid': dbuuid, 'report_id': self.report_id,
               'datas': attachment_id.datas.decode(), 'amz_report_type': 'shipment_report'}
        imp_file = []
        response = iap_tools.iap_jsonrpc(DECODE_ENDPOINT, params=req, timeout=1000)
        if response.get('result', False):
            try:
                imp_file = StringIO(base64.b64decode(response.get('result', {})).decode())
            except Exception:
                imp_file = StringIO(base64.b64decode(response.get('result', {})).decode('ISO-8859-1'))
        elif not self._context.get('is_auto_process', False):
            raise UserError(_(response.get('error', '')))
        else:
            raise UserError('Error found in Decryption of Data %s' % response.get('error', ''))

        return imp_file
