frappe.ui.form.on('Inspection Event', {
    refresh: function(frm) {
        control_po_items_and_buttons(frm);
    },
    starts_on: function(frm) { control_po_items_and_buttons(frm); },
    ends_on: function(frm) { control_po_items_and_buttons(frm); },
    supplier: function(frm) { control_po_items_and_buttons(frm); },
    inspector: function(frm) { control_po_items_and_buttons(frm); }
});

function control_po_items_and_buttons(frm) {
    const is_new = frm.doc.__islocal || !frm.doc.name;

    if (is_new) {
        frm.set_df_property('po_items', 'hidden', 1);
        if (frm.fields_dict.po_items?.grid) {
            frm.fields_dict.po_items.grid.cannot_add_rows = true;
            frm.fields_dict.po_items.grid.wrapper.find('.grid-add-row').hide();
        }
        if (!frm._po_hint_shown) {
            frm.dashboard.add_comment(
                __('Please save the Inspection Event first to add PO items.'),
                'blue',
                true
            );
            frm._po_hint_shown = true;
        }
        frm.remove_custom_button(__('Add PO Items'));
        frm.remove_custom_button(__('Send Invitation'));

    } else {
        frm.set_df_property('po_items', 'hidden', 0);
        if (frm.fields_dict.po_items?.grid) {
            frm.fields_dict.po_items.grid.cannot_add_rows = true;
            frm.fields_dict.po_items.grid.wrapper.find('.grid-add-row').hide();
        }
        frm.dashboard.clear_comment(__('Please save the Inspection Event first to add PO items.'));
        delete frm._po_hint_shown;

        // Add PO Items 按鈕
        if (!frm.page.btn_primary || frm.page.btn_primary.text() !== __('Add PO Items')) {
            frm.add_custom_button(__('Add PO Items'), function() {
                open_po_items_dialog(frm);
            }, null, { primary: true });
            frm.change_custom_button_type(__('Add PO Items'), null, 'primary');
        }

        // 新增 Send Invitation 按鈕（放在旁邊）
        frm.add_custom_button(__('Send Invitation'), function() {
            send_invitation_email(frm);
        }, null, { primary: true });
        frm.change_custom_button_type(__('Send Invitation'), null, 'primary');
    }
}
// === 發送邀請函數 ===
function send_invitation_email(frm) {
    frappe.call({
        method: 'hksoho.byrydens.inspection_api.send_inspection_invitation',
        args: { inspection_event_name: frm.doc.name },
        callback: function(r) {
            if (r.message.status === "success") {
                frappe.msgprint({
                    title: __('成功'),
                    message: r.message.message,
                    indicator: 'green'
                });
            }
        },
        error: function(err) {
            frappe.msgprint({
                title: __('錯誤'),
                message: __('無法發送邀請，請檢查 Inspector email。'),
                indicator: 'red'
            });
        }
    });
}


// =======================================
// Dialog: Select PO → Select Items → Add via API
// =======================================
function open_po_items_dialog(frm) {
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Purchase Order',
            filters: { workflow_state: 'Ready to QC' },
            fields: ['name'],
            limit_page_length: 200,
            ignore_permissions: true   
        },
        callback: function(r) {
            if (!r.message || r.message.length === 0) {
                frappe.msgprint(__('No Purchase Orders found with status "Ready to QC".'));
                return;
            }

            let po_options = r.message.map(po => po.name);

            let d = new frappe.ui.Dialog({
                title: __('Select PO Items'),
                fields: [
                    {
                        label: __('Select Purchase Order'),
                        fieldname: 'po_select',
                        fieldtype: 'Select',
                        options: po_options,
                        reqd: 1,
                        change: function() { refresh_po_items_table(d); }
                    },
                    {
                        fieldname: 'items_table',
                        fieldtype: 'HTML'
                    }
                ],
                primary_action_label: __('Add Selected Items'),
                primary_action: function() {
                    let selected_items = [];
                    d.$wrapper.find('input[name="item_select"]:checked').each(function() {
                        selected_items.push($(this).val());
                    });

                    if (selected_items.length === 0) {
                        frappe.msgprint(__('Please select at least one item.'));
                        return;
                    }

                    frappe.call({
                        method: 'hksoho.byrydens.inspection_api.add_po_items_to_inspection_event',
                        args: {
                            inspection_event_name: frm.doc.name,
                            selected_items: selected_items
                        },
                        callback: function(resp) {
                            if (resp.message?.status === "success") {
                                frm.reload_doc();
                                d.hide();
                                frappe.show_alert({
                                    message: resp.message.message,
                                    indicator: 'green'
                                }, 5);
                            } else if (resp.message?.status === "warning") {
                                d.hide();
                                frappe.msgprint({
                                    title: __('Warning'),
                                    message: resp.message.message,
                                    indicator: 'orange'
                                });
                            }
                        },
                        error: function(err) {
                            let msg = __('Failed to add items');
                            try {
                                let exc = JSON.parse(err.message || err.exc || '{}');
                                msg += ': ' + (exc[0]?.message || exc.message || err.message);
                            } catch (e) {
                                msg += '.';
                            }
                            frappe.msgprint({ title: __('Error'), message: msg, indicator: 'red' });
                        }
                    });
                }
            });

            d.show();
            d.fields_dict.items_table.$wrapper.html('<p>Please select a Purchase Order first.</p>');
        },
        error: function() {
            frappe.msgprint(__('Failed to load Purchase Orders.'));
        }
    });
}

function refresh_po_items_table(dialog) {
    let po_name = dialog.get_value('po_select');
    if (!po_name) {
        dialog.fields_dict.items_table.$wrapper.html('<p>Please select a Purchase Order.</p>');
        return;
    }

    frappe.call({
        method: 'hksoho.byrydens.inspection_api.get_po_items_qcstatus',
        args: { po_name: po_name },
        callback: function(r) {
            let $wrapper = dialog.fields_dict.items_table.$wrapper.empty();

            if (!r.message || !Array.isArray(r.message) || r.message.length === 0) {
                $wrapper.html('<p>No items available for inspection.</p>');
                return;
            }

            let table = $(`
                <table class="table table-bordered table-sm">
                    <thead class="thead-light">
                        <tr>
                            <th width="50"><input type="checkbox" id="select_all"></th>
                            <th>Line</th>
                            <th>Article #</th>
                            <th>Article Name</th>
                            <th>Confirmed QTY</th>
                        </tr>
                    </thead>
                    <tbody></tbody>
                </table>
            `);

            let tbody = table.find('tbody');
            r.message.forEach(item => {
                tbody.append(`
                    <tr>
                        <td><input type="checkbox" name="item_select" value="${item.name}"></td>
                        <td>${item.line || ''}</td>
                        <td>${item.article_number || ''}</td>
                        <td>${item.article_name || ''}</td>
                        <td>${item.confirmed_qty || 0}</td>
                    </tr>
                `);
            });

            table.find('#select_all').on('change', function() {
                table.find('input[name="item_select"]').prop('checked', this.checked);
            });

            $wrapper.append(table);
        },
        error: function() {
            dialog.fields_dict.items_table.$wrapper.html('<p>Failed to load items.</p>');
        }
    });
}