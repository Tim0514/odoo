odoo.define('web_sale.WebShopListView', function (require) {
"use strict";

var ListView = require('web.ListView');
var WebShopListController = require('web_sale.WebShopListController');
var viewRegistry = require('web.view_registry');


var WebShopListView = ListView.extend({
    config: _.extend({}, ListView.prototype.config, {
        Controller: WebShopListController,
    }),
});

viewRegistry.add('web_sale.web_shop_list', WebShopListView);

return WebShopListView;

});
