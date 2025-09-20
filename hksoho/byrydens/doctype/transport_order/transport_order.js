frappe.ui.form.on('Transport Order', {
    refresh: function(frm) {
        // 隱藏 items 表的「Add」按鈕
        frm.fields_dict.items.grid.cannot_add_rows = true;
        frm.fields_dict.items.grid.wrapper.find('.grid-add-row').hide();

        // 添加自訂按鈕「Add Item」
        frm.add_custom_button(__('Add Item'), function() {
            // 獲取所有有效的 Purchase Order
            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Purchase Order',
                    filters: {
                        // docstatus: 1 // 僅顯示已提交的 PO，根據需要可取消註釋
                    },
                    fields: ['name'],
                    limit_page_length: 100
                },
                callback: function(r) {
                    if (r.message && r.message.length > 0) {
                        let po_options = r.message.map(po => po.name);

                        // 創建對話框
                        let d = new frappe.ui.Dialog({
                            title: __('Select Purchase Order Items'),
                            fields: [
                                {
                                    label: __('選擇採購訂單'),
                                    fieldname: 'po_select',
                                    fieldtype: 'Select',
                                    options: po_options,
                                    reqd: 1,
                                    change: function() {
                                        refreshTable(d);
                                    }
                                },
                                {
                                    label: __('項目列表'),
                                    fieldname: 'items_table',
                                    fieldtype: 'HTML'
                                }
                            ],
                            primary_action_label: __('Add Selected Items'),
                            primary_action: function() {
                                let selected_items = [];
                                let po_name = d.get_value('po_select');
                                $(d.$wrapper).find('input[name="item_select"]:checked').each(function() {
                                    selected_items.push({
                                        name: $(this).val(),
                                        line: $(this).data('line'),
                                        article_number: $(this).data('article-number'),
                                        article_name: $(this).data('article-name'),
                                        qty: parseFloat($(this).data('qty') || 0),
                                        ctns: parseInt($(this).data('ctns') || 0),
                                        cbm: parseFloat($(this).data('cbm') || 0),
                                        gross_kg: parseFloat($(this).data('gross-kg') || 0),
                                        unit_price: parseFloat($(this).data('unit-price') || 0)
                                    });
                                });

                                if (selected_items.length === 0) {
                                    frappe.msgprint({
                                        title: __('錯誤'),
                                        message: __('請至少選擇一個項目！'),
                                        indicator: 'red'
                                    });
                                    return;
                                }

                                // 檢查是否有重複的 po_line
                                let existing_po_lines = frm.doc.items ? frm.doc.items.map(item => item.po_line) : [];
                                let duplicates = selected_items.filter(item => existing_po_lines.includes(item.name));
                                if (duplicates.length > 0) {
                                    frappe.msgprint({
                                        title: __('錯誤'),
                                        message: __('以下項目已存在於 Transport Order Line 中：') + duplicates.map(d => d.line).join(', '),
                                        indicator: 'red'
                                    });
                                    return;
                                }

                                // 添加選中的項目到 Transport Order Line 子表格
                                selected_items.forEach(item => {
                                    let row = frm.add_child('items');
                                    row.po_number = po_name;
                                    row.po_line = item.name;
                                    row.article_number = item.article_number;
                                    row.article_name = item.article_name;
                                    row.qty = item.qty;
                                    row.ctns = item.ctns;
                                    row.cbm = item.cbm;
                                    row.gross_kg = item.gross_kg;
                                    row.unit_price = item.unit_price;
                                    row.value = item.qty * item.unit_price;
                                });

                                // 刷新子表格並更新總值
                                frm.refresh_field('items');
                                calculate_total(frm);
                                d.hide(); // 確保對話框關閉
                                frappe.msgprint({
                                    title: __('成功'),
                                    message: __('已成功添加選中的項目！'),
                                    indicator: 'green'
                                });
                            }
                        });

                        // 定義刷新表格的函數
                        function refreshTable(dialog) {
                            let po_name = dialog.get_value('po_select');
                            if (!po_name) {
                                dialog.fields_dict.items_table.$wrapper.empty();
                                return;
                            }

                            frappe.call({
                                method: 'hksoho.byrydens.transport_order_api.get_po_items',
                                args: {
                                    po_name: po_name
                                },
                                callback: function(r) {
                                    let $container = dialog.fields_dict.items_table.$wrapper;
                                    $container.empty(); // 清空容器

                                    if (r.message && Array.isArray(r.message) && r.message.length > 0) {
                                        let table = $(`
                                            <table class="table table-bordered">
                                                <thead>
                                                    <tr>
                                                        <th style="width: 10%;">${__('選擇')}</th>
                                                        <th style="width: 15%;">${__('Line')}</th>
                                                        <th style="width: 15%;">${__('Article #')}</th>
                                                        <th style="width: 20%;">${__('Article Name')}</th>
                                                        <th style="width: 10%;">${__('QTY')}</th>
                                                        <th style="width: 10%;">${__('Ctns')}</th>
                                                        <th style="width: 10%;">${__('CBM')}</th>
                                                        <th style="width: 10%;">${__('Gross Kg')}</th>
                                                        <th style="width: 10%;">${__('Unit Price')}</th>
                                                    </tr>
                                                </thead>
                                                <tbody></tbody>
                                            </table>
                                        `);

                                        let tbody = table.find('tbody');
                                        r.message.forEach(item => {
                                            tbody.append(`
                                                <tr>
                                                    <td><input type="checkbox" name="item_select" value="${item.name}" 
                                                        data-line="${item.line || ''}" 
                                                        data-article-number="${item.article_number || ''}" 
                                                        data-article-name="${item.article_name || ''}" 
                                                        data-qty="${item.confirmed_qty || 0}" 
                                                        data-ctns="${item.ctns_on_pallet || 0}" 
                                                        data-cbm="${item.carton_cbm || 0}" 
                                                        data-gross-kg="${item.carton_gross_kg || 0}" 
                                                        data-unit-price="${item.unit_price || 0}"></td>
                                                    <td>${item.line || ''}</td>
                                                    <td>${item.article_number || ''}</td>
                                                    <td>${item.article_name || ''}</td>
                                                    <td>${item.confirmed_qty || 0}</td>
                                                    <td>${item.ctns_on_pallet || 0}</td>
                                                    <td>${item.carton_cbm || 0}</td>
                                                    <td>${item.carton_gross_kg || 0}</td>
                                                    <td>${item.unit_price || 0}</td>
                                                </tr>
                                            `);
                                        });

                                        $container.append(table);
                                    } else {
                                        $container.html('<p>' + __('無項目可顯示') + '</p>');
                                    }
                                },
                                error: function(r) {
                                    console.error("Error fetching PO items:", r);
                                    let error_message = r.exc ? (JSON.parse(r.exc)[0] || r.exc) : __('未知錯誤');
                                    if (error_message.includes('You do not have enough permissions')) {
                                        frappe.msgprint({
                                            title: __('權限不足'),
                                            message: __('您沒有足夠的權限來訪問採購訂單項目。請聯繫您的管理員以獲取訪問權限。'),
                                            indicator: 'red'
                                        });
                                    } else {
                                        frappe.msgprint({
                                            title: __('錯誤'),
                                            message: __('無法獲取採購訂單項目，請稍後重試。錯誤：') + error_message,
                                            indicator: 'red'
                                        });
                                    }
                                }
                            });
                        }

                        // 顯示對話框並初始化內容
                        d.show();
                        d.fields_dict.items_table.$wrapper.empty();
                    } else {
                        frappe.msgprint({
                            title: __('無數據'),
                            message: __('未找到有效的採購訂單。'),
                            indicator: 'orange'
                        });
                    }
                },
                error: function(r) {
                    console.error("Error fetching POs:", r);
                    let error_message = r.exc ? (JSON.parse(r.exc)[0] || r.exc) : __('未知錯誤');
                    if (error_message.includes('You do not have enough permissions')) {
                        frappe.msgprint({
                            title: __('權限不足'),
                            message: __('您沒有足夠的權限來訪問採購訂單。請聯繫您的管理員以獲取訪問權限。'),
                            indicator: 'red'
                        });
                    } else {
                        frappe.msgprint({
                            title: __('錯誤'),
                            message: __('無法獲取採購訂單列表，請稍後重試。錯誤：') + error_message,
                            indicator: 'red'
                        });
                    }
                }
            });
        });

        // Add "(Select)" hyperlink next to the Vessel label
        let vessel_field = frm.get_field('vessel').$wrapper;
        vessel_field.find('.select-vessel-link').remove(); // Remove any existing hyperlink
        vessel_field.find('.control-label').append(`
            <a href="#" class="select-vessel-link" style="margin-left: 5px; font-size: 12px; color: #007bff; text-decoration: none;">(${__('Select')})</a>
        `);
        vessel_field.find('.select-vessel-link').on('click', function(e) {
            e.preventDefault();
            let selected_row = null;
            let dialog = new frappe.ui.Dialog({
                title: __('Select Vessel'),
                size: 'extra-large',
                fields: [
                    { fieldtype: 'HTML', fieldname: 'vessel_html' }
                ],
                primary_action_label: __('Add New'),
                primary_action: function() {
                    frappe.new_doc('Vessels Time Table', {}, function() {
                        dialog.hide();
                    });
                }
            });

            // Debounce function to delay filter and sort execution
            function debounce(func, wait) {
                let timeout;
                return function executedFunction(...args) {
                    const later = () => {
                        clearTimeout(timeout);
                        func(...args);
                    };
                    clearTimeout(timeout);
                    timeout = setTimeout(later, wait);
                };
            }

            function render_table(records, initial = false) {
                let html = `
                    <style>
                        table.vessel-table { width: 100%; border-collapse: collapse; font-size: 13px; border: 1px solid #e6e6e6; }
                        table.vessel-table th, table.vessel-table td {
                            border: 1px solid #e6e6e6; padding: 8px; text-align: left; white-space: nowrap;
                        }
                        table.vessel-table th { background: #f4f4f4; }
                        table.vessel-table tr.sel { background-color: #e6f3ff; }
                        table.vessel-table tr:hover { background-color: #f0f4f7; cursor: pointer; }
                        .vessel-table-container { max-height: 500px; overflow-y: auto; overflow-x: auto; }
                        .modal-dialog { width: 85vw !important; max-width: 1400px !important; }
                        .vessel-table input { width: calc(100% - 20px); box-sizing: border-box; padding: 5px; font-size: 12px; margin: 0; border: 1px solid #ccc; }
                        .filter-row th { padding: 5px; position: relative; }
                        .sort { cursor: pointer; }
                        .sort-asc::after { content: ' ↑'; }
                        .sort-desc::after { content: ' ↓'; }
                        .vessel-table tfoot { font-size: 12px; }
                        .vessel-table tfoot td { padding: 5px; }
                        .vessel-table tfoot a { color: #007bff; text-decoration: none; }
                        .vessel-table tfoot a:hover { text-decoration: underline; }
                        .eta-filter-container { display: flex; align-items: center; }
                        .eta-filter-container span { margin-right: 5px; font-size: 12px; }
                        .clear-filter { position: absolute; right: 5px; top: 50%; transform: translateY(-50%); cursor: pointer; font-size: 12px; color: #007bff; }
                        .clear-filter:hover { color: #0056b3; }
                    </style>
                    <div class="vessel-table-container">
                    <table class="vessel-table">
                        <thead>
                            <tr class="filter-row">
                                <th style="width: 150px;">
                                    <input type="text" id="vessel_filter" placeholder="Vessel" class="form-control" value="${dialog.fields_dict.vessel_html.$wrapper.find('#vessel_filter').val() || ''}">
                                    <span class="clear-filter" data-filter="vessel_filter">X</span>
                                </th>
                                <th style="width: 100px;">
                                    <input type="text" id="voyage_filter" placeholder="Voyage" class="form-control" value="${dialog.fields_dict.vessel_html.$wrapper.find('#voyage_filter').val() || ''}">
                                    <span class="clear-filter" data-filter="voyage_filter">X</span>
                                </th>
                                <th style="width: 120px;">
                                    <input type="text" id="loading_port_filter" placeholder="Load Port" class="form-control" value="${dialog.fields_dict.vessel_html.$wrapper.find('#loading_port_filter').val() || ''}">
                                    <span class="clear-filter" data-filter="loading_port_filter">X</span>
                                </th>
                                <th style="width: 120px;">
                                    <input type="text" id="destination_port_filter" placeholder="Dest Port" class="form-control" value="${dialog.fields_dict.vessel_html.$wrapper.find('#destination_port_filter').val() || ''}">
                                    <span class="clear-filter" data-filter="destination_port_filter">X</span>
                                </th>
                                <th style="width: 100px;"></th>
                                <th style="width: 100px;">
                                    <div class="eta-filter-container">
                                        <span>&gt;</span>
                                        <input type="date" id="eta_date_filter" placeholder="ETA >=" class="form-control" value="${dialog.fields_dict.vessel_html.$wrapper.find('#eta_date_filter').val() || ''}">
                                        <span class="clear-filter" data-filter="eta_date_filter">X</span>
                                    </div>
                                </th>
                            </tr>
                            <tr class="header-row">
                                <th style="width: 150px;" class="sort" data-sort="vessel">Vessel</th>
                                <th style="width: 100px;" class="sort" data-sort="voyage">Voyage</th>
                                <th style="width: 120px;" class="sort" data-sort="loading_port_loc_code">Load Port</th>
                                <th style="width: 120px;" class="sort" data-sort="destination_port_loc_code">Dest Port</th>
                                <th style="width: 100px;" class="sort" data-sort="etd_date">ETD Date</th>
                                <th style="width: 100px;" class="sort" data-sort="eta_date">ETA Date</th>
                            </tr>
                        </thead>
                        <tbody>
                `;
                records.forEach(row => {
                    html += `
                        <tr data-name="${row.name}">
                            <td>${row.vessel || ''}</td>
                            <td>${row.voyage || ''}</td>
                            <td>${row.loading_port_loc_code || ''}</td>
                            <td>${row.destination_port_loc_code || ''}</td>
                            <td>${row.etd_date || ''}</td>
                            <td>${row.eta_date || ''}</td>
                        </tr>
                    `;
                });
                html += `
                        </tbody>
                        <tfoot>
                            <tr class="footer">
                                <td colspan="6" style="padding: 5px;">
                                    <a href="#" onclick="frappe.new_doc('Vessels Time Table', {}, function() { dialog.hide(); });">(add new)</a> (${records.length} records)
                                </td>
                            </tr>
                        </tfoot>
                    </table>
                    </div>
                `;
                if (initial) {
                    dialog.fields_dict.vessel_html.$wrapper.html(html);
                    // Bind events only on initial render
                    const debounced_load_data = debounce(load_data, 300);
                    const debounced_sort_data = debounce(sort_data, 300);
                    dialog.fields_dict.vessel_html.$wrapper.find('#vessel_filter').on('input', debounced_load_data);
                    dialog.fields_dict.vessel_html.$wrapper.find('#voyage_filter').on('input', debounced_load_data);
                    dialog.fields_dict.vessel_html.$wrapper.find('#loading_port_filter').on('input', debounced_load_data);
                    dialog.fields_dict.vessel_html.$wrapper.find('#destination_port_filter').on('input', debounced_load_data);
                    dialog.fields_dict.vessel_html.$wrapper.find('#eta_date_filter').on('change', debounced_load_data);
                    dialog.fields_dict.vessel_html.$wrapper.find('.sort').on('click', function() {
                        let sort_field = $(this).data('sort');
                        let sort_order = $(this).hasClass('sort-asc') ? 'desc' : 'asc';
                        debounced_sort_data(sort_field, sort_order, records);
                    });
                    dialog.fields_dict.vessel_html.$wrapper.find('.clear-filter').on('click', function() {
                        let filter_id = $(this).data('filter');
                        dialog.fields_dict.vessel_html.$wrapper.find(`#${filter_id}`).val('').trigger('input');
                    });
                } else {
                    dialog.fields_dict.vessel_html.$wrapper.find('.vessel-table tbody').html($(html).find('tbody').html());
                    dialog.fields_dict.vessel_html.$wrapper.find('.vessel-table tfoot').html($(html).find('tfoot').html());
                }
                dialog.fields_dict.vessel_html.$wrapper.find('tbody tr').on('click', function() {
                    dialog.fields_dict.vessel_html.$wrapper.find('tr').removeClass('sel');
                    $(this).addClass('sel');
                    let name = $(this).data('name');
                    selected_row = records.find(r => r.name === name);
                    console.log('Selected vessel:', selected_row);
                    frm.set_value('vessel', selected_row.name);
                    frm.set_value('carrier', selected_row.carrier || '');
                    frm.set_value('voyage', selected_row.voyage || '');
                    frm.set_value('load_port', selected_row.loading_port_name || '');
                    frm.set_value('load_code', selected_row.loading_port_loc_code || '');
                    frm.set_value('dest_port', selected_row.destination_port_name || '');
                    frm.set_value('dest_code', selected_row.destination_port_loc_code || '');
                    frm.set_value('cfs_close', selected_row.cfs_close || '');
                    frm.set_value('etd_date', selected_row.etd_date || '');
                    frm.set_value('eta_date', selected_row.eta_date || '');
                    frappe.show_alert({ message: __('Selected Vessel: ') + selected_row.vessel, indicator: 'green' });
                    dialog.hide();
                });
            }

            function sort_data(sort_field, sort_order, records) {
                dialog.fields_dict.vessel_html.$wrapper.find('.sort').removeClass('sort-asc sort-desc');
                dialog.fields_dict.vessel_html.$wrapper.find(`.sort[data-sort="${sort_field}"]`).addClass(`sort-${sort_order}`);
                records.sort((a, b) => {
                    let val_a = a[sort_field] || '';
                    let val_b = b[sort_field] || '';
                    if (sort_field.includes('date')) {
                        val_a = val_a ? new Date(val_a) : new Date(0);
                        val_b = val_b ? new Date(val_b) : new Date(0);
                    }
                    if (sort_order === 'asc') {
                        return val_a > val_b ? 1 : -1;
                    } else {
                        return val_a < val_b ? 1 : -1;
                    }
                });
                render_table(records);
            }

            function load_data() {
                let filters = {};
                let vessel_filter = dialog.fields_dict.vessel_html.$wrapper.find('#vessel_filter').val();
                let voyage_filter = dialog.fields_dict.vessel_html.$wrapper.find('#voyage_filter').val();
                let loading_port_filter = dialog.fields_dict.vessel_html.$wrapper.find('#loading_port_filter').val();
                let destination_port_filter = dialog.fields_dict.vessel_html.$wrapper.find('#destination_port_filter').val();
                let eta_date_filter = dialog.fields_dict.vessel_html.$wrapper.find('#eta_date_filter').val();

                let promises = [];
                if (loading_port_filter) {
                    promises.push(frappe.db.get_list('Load-Dest Port', {
                        fields: ['name'],
                        filters: { loc_code: ['like', `%${loading_port_filter}%`] }
                    }).then(ports => {
                        if (ports && ports.length > 0) {
                            filters.loading_port = ['in', ports.map(p => p.name)];
                        }
                    }));
                }
                if (destination_port_filter) {
                    promises.push(frappe.db.get_list('Load-Dest Port', {
                        fields: ['name'],
                        filters: { loc_code: ['like', `%${destination_port_filter}%`] }
                    }).then(ports => {
                        if (ports && ports.length > 0) {
                            filters.destination_port = ['in', ports.map(p => p.name)];
                        }
                    }));
                }
                if (vessel_filter) filters.vessel = ['like', `%${vessel_filter}%`];
                if (voyage_filter) filters.voyage = ['like', `%${voyage_filter}%`];
                if (eta_date_filter) filters.eta_date = ['>=', eta_date_filter];

                Promise.all(promises).then(() => {
                    console.log('Filters applied:', filters);

                    frappe.db.get_list('Vessels Time Table', {
                        fields: ['name', 'vessel', 'voyage', 'loading_port', 'destination_port', 'etd_date', 'eta_date', 'carrier', 'cfs_close'],
                        filters: filters,
                        limit: 100
                    }).then(records => {
                        console.log('Fetched records:', records);
                        let promises = records.map(row => {
                            return Promise.all([
                                row.loading_port ? frappe.db.get_value('Load-Dest Port', row.loading_port, ['name', 'loc_code']) : Promise.resolve({ name: '', loc_code: '' }),
                                row.destination_port ? frappe.db.get_value('Load-Dest Port', row.destination_port, ['name', 'loc_code']) : Promise.resolve({ name: '', loc_code: '' })
                            ]).then(([loading_port_res, destination_port_res]) => {
                                row.loading_port_name = loading_port_res.message.name || '';
                                row.loading_port_loc_code = loading_port_res.message.loc_code || '';
                                row.destination_port_name = destination_port_res.message.name || '';
                                row.destination_port_loc_code = destination_port_res.message.loc_code || '';
                                return row;
                            });
                        });

                        Promise.all(promises).then(updated_records => {
                            console.log('Updated records with loc_code:', updated_records);
                            selected_row = null;
                            render_table(updated_records);
                        });
                    });
                });
            }

            render_table([], true); // Initial render with empty records
            load_data();
            dialog.show();
            console.log('Dialog shown');
        });

        // Set vessel field readonly based on add_vessel_now and show vessel_section
        toggleVesselSection(frm);
    },
    add_vessel_now: function(frm) {
        toggleVesselSection(frm);
    },
    items_add: function(frm, cdt, cdn) {
        calculate_total(frm);
    },
    items_remove: function(frm, cdt, cdn) {
        calculate_total(frm);
    }
});

frappe.ui.form.on('Transport Order Line', {
    value: function(frm, cdt, cdn) {
        calculate_total(frm);
    },
    unit_price: function(frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        row.value = (row.unit_price || 0) * (row.qty || 0);
        frm.refresh_field('items');
        calculate_total(frm);
    },
    qty: function(frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        row.value = (row.unit_price || 0) * (row.qty || 0);
        frm.refresh_field('items');
        calculate_total(frm);
    },
    // po_line: function(frm, cdt, cdn) {
    //     var row = locals[cdt][cdn];
    //     if (row.po_line) {
    //         var duplicates = frm.doc.items.filter(function(d) {
    //             return d.po_line === row.po_line && d.name !== row.name;
    //         });
    //         if (duplicates.length > 0) {
    //             frappe.msgprint(__('Duplicate PO Line found! Please remove or change.'));
    //             frappe.model.set_value(cdt, cdn, 'po_line', '');
    //         } else {
    //             frappe.model.get_value('Purchase Order Item', row.po_line, ['article_number', 'article_name'], function(value) {
    //                 frappe.model.set_value(cdt, cdn, 'article_number', value.article_number);
    //                 frappe.model.set_value(cdt, cdn, 'article_name', value.article_name);
    //             });
    //         }
    //     } else {
    //         frappe.model.set_value(cdt, cdn, 'article_number', '');
    //         frappe.model.set_value(cdt, cdn, 'article_name', '');
    //     }
    //     frm.refresh_field('items');
    // }
});

function toggleVesselSection(frm) {
    // Show or hide vessel_section based on add_vessel_now
    frm.set_df_property('vessel_section', 'hidden', frm.doc.add_vessel_now == 1 ? 0 : 1);
    // Set vessel field readonly via HTML when add_vessel_now is checked
    let vessel_input = frm.get_field('vessel').$input;
    if (frm.doc.add_vessel_now == 1) {
        vessel_input.prop('readonly', true);
    } else {
        vessel_input.prop('readonly', false);
    }
}

function calculate_total(frm) {
    let total = 0;
    frm.doc.items.forEach(row => {
        total += row.value || 0;
    });
    frm.set_value('total_value', total);
}