odoo.define('product.ProductListView', function (require) {
"use strict";

var ListView = require('web.ListView');
var ProductListController = require('product.ProductListController');
var viewRegistry = require('web.view_registry');


var ProductListView = ListView.extend({
    config: _.extend({}, ListView.prototype.config, {
        Controller: ProductListController,
    }),
});

viewRegistry.add('product.product_list', ProductListView);

return ProductListView;

});
