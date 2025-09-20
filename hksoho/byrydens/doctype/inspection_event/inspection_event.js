frappe.ui.form.on('Inspection Event', {
    refresh: function(frm) {
        // 隐藏 po_items 表的「Add」按钮
        frm.fields_dict.po_items.grid.cannot_add_rows = true;
        frm.fields_dict.po_items.grid.wrapper.find('.grid-add-row').hide();

        // 添加按钮以打开自定义对话框
        frm.add_custom_button(__('Add PO Items'), function() {
            // 获取状态为 "Ready to QC" 的采购订单
            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Purchase Order',
                    filters: {
                        workflow_state: 'Ready to QC'
                    },
                    fields: ['name']
                },
                callback: function(r) {
                    if (r.message) {
                        let po_options = r.message.map(po => po.name);
                        if (po_options.length === 0) {
                            frappe.msgprint(__('No Purchase Orders found with status "Ready to QC".'));
                            return;
                        }

                        // 创建对话框
                        let d = new frappe.ui.Dialog({
                            title: __('Select PO Items'),
                            fields: [
                                {
                                    fieldtype: 'Select',
                                    fieldname: 'po_select',
                                    label: __('选择采购订单'),
                                    options: po_options,
                                    change: function() {
                                        refreshTable(d);
                                    }
                                },
                                {
                                    fieldtype: 'HTML',
                                    fieldname: 'items_table'
                                }
                            ],
                            primary_action_label: __('Add Selected Items'),
                            primary_action: function() {
                                let selected_items = [];
                                $('input[name="item_select"]:checked').each(function() {
                                    selected_items.push($(this).val());
                                });

                                if (selected_items.length === 0) {
                                    frappe.msgprint(__('請至少選擇一個項目'));
                                    return;
                                }

                                console.log("Adding items to Inspection Event:", selected_items, "Type:", typeof selected_items); // 調試日誌
                                // 調用 Python 函數將項目添加到 po_items 表
                                frappe.call({
                                    method: 'hksoho.byrydens.inspection_api.add_po_items_to_inspection_event',
                                    args: {
                                        inspection_event_name: frm.doc.name,
                                        selected_items: selected_items // 直接傳遞陣列
                                    },
                                    callback: function(r) {
                                        console.log("Add items response:", r); // 調試日誌
                                        if (r.message && r.message.status === "success") {
                                            frm.reload_doc();
                                            d.hide();
                                            frappe.msgprint({
                                                title: __('Success'),
                                                message: r.message.message,
                                                indicator: 'green'
                                            });
                                        } else if (r.message && r.message.status === "warning") {
                                            d.hide();
                                            frappe.msgprint({
                                                title: __('Warning'),
                                                message: r.message.message,
                                                indicator: 'orange'
                                            });
                                        }
                                    },
                                    error: function(r) {
                                        console.error("Error adding PO items:", r); // 調試日誌
                                        // 處理權限錯誤
                                        let error_message = r.exc ? (JSON.parse(r.exc)[0] || r.exc) : __('未知錯誤');
                                        if (error_message.includes('You do not have enough permissions')) {
                                            frappe.msgprint({
                                                title: __('Not permitted'),
                                                message: __('You do not have enough permissions to access this resource. Please contact your manager to get access.'),
                                                indicator: 'red'
                                            });
                                        } else if (error_message.includes('無有效的項目被選擇')) {
                                            frappe.msgprint({
                                                title: __('Error'),
                                                message: __('無有效的項目被選擇。'),
                                                indicator: 'red'
                                            });
                                        } else if (error_message.includes('無效的項目選擇格式')) {
                                            frappe.msgprint({
                                                title: __('Error'),
                                                message: __('無效的項目選擇格式。'),
                                                indicator: 'red'
                                            });
                                        } else {
                                            frappe.msgprint({
                                                title: __('Error'),
                                                message: __('無法添加項目，請稍後重試。錯誤：') + error_message,
                                                indicator: 'red'
                                            });
                                        }
                                    }
                                });
                            }
                        });

                        // 定义刷新表格的函数
                        function refreshTable(dialog) {
                            let po_name = dialog.get_value('po_select');
                            if (!po_name) {
                                dialog.fields_dict.items_table.$wrapper.empty();
                                return;
                            }

                            frappe.call({
                                method: 'hksoho.byrydens.inspection_api.get_po_items_qcstatus',
                                args: {
                                    po_name: po_name
                                },
                                callback: function(r) {
                                    let $container = dialog.fields_dict.items_table.$wrapper;
                                    $container.empty(); // 清空容器

                                    if (r.message && Array.isArray(r.message)) {
                                        let table = $(`
                                            <table class="table table-bordered">
                                                <thead>
                                                    <tr>
                                                        <th>Select</th>
                                                        <th>Line</th>
                                                        <th>Requested QTY</th>
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
                                                    <td>${item.requested_qty || 0}</td>
                                                    <td>${item.article_number || ''}</td>
                                                    <td>${item.article_name || ''}</td>
                                                    <td>${item.confirmed_qty || 0}</td>
                                                </tr>
                                            `);
                                        });

                                        $container.append(table);
                                    } else {
                                        $container.html('<p>无项目可显示</p>');
                                    }
                                }
                            });
                        }

                        // 在对话框显示时初始化内容
                        d.show();
                        // 初始清空表格区域
                        d.fields_dict.items_table.$wrapper.empty();
                    }
                }
            });
        });
    }
});