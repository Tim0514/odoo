odoo.define('eshow_ext.widgets', function (require) {
    "use strict";

    const AbstractField = require('web.AbstractFieldOwl');
    const { _lt } = require('web.translation');
    const registry = require('web.field_registry_owl');
    const field_utils = require('web.field_utils');

    class FieldBooleanBadge extends AbstractField {
        _getClassFromDecoration(decoration) {
            return `bg-${decoration.split('-')[1]}-light`;
        }
    }
    FieldBooleanBadge.description = _lt("Badge");
    FieldBooleanBadge.supportedFieldTypes = ['boolean'];
    FieldBooleanBadge.template = 'eshow_ext.FieldBooleanBadge';

    registry
        .add('boolean_badge', FieldBooleanBadge)

    return {
        FieldBooleanBadge,
    };
});