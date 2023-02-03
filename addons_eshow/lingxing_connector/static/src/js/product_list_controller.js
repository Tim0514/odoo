odoo.define('product.ProductListController', function (require) {
"use strict";

var ListController = require('web.ListController');
var Dialog = require('web.Dialog');

var ProductListController = ListController.extend({
    buttons_template: 'product.product.buttons',

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
        this.$buttons.on('click', '.o_button_export_products', this._onOpenWizard.bind(this));
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
                model: 'product.product',   //需要调用方法的模型
                method: 'action_export_products',  //需要调用的方法
                args: [this.selectedRecords],  //传参
            }).then(function(res){
                location.reload()  //更新后刷新页面
            });
        };

        let dialog_content = "<div>This will start exporting local product data to Lingxing Server, you may view result in connector's log book later.</div>"

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
    },
});

return ProductListController;

});
