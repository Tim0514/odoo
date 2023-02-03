odoo.define('web_sale.WebShopListController', function (require) {
"use strict";

var ListController = require('web.ListController');
var Dialog = require('web.Dialog');

var WebShopListController = ListController.extend({
    buttons_template: 'web_sale.web_shop.buttons',

    // -------------------------------------------------------------------------
    // Public
    // -------------------------------------------------------------------------

    init: function (parent, model, renderer, params) {
        this.context = renderer.state.getContext();
        return this._super.apply(this, arguments);
    },

    /**
     * @override
     */
    renderButtons: function ($node) {
        this._super.apply(this, arguments);
        // if (this.context.no_at_date) {
        //     this.$buttons.find('button.o_button_at_date').hide();
        // }
        this.$buttons.on('click', '.o_button_sync_shops', this._onOpenWizard.bind(this));
    },

    // -------------------------------------------------------------------------
    // Handlers
    // -------------------------------------------------------------------------

    /**
     * Handler called when the user clicked on the 'Inventory at Date' button.
     * Opens wizard to display, at choice, the products inventory or a computed
     * inventory at a given date.
     */
    _onOpenWizard: function () {
        var state = this.model.get(this.handle, {raw: true});
        var stateContext = state.getContext();
        var context = {
            active_model: this.modelName,
        };

        var affirm = function () {
            // dialog.close();
            this._rpc({
                model: 'web.sale.shop',   //需要调用方法的模型
                method: 'action_import_web_shops',  //需要调用的方法
                args: [this.selectedRecords],  //传参
            }).then(function(res){
                location.reload()  //更新后刷新页面
            });
        };

        let dialog_content = "<div>This will start importing shop data from Lingxing Server, you may view result in connector's log book later.</div>"

        var dialog = new Dialog(this, {
            title: 'Notice',
            size: 'medium',
            // size: 'small',
            // size: 'large',
            $content: dialog_content,
            buttons: [{
                text: 'Confirm',
                classes: 'btn-primary',
                close: true,
                click: affirm
            },
            {
                text: 'Cancel',
                close: true
            }]
        }).open();

        // if (stateContext.default_product_id) {
        //     context.product_id = stateContext.default_product_id;
        // } else if (stateContext.product_tmpl_id) {
        //     context.product_tmpl_id = stateContext.product_tmpl_id;
        // }
        // this.do_action({
        //     res_model: 'stock.quantity.history',
        //     views: [[false, 'form']],
        //     target: 'new',
        //     type: 'ir.actions.act_window',
        //     context: context,
        // });

        //     return this._rpc({
        //         model: 'web.sale.shop',   //需要调用方法的模型
        //         method: 'do_import_shops',  //需要调用的方法
        //         args: [this.selectedRecords],  //传参
        //     }).then(function(res){
        //         location.reload()  //更新后刷新页面
        // });

    },
});

return WebShopListController;

});
