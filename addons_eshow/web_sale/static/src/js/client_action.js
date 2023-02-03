odoo.define('web_sale.ClientAction', function (require) {
'use strict';

const { ComponentWrapper } = require('web.OwlCompatibility');

var concurrency = require('web.concurrency');
var core = require('web.core');
var Pager = require('web.Pager');
var AbstractAction = require('web.AbstractAction');
var Dialog = require('web.Dialog');
var field_utils = require('web.field_utils');

var QWeb = core.qweb;
var _t = core._t;

const defaultPagerSize = 20;

var ClientAction = AbstractAction.extend({
    contentTemplate: 'shipping_schedule_main',
    hasControlPanel: true,
    loadControlPanel: true,
    withSearchBar: true,
    searchMenuTypes: ['filter', 'groupBy', 'favorite'],
    custom_events: _.extend({}, AbstractAction.prototype.custom_events, {
        pager_changed: '_onPagerChanged',
    }),
    events: {
        'change .o_shipping_schedule_main_input_forcast_qty': '_onChangeForecast',
        'change .o_shipping_schedule_main_input_safety_inventory': '_onChangeSafetyInventory',
        'change .o_shipping_schedule_main_input_arriving_qty_apply': '_onChangeArrivingQtyApply',
        'change .o_shipping_schedule_main_input_arriving_qty_verify': '_onChangeArrivingQtyVerify',

        'click .o_shipping_schedule_safety_inventory_auto_mode': '_onClickSafetyInventoryAutoMode',
        'click .o_shipping_schedule_forecast_sale_qty_auto_mode': '_onClickForecastSaleQtyAutoMode',
        'click .o_shipping_schedule_arriving_qty_apply_auto_mode': '_onClickArrivingQtyApplyAutoMode',
        'click .o_shipping_schedule_arriving_qty_verify_auto_mode': '_onClickArrivingQtyVerifyAutoMode',

        'click .o_shipping_schedule_sales_confirm': '_onClickSalesConfirm',
        'click .o_shipping_schedule_logistics_confirm': '_onClickLogisticsConfirm',
        'click .o_shipping_schedule_cancel_confirm': '_onClickCancelConfirm',

        'click .o_shipping_schedule_procurement': '_onClickReplenish',

        'click .o_shipping_schedule_record_url': '_onClickRecordLink',
        'click .o_shipping_schedule_hide': '_onClickHide',

        'focus .o_shipping_schedule_main_input_forcast_qty': '_onFocusInputControl',
        'focus .o_shipping_schedule_main_input_safety_inventory': '_onFocusInputControl',
        'focus .o_shipping_schedule_main_input_arriving_qty_apply': '_onFocusInputControl',
        'focus .o_shipping_schedule_main_input_arriving_qty_verify': '_onFocusInputControl',

        'mouseover .o_shipping_schedule_procurement': '_onMouseOverReplenish',
        'mouseout .o_shipping_schedule_procurement': '_onMouseOutReplenish',

    },

    init: function (parent, action) {
        //set action.domain from action.params.domain
        action.domain = action.params.domain

        this._super.apply(this, arguments);
        this.actionManager = parent;
        this.action = action;
        this.context = action.context;
        this.domain = [];

        this.companyId = false;
        this.date_range = [];
        this.formatFloat = field_utils.format.float;
        this.manufacturingPeriod = false;
        this.manufacturingPeriods = [];
        this.state = false;

        this.active_ids = [];
        this.pager = false;
        this.recordsPager = false;
        this.mutex = new concurrency.Mutex();

        this.searchModelConfig.modelName = 'web.sale.shipping.schedule';
    },

    async willStart() {
        await this._super(...arguments);
        const searchQuery = this.controlPanelProps.searchModel.get("query");
        this.domain = searchQuery.domain;
        if ('shipping_schedule_group_id' in this.context) {
            this.domain.push(["shipping_schedule_group_id" , "=" , this.context.shipping_schedule_group_id])
        }
        await this._getRecordIds();
        await this._getState();
    },

    start: async function () {
        await this._super(...arguments);
        if (this.state.length == 0) {
            this.$el.find('.o_shipping_schedule_main').append($(QWeb.render('shipping_schedule_main_nocontent_helper')));
        }
        await this.update_cp();
        await this.renderPager();
    },

    //--------------------------------------------------------------------------
    // Public
    //--------------------------------------------------------------------------


    /**
     * Create the Pager and render it. It needs the records information to determine the size.
     * It also needs the controlPanel to be rendered in order to append the pager to it.
     */
    renderPager: async function () {
        const currentMinimum = 1;
        const limit = defaultPagerSize;
        const size = this.recordsPager.length;

        this.pager = new ComponentWrapper(this, Pager, { currentMinimum, limit, size });

        await this.pager.mount(document.createDocumentFragment());
        const pagerContainer = Object.assign(document.createElement('span'), {
            className: 'o_shipping_schedule_pager float-right',
        });
        pagerContainer.appendChild(this.pager.el);
        this.$pager = pagerContainer;

        this._controlPanelWrapper.el.querySelector('.o_cp_pager').append(pagerContainer);
    },

    /**
     * Update the control panel in order to add the 'replenish' button and a
     * custom menu with checkbox buttons in order to hide/display the different
     * rows.
     */
    update_cp: async function () {
        this.$buttons = $(QWeb.render('shipping_schedule_main_control_panel_buttons', {}));
        this._update_cp_buttons();

        var $salesConfirmButton = this.$buttons.find('.o_shipping_schedule_main_sales_confirm');
        $salesConfirmButton.on('click', this._onClickSalesConfirm.bind(this));

        var $logisticsConfirmButton = this.$buttons.find('.o_shipping_schedule_main_logistics_confirm');
        $logisticsConfirmButton.on('click', this._onClickLogisticsConfirm.bind(this));

        var $replenishButton = this.$buttons.find('.o_shipping_schedule_main_replenish');
        $replenishButton.on('click', this._onClickReplenish.bind(this));
        $replenishButton.on('mouseover', this._onMouseOverReplenish.bind(this));
        $replenishButton.on('mouseout', this._onMouseOutReplenish.bind(this));

        var $cancelConfirmButton = this.$buttons.find('.o_shipping_schedule_main_cancel_confirm');
        $cancelConfirmButton.on('click', this._onClickCancelConfirm.bind(this));

        const res = await this.updateControlPanel({
            title: _t('Shipping Schedule'),
            cp_content: {
                $buttons: this.$buttons,
            },
        });
        return res;
    },

    loadFieldView: function (modelName, context, view_id, view_type, options) {
        // add the action_id to get favorite search correctly
        options.action_id = this.action.id;
        return this._super(...arguments);
    },

    //--------------------------------------------------------------------------
    // Private
    //--------------------------------------------------------------------------

    /**
     * Make an rpc to replenish the different schedules passed as arguments.
     * If the procurementIds list is empty, it replenish all the schedules under
     * the current domain. Reload the content after the replenish in order to
     * display the new forecast cells to run.
     *
     * @private
     * @param {Array} [shippingScheduleId] mrp.shipping.schedule id to
     * replenish or False if it needs to replenish all schedules in state.
     * @return {Promise}
     */
    _actionReplenish: function (shippingScheduleId) {
        var self = this;
        var ids;
        var basedOnLeadTime;
        if (shippingScheduleId.length) {
            ids = shippingScheduleId;
            basedOnLeadTime = false;
        }
        else {
            ids = self.active_ids;
            basedOnLeadTime = true;
        }
        this.mutex.exec(function () {
            return self._rpc({
                model: 'web.sale.shipping.schedule',
                method: 'action_replenish',
                args: [ids, basedOnLeadTime]
            }).then(function (){
                return self._reloadContent();
            });
        });
    },

    _actionSalesConfirm: function (shippingScheduleId) {
        var self = this;
        var ids;
        if (shippingScheduleId.length) {
            ids = shippingScheduleId;
        }
        else {
            ids = self.active_ids;
        }
        this.mutex.exec(function () {
            return self._rpc({
                model: 'web.sale.shipping.schedule',
                method: 'action_sales_confirm',
                args: [ids]
            }).then(function (){
                return self._reloadContent();
            });
        });
    },

    _actionLogisticsConfirm: function (shippingScheduleId) {
        var self = this;
        var ids;
        if (shippingScheduleId.length) {
            ids = shippingScheduleId;
        }
        else {
            ids = self.active_ids;
        }
        this.mutex.exec(function () {
            return self._rpc({
                model: 'web.sale.shipping.schedule',
                method: 'action_logistics_confirm',
                args: [ids]
            }).then(function (){
                return self._reloadContent();
            });
        });
    },

    _actionCancelConfirm: function (shippingScheduleId) {
        var self = this;
        var ids;
        if (shippingScheduleId.length) {
            ids = shippingScheduleId;
        }
        else {
            ids = self.active_ids;
        }
        this.mutex.exec(function () {
            return self._rpc({
                model: 'web.sale.shipping.schedule',
                method: 'action_cancel_confirm',
                args: [ids]
            }).then(function (){
                return self._reloadContent();
            });
        });
    },


    _backToState: function (shippingScheduleId) {
        var state = _.where(_.flatten(_.values(this.state)), {id: shippingScheduleId});
        return this._renderState(state);
    },

    _focusNextInput: function (shippingScheduleId, dateIndex, inputName) {
        var tableSelector = '.o_shipping_schedule_main_content[data-id=' + shippingScheduleId + ']';
        var rowSelector = 'span[name=' + inputName + ']';
        var inputSelector = 'input[data-date_index=' + (dateIndex + 1) + ']';
        return $([tableSelector, rowSelector, inputSelector].join(' ')).select();
    },

    _getRecordIds: function () {
        var self = this;
        return this._rpc({
            model: 'web.sale.shipping.schedule',
            method: 'search_read',
            domain: this.domain,
            fields: ['id'],
        }).then(function (ids) {
            self.recordsPager = ids;
            self.active_ids = ids.slice(0, defaultPagerSize).map(i => i.id);
        });
    },

    /**
     * Make an rpc to get the state and afterwards set the company, the
     * manufacturing period, the groups in order to display/hide the differents
     * rows and the state that contains all the informations
     * about shipping schedules and their forecast for each period.
     *
     * @private
     * @return {Promise}
     */
    _getState: function () {
        var self = this;
        var domain = this.domain.concat([['id', 'in', this.active_ids]]);
        return this._rpc({
            model: 'web.sale.shipping.schedule',
            method: 'get_shipping_schedule_main_view_state',
            args: [domain],
        }).then(function (state) {
            self.companyId = state.company_id;
            self.manufacturingPeriods = state.dates;
            self.state = state.shipping_schedule_ids;
            self.manufacturingPeriod = state.manufacturing_period;
            return state;
        });
    },

    _getShippingScheduleState: function (shippingScheduleId) {
        var self = this;

        var shippingScheduleIds = [shippingScheduleId];

        return self._rpc({
            model: 'web.sale.shipping.schedule',
            method: 'get_shipping_schedule_view_state',
            args: [shippingScheduleIds],
        }).then(function (states) {
                for (var i = 0; i < states.length; i++) {
                    var state = states[i];
                    var index =  _.findIndex(self.state, {id: state.id});
                    if (index >= 0) {
                        self.state[index] = state;
                    }
                    else {
                        self.state.push(state);
                    }
                }
                return states;
        });
    },

    /**
     * reload all the shipping schedules inside content. Make an rpc to the
     * server in order to get the updated state and render it.
     *
     * @private
     * @return {Promise}
     */
    _reloadContent: function () {
        var self = this;
        return this._getState().then(function () {
            var $content = $(QWeb.render('shipping_schedule_main', {
                widget: {
                    manufacturingPeriods: self.manufacturingPeriods,
                    state: self.state,
                    formatFloat: self.formatFloat,
                }
            }));
            $('.o_shipping_schedule_main').replaceWith($content);
            self._update_cp_buttons();
        });
    },

    _resetSafetyInventory: function (dateIndex, shippingScheduleId) {
        var self = this;
        this.mutex.exec(function () {
            return self._rpc({
                model: 'web.sale.shipping.schedule',
                method: 'reset_safety_inventory_qty',
                args: [shippingScheduleId, dateIndex],
            }).then(function () {
                return self._renderShippingSchedule(shippingScheduleId);
            });
        });
    },

    _resetForecastSaleQty: function (dateIndex, shippingScheduleId) {
        var self = this;
        this.mutex.exec(function () {
            return self._rpc({
                model: 'web.sale.shipping.schedule',
                method: 'reset_forecast_sale_qty',
                args: [shippingScheduleId, dateIndex],
            }).then(function () {
                return self._renderShippingSchedule(shippingScheduleId);
            });
        });
    },

    _resetArrivingQtyApply: function (dateIndex, shippingScheduleId) {
        var self = this;
        this.mutex.exec(function () {
            return self._rpc({
                model: 'web.sale.shipping.schedule',
                method: 'reset_arriving_qty_apply',
                args: [shippingScheduleId, dateIndex],
            }).then(function () {
                return self._renderShippingSchedule(shippingScheduleId);
            });
        });
    },

    _resetArrivingQtyVerify: function (dateIndex, shippingScheduleId) {
        var self = this;
        this.mutex.exec(function () {
            return self._rpc({
                model: 'web.sale.shipping.schedule',
                method: 'reset_arriving_qty_verify',
                args: [shippingScheduleId, dateIndex],
            }).then(function () {
                return self._renderShippingSchedule(shippingScheduleId);
            });
        });
    },

    /**
     * Get the state with an rpc and render it with qweb. If the shipping
     * schedule is already present in the view replace it. Else append it at the
     * end of the table.
     *
     * @private
     * @param {Array} [shippingScheduleIds] mrp.shipping.schedule ids to render
     * @return {Promise}
     */
    _renderShippingSchedule: function (shippingScheduleId) {
        var self = this;
        return this._getShippingScheduleState(shippingScheduleId).then(function (states) {
            return self._renderState(states);
        });
    },

    _renderState: function (states) {
        for (var i = 0; i < states.length; i++) {
            var state = states[i];

            var $table = $(QWeb.render('shipping_schedule', {
                manufacturingPeriods: this.manufacturingPeriods,
                state: [state],
                formatFloat: this.formatFloat,
            }));
            var $tbody = $('.o_shipping_schedule_main_content[data-id='+ state.id +']');
            if ($tbody.length) {
                $tbody.replaceWith($table);
            } else {
                var $default_shop = false;
                if ('shop_id' in state) {
                    $default_shop = $('.o_shipping_schedule_main_content[data-shop_id='+ state.shop_id[0] +']');
                }
                if ($default_shop.length) {
                    $default_shop.last().append($table);
                } else {
                    $('.o_shipping_schedule_main_table').append($table);
                }
            }
        }
        this._update_cp_buttons();
        return Promise.resolve();
    },

    /**
     * Save the forecasted quantity and reload the current schedule in order
     * to update its To Replenish quantity and its safety stock (current and
     * future period). Also update the other schedules linked by BoM in order
     * to update them depending the indirect demand.
     *
     * @private
     * @param {Object} [shippingScheduleId] web.sale.shipping.schedule Id.
     * @param {Integer} [dateIndex] period to save (column number)
     * @param {Float} [forecastQty] The new forecasted quantity
     * @return {Promise}
     */
    _saveForecast: function (shippingScheduleId, dateIndex, forecastQty) {
        var self = this;
        this.mutex.exec(function () {
            return self._rpc({
                model: 'web.sale.shipping.schedule',
                method: 'set_forecast_sale_qty',
                args: [shippingScheduleId, dateIndex, forecastQty],
            }).then(function () {
                return self._renderShippingSchedule(shippingScheduleId).then(function () {
                    return self._focusNextInput(shippingScheduleId, dateIndex, 'arriving_qty_apply');
                });
            });
        });
    },

    _saveArrivingQtyApply: function (shippingScheduleId, dateIndex, arrivingQtyApply) {
        var self = this;
        this.mutex.exec(function () {
            return self._rpc({
                model: 'web.sale.shipping.schedule',
                method: 'set_arriving_qty_apply',
                args: [shippingScheduleId, dateIndex, arrivingQtyApply],
            }).then(function () {
                return self._renderShippingSchedule(shippingScheduleId).then(function () {
                    return self._focusNextInput(shippingScheduleId, dateIndex, 'safety_inventory');
                });
            });
        });
    },

    _saveArrivingQtyVerify: function (shippingScheduleId, dateIndex, arrivingQtyVerify) {
        var self = this;
        this.mutex.exec(function () {
            return self._rpc({
                model: 'web.sale.shipping.schedule',
                method: 'set_arriving_qty_verify',
                args: [shippingScheduleId, dateIndex, arrivingQtyVerify],
            }).then(function () {
                return self._renderShippingSchedule(shippingScheduleId).then(function () {
                    return self._focusNextInput(shippingScheduleId, dateIndex, 'safety_inventory');
                });
            });
        });
    },

    /**
     * Save the safety inventory quantity
     * to update it's safety stock and quantity in future period. Also mark
     * the cell with a blue background in order to show that it was manually
     * updated.
     *
     * @private
     * @param {Object} [shippingScheduleId] mrp.shipping.schedule Id.
     * @param {Integer} [dateIndex] period to save (column number)
     * @param {Float} [replenishQty] The new quantity To Replenish
     * @return {Promise}
     */
    _saveSafetyInventory: function (shippingScheduleId, dateIndex, safetyInventoryQty) {
        var self = this;
        this.mutex.exec(function () {
            return self._rpc({
                model: 'web.sale.shipping.schedule',
                method: 'set_safety_inventory_qty',
                args: [shippingScheduleId, dateIndex, safetyInventoryQty],
            }).then(function () {
                return self._renderShippingSchedule(shippingScheduleId).then(function () {
                    return self._focusNextInput(shippingScheduleId, dateIndex, 'sale_forecast');
                });
            }, function () {
                // Get the state with shippingScheduleId as id
                return self._backToState(shippingScheduleId);
            });
        });
    },

    _update_cp_buttons: function () {
        var recordsLen = Object.keys(this.state).length;
        var $salesConfirmButton = this.$buttons.find('.o_shipping_schedule_main_sales_confirm');
        var $logisticsConfirmButton = this.$buttons.find('.o_shipping_schedule_main_logistics_confirm');
        var $replenishButton = this.$buttons.find('.o_shipping_schedule_main_replenish');
        var $cancelConfirmButton = this.$buttons.find('.o_shipping_schedule_main_cancel_confirm');

        if (recordsLen) {
            $salesConfirmButton.removeClass('o_hidden');
            $logisticsConfirmButton.removeClass('o_hidden');
            $replenishButton.removeClass('o_hidden');
            $cancelConfirmButton.removeClass('o_hidden');
            this.el.querySelector('.o_shipping_schedule_main_table').classList.remove('d-none');
        } else {
            $salesConfirmButton.addClass('o_hidden');
            $logisticsConfirmButton.addClass('o_hidden');
            $replenishButton.addClass('o_hidden');
            $cancelConfirmButton.addClass('o_hidden');
            this.el.querySelector('.o_shipping_schedule_main_table').classList.add('d-none');
        }
        var toSalesConfirm = _.filter(_.flatten(_.values(this.state)), function (shipping_schedule) {
            if (shipping_schedule.state == 'draft') {
                return true;
            } else {
                return false;
            }
        });
        if (toSalesConfirm.length) {
            $salesConfirmButton.removeClass('o_hidden');
        } else {
            $salesConfirmButton.addClass('o_hidden');
        }

        var toLogisticsConfirm = _.filter(_.flatten(_.values(this.state)), function (shipping_schedule) {
            if (shipping_schedule.state == 'sales_confirmed' && shipping_schedule.is_web_sale_manager) {
                return true;
            } else {
                return false;
            }
        });
        if (toLogisticsConfirm.length) {
            $logisticsConfirmButton.removeClass('o_hidden');
        } else {
            $logisticsConfirmButton.addClass('o_hidden');
        }

        var toReplenish = _.filter(_.flatten(_.values(this.state)), function (shipping_schedule) {
            if (shipping_schedule.state == 'logistics_confirmed' && shipping_schedule.is_web_sale_manager) {
                return true;
            } else {
                return false;
            }
        });
        if (toReplenish.length) {
            $replenishButton.removeClass('o_hidden');
        } else {
            $replenishButton.addClass('o_hidden');
        }

        var toCancelConfirm = _.filter(_.flatten(_.values(this.state)), function (shipping_schedule) {
            if (['sales_confirmed','logistics_confirmed','done'].includes(shipping_schedule.state)) {
                return true;
            } else {
                return false;
            }
        });
        if (toCancelConfirm.length) {
            $cancelConfirmButton.removeClass('o_hidden');
        } else {
            $cancelConfirmButton.addClass('o_hidden');
        }
    },

    //--------------------------------------------------------------------------
    // Handlers
    //--------------------------------------------------------------------------

    /**
     * Handles the change on a forecast cell.
     *
     * @private
     * @param {jQuery.Event} ev
     */
    _onChangeForecast: function (ev) {
        ev.stopPropagation();
        var $target = $(ev.target);
        var dateIndex = $target.data('date_index');
        var shippingScheduleId = $target.closest('.o_shipping_schedule_main_content').data('id');
        var forecastQty = parseFloat($target.val());
        if (isNaN(forecastQty)){
            this._backToState(shippingScheduleId);
        } else {
            this._saveForecast(shippingScheduleId, dateIndex, forecastQty);
        }
    },

    /**
     * Handles the safety inventory change on a forecast cell.
     *
     * @private
     * @param {jQuery.Event} ev
     */
    _onChangeSafetyInventory: function (ev) {
        ev.stopPropagation();
        var $target = $(ev.target);
        var dateIndex = $target.data('date_index');
        var shippingScheduleId= $target.closest('.o_shipping_schedule_main_content').data('id');
        var safetyInventory = parseFloat($target.val());
        if (isNaN(safetyInventory)){
            this._backToState(shippingScheduleId);
        } else {
            this._saveSafetyInventory(shippingScheduleId, dateIndex, safetyInventory);
        }
    },

    _onChangeArrivingQtyApply: function (ev) {
        ev.stopPropagation();
        var $target = $(ev.target);
        var dateIndex = $target.data('date_index');
        var shippingScheduleId= $target.closest('.o_shipping_schedule_main_content').data('id');
        var arrivingQtyApply = parseFloat($target.val());
        if (isNaN(arrivingQtyApply)){
            this._backToState(shippingScheduleId);
        } else {
            this._saveArrivingQtyApply(shippingScheduleId, dateIndex, arrivingQtyApply);
        }
    },

    _onChangeArrivingQtyVerify: function (ev) {
        ev.stopPropagation();
        var $target = $(ev.target);
        var dateIndex = $target.data('date_index');
        var shippingScheduleId= $target.closest('.o_shipping_schedule_main_content').data('id');
        var arrivingQtyVerify = parseFloat($target.val());
        if (isNaN(arrivingQtyVerify)){
            this._backToState(shippingScheduleId);
        } else {
            this._saveArrivingQtyVerify(shippingScheduleId, dateIndex, arrivingQtyVerify);
        }
    },

    _onClickSafetyInventoryAutoMode: function (ev) {
        ev.stopPropagation();
        var $target = $(ev.target);
        var dateIndex = $target.data('date_index');
        var shippingScheduleId = $target.closest('.o_shipping_schedule_main_content').data('id');
        this._resetSafetyInventory(dateIndex, shippingScheduleId);
    },

    _onClickForecastSaleQtyAutoMode: function (ev) {
        ev.stopPropagation();
        var $target = $(ev.target);
        var dateIndex = $target.data('date_index');
        var shippingScheduleId = $target.closest('.o_shipping_schedule_main_content').data('id');
        this._resetForecastSaleQty(dateIndex, shippingScheduleId);
    },

    _onClickArrivingQtyApplyAutoMode: function (ev) {
        ev.stopPropagation();
        var $target = $(ev.target);
        var dateIndex = $target.data('date_index');
        var shippingScheduleId = $target.closest('.o_shipping_schedule_main_content').data('id');
        this._resetArrivingQtyApply(dateIndex, shippingScheduleId);
    },

    _onClickArrivingQtyVerifyAutoMode: function (ev) {
        ev.stopPropagation();
        var $target = $(ev.target);
        var dateIndex = $target.data('date_index');
        var shippingScheduleId = $target.closest('.o_shipping_schedule_main_content').data('id');
        this._resetArrivingQtyVerify(dateIndex, shippingScheduleId);
    },

    /**
     * Handles the click on product name. It will open the product form view
     *
     * @private
     * @param {MouseEvent} ev
     */
    _onClickRecordLink: function (ev) {
        ev.preventDefault();
        return this.do_action({
            type: 'ir.actions.act_window',
            res_model: $(ev.currentTarget).data('model'),
            res_id: $(ev.currentTarget).data('res-id'),
            views: [[false, 'form']],
            target: 'current'
        });
    },

    /**
     * Handles the click on replenish button. It will call action_replenish with
     * all the Ids present in the view.
     *
     * @private
     * @param {MouseEvent} ev
     */
    _onClickReplenish: function (ev) {
        ev.stopPropagation();
        var shippingScheduleId = [];
        var $tbody = $(ev.target).closest('.o_shipping_schedule_main_content');
        if ($tbody.length) {
            shippingScheduleId = [$tbody.data('id')];
        }
        this._actionReplenish(shippingScheduleId);
    },

    _onClickSalesConfirm: function (ev) {
        ev.stopPropagation();
        var shippingScheduleId = [];
        var $tbody = $(ev.target).closest('.o_shipping_schedule_main_content');
        if ($tbody.length) {
            shippingScheduleId = [$tbody.data('id')];
        }
        this._actionSalesConfirm(shippingScheduleId);
    },

    _onClickLogisticsConfirm: function (ev) {
        ev.stopPropagation();
        var shippingScheduleId = [];
        var $tbody = $(ev.target).closest('.o_shipping_schedule_main_content');
        if ($tbody.length) {
            shippingScheduleId = [$tbody.data('id')];
        }
        this._actionLogisticsConfirm(shippingScheduleId);
    },

    _onClickCancelConfirm: function (ev) {
        ev.stopPropagation();
        var shippingScheduleId = [];
        var $tbody = $(ev.target).closest('.o_shipping_schedule_main_content');
        if ($tbody.length) {
            shippingScheduleId = [$tbody.data('id')];
        }
        this._actionCancelConfirm(shippingScheduleId);
    },

    _onFocusInputControl: function (ev) {
        ev.preventDefault();
        $(ev.target).select();
    },

    _onMouseOverReplenish: function (ev) {
        ev.stopPropagation();
        var table = $(ev.target).closest('tbody');
        var replenishClass = '.o_shipping_schedule_forced_replenish';
        if (! table.length) {
            table = $('tr');
            replenishClass = '.o_shipping_schedule_to_replenish';
        }
        table.find(replenishClass).addClass('o_shipping_schedule_hover');
    },

    _onMouseOutReplenish: function (ev) {
        ev.stopPropagation();
        var table = $(ev.target).closest('tbody');
        if (! table.length) {
            table = $('tr');
        }
        table.find('.o_shipping_schedule_hover').removeClass('o_shipping_schedule_hover');
    },

    _onPagerChanged: function (ev) {
        let { currentMinimum, limit } = ev.data;
        this.pager.update({ currentMinimum, limit });
        currentMinimum = currentMinimum - 1;
        this.active_ids = this.recordsPager.slice(currentMinimum, currentMinimum + limit).map(i => i.id);
        this._reloadContent();
    },

    /**
     * Handles the change on the search bar. Save the domain and reload the
     * content with the new domain.
     *
     * @private
     * @param {Object} searchQuery
     */
    _onSearch: async function (searchQuery) {
        this.domain = searchQuery.domain;
        this.$pager.remove();
        this.pager.destroy();
        await this._getRecordIds();
        await this.renderPager();
        await this._reloadContent();
        await this.updateControlPanel();
    },
});

core.action_registry.add('shipping_schedule_client_action', ClientAction);

return ClientAction;

});
