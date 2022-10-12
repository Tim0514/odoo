# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from dateutil.relativedelta import relativedelta
import copy


class AccountCashFlowReport(models.AbstractModel):
    _inherit = 'account.cash.flow.report'

    @api.model
    def _get_lines_to_compute(self, options):
        return [
            {
                'id': 'cash_flow_line_%s' % index,
                'name': name,
                'level': level,
                'class': 'o_account_reports_totals_below_sections' if self.env.company.totals_below_sections else '',
                'columns': [{'name': 0.0, 'class': 'number'}],
            } for index, level, name in [
                 (0, 0, '一、经营活动产生的现金流量：'),
                 (1, 1, '销售产成品、商品、提供劳务收到的现金'),
                 (2, 1, '收到其他与经营活动有关的现金'),
                 (3, 1, '购买原材料、商品、接受劳务支付的现金'),
                 (4, 1, '支付的职工薪酬'),
                 (5, 1, '支付的税费'),
                 (6, 1, '支付其他与经营活动有关的现金'),
                 (7, 1, '经营活动产生的现金流量净额'),
                 (8, 0, '二、投资活动产生的现金流量：'),
                 (9, 1, '处置固定资产、无形资产收回的现金净额'),
                 (10, 1, '收回短期投资、长期债券和长期股权投资收到的现金'),
                 (11, 1, '取得投资收益收到的现金'),
                 (12, 1, '构建固定资产和无形资产支付的现金'),
                 (13, 1, '短期投资、长期债券和长期股权投资支付的现金'),
                 (14, 1, '支付其他与投资活动有关的现金'),
                 (15, 1, '投资活动产生的现金流量净额'),
                 (16, 0, '三、筹资活动产生的现金流量：'),
                 (17, 1, '取得借款收到的现金'),
                 (18, 1, '吸收投资者投资收到的现金'),
                 (19, 1, '偿还借款本息支付的现金'),
                 (20, 1, '分配利润支付的现金'),
                 (21, 1, '筹资活动产生的现金流量净额'),
                 (22, 0, '四、现金净增加额：'),
                 (23, 1, '加：期初现金余额'),
                 (24, 0, '五、期末现金余额：'),
            ]
        ]

    @api.model
    def _get_tags_index(self):
        res = {}
        tags_idx = [
            ('l10n_cn_reports.account_tag_cf01', 1),
            ('l10n_cn_reports.account_tag_cf02', 2),
            ('l10n_cn_reports.account_tag_cf03', 3),
            ('l10n_cn_reports.account_tag_cf04', 4),
            ('l10n_cn_reports.account_tag_cf05', 5),
            ('l10n_cn_reports.account_tag_cf06', 6),
            ('l10n_cn_reports.account_tag_cf09', 9),
            ('l10n_cn_reports.account_tag_cf10', 10),
            ('l10n_cn_reports.account_tag_cf11', 11),
            ('l10n_cn_reports.account_tag_cf12', 12),
            ('l10n_cn_reports.account_tag_cf13', 13),
            ('l10n_cn_reports.account_tag_cf14', 14),
            ('l10n_cn_reports.account_tag_cf17', 17),
            ('l10n_cn_reports.account_tag_cf18', 18),
            ('l10n_cn_reports.account_tag_cf19', 19),
            ('l10n_cn_reports.account_tag_cf20', 20),
            ('l10n_cn_reports.account_tag_cf21', 21),
        ]
        for tag,idx in tags_idx:
            res.update({self.env.ref(tag): idx})
            
        return res

    @api.model
    def _get_lines(self, options, line_id=None):

        def _insert_at_index(index, account_id, account_code, account_name, amount):
            ''' Insert the amount in the right section depending the line's index and the account_id. '''
            # Helper used to add some values to the report line having the index passed as parameter
            # (see _get_lines_to_compute).
            line = lines_to_compute[index]

            if self.env.company.currency_id.is_zero(amount):
                return

            line.setdefault('unfolded_lines', {})
            line['unfolded_lines'].setdefault(account_id, {
                'id': account_id,
                'name': '%s %s' % (account_code, account_name),
                'level': line['level'] + 1,
                'parent_id': line['id'],
                'columns': [{'name': 0.0, 'class': 'number'}],
                'caret_options': 'account.account',
            })
            line['columns'][0]['name'] += amount
            line['unfolded_lines'][account_id]['columns'][0]['name'] += amount

        def _dispatch_result(account_id, account_code, account_name, account_internal_type, amount):
            ''' Dispatch the newly fetched line inside the right section. '''
            if account_internal_type == 'receivable':
                # 'Advance Payments received from customers'                (index=3)
                _insert_at_index(2, account_id, account_code, account_name, -amount)
            elif account_internal_type == 'payable':
                # 'Advance Payments made to suppliers'                      (index=5)
                _insert_at_index(6, account_id, account_code, account_name, -amount)
            else:
                for k,v in tags_index.items():
                    if k.id in tags_per_account.get(account_id, []):
                        _insert_at_index(v, account_id, account_code, account_name, -amount)
                    
        self.flush()
        unfold_all = self._context.get('print_mode') or options.get('unfold_all')
        currency_table_query = self.env['res.currency']._get_query_currency_table(options)
        lines_to_compute = self._get_lines_to_compute(options)
        
        tags_index = self._get_tags_index()
        
        tag_ids = tuple([x.id for x in tags_index.keys()])
        tags_per_account = self._get_tags_per_account(options, tag_ids)

        payment_move_ids, payment_account_ids = self._get_liquidity_move_ids(options)

        # ==== Process liquidity moves ====
        res = self._get_liquidity_move_report_lines(options, currency_table_query, payment_move_ids, payment_account_ids)
        for account_id, account_code, account_name, account_internal_type, amount in res:
            _dispatch_result(account_id, account_code, account_name, account_internal_type, amount)

        # ==== Process reconciled moves ====
        res = self._get_reconciled_move_report_lines(options, currency_table_query, payment_move_ids, payment_account_ids)
        for account_id, account_code, account_name, account_internal_type, balance in res:
            #print("%s=%s" % (account_name, balance) )
            _dispatch_result(account_id, account_code, account_name, account_internal_type, balance)

        # (7, 1, '经营活动产生的现金流量净额')
        lines_to_compute[7]['columns'][0]['name'] = \
            lines_to_compute[1]['columns'][0]['name'] + \
            lines_to_compute[2]['columns'][0]['name'] + \
            lines_to_compute[3]['columns'][0]['name'] + \
            lines_to_compute[4]['columns'][0]['name'] + \
            lines_to_compute[5]['columns'][0]['name'] + \
            lines_to_compute[6]['columns'][0]['name']

        # (15, 1, '投资活动产生的现金流量净额'),
        lines_to_compute[15]['columns'][0]['name'] = \
            lines_to_compute[9]['columns'][0]['name'] + \
            lines_to_compute[10]['columns'][0]['name'] + \
            lines_to_compute[11]['columns'][0]['name'] + \
            lines_to_compute[12]['columns'][0]['name'] + \
            lines_to_compute[13]['columns'][0]['name'] + \
            lines_to_compute[14]['columns'][0]['name']

        # (21, 1, '筹资活动产生的现金流量净额'),
        lines_to_compute[21]['columns'][0]['name'] = \
            lines_to_compute[17]['columns'][0]['name'] + \
            lines_to_compute[18]['columns'][0]['name'] + \
            lines_to_compute[19]['columns'][0]['name'] + \
            lines_to_compute[20]['columns'][0]['name']
        
        # (22, 0, '四、现金净增加额：'),
        lines_to_compute[22]['columns'][0]['name'] = \
            lines_to_compute[7]['columns'][0]['name'] + \
            lines_to_compute[15]['columns'][0]['name'] + \
            lines_to_compute[21]['columns'][0]['name']

        # (23, 1, '加：期初现金余额'),
        beginning_period_options = self._get_options_beginning_period(options)
        for account_id, account_code, account_name, balance in self._compute_liquidity_balance(beginning_period_options, currency_table_query, payment_account_ids):
            _insert_at_index(23, account_id, account_code, account_name, balance)

        # (24, 0, '五、期末现金余额：'),
        lines_to_compute[24]['columns'][0]['name'] = \
            lines_to_compute[22]['columns'][0]['name'] + \
            lines_to_compute[23]['columns'][0]['name']

        # ==== Compute the unexplained difference ====
        closing_ending_gap = lines_to_compute[24]['columns'][0]['name'] - lines_to_compute[0]['columns'][0]['name']
        computed_gap = sum(lines_to_compute[index]['columns'][0]['name'] for index in [22, 23])
        delta = closing_ending_gap - computed_gap
        if not self.env.company.currency_id.is_zero(delta):
            lines_to_compute.insert(24, {
                'id': 'cash_flow_line_unexplained_difference',
                'name': '未归类金额',
                'level': 0,
                'columns': [{'name': delta, 'class': 'number'}],
            })

        # ==== Build final lines ====
        lines = []
        for line in lines_to_compute:
            unfolded_lines = line.pop('unfolded_lines', {})
            sub_lines = [unfolded_lines[k] for k in sorted(unfolded_lines)]

            line['unfoldable'] = len(sub_lines) > 0
            line['unfolded'] = line['unfoldable'] and (unfold_all or line['id'] in options['unfolded_lines'])

            # Header line.
            line['columns'][0]['name'] = self.format_value(line['columns'][0]['name'])
            lines.append(line)

            # Sub lines.
            for sub_line in sub_lines:
                sub_line['columns'][0]['name'] = self.format_value(sub_line['columns'][0]['name'])
                sub_line['style'] = '' if line['unfolded'] else 'display: none;'
                lines.append(sub_line)

            # Total line.
            if line['unfoldable']:
                lines.append({
                    'id': '%s_total' % line['id'],
                    'name': _('Total') + ' ' + line['name'],
                    'level': line['level'] + 1,
                    'parent_id': line['id'],
                    'columns': line['columns'],
                    'class': 'o_account_reports_domain_total',
                    'style': '' if line['unfolded'] else 'display: none;',
                })
        return lines

    @api.model
    def _get_report_name(self):
        return '现金流量表 - 开源智造'
        