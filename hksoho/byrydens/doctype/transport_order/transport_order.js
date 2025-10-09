frappe.ui.form.on('Transport Order', {
    refresh: function(frm) {
        // Hide the "Add" button for items table
        frm.fields_dict.items.grid.cannot_add_rows = true;
        frm.fields_dict.items.grid.wrapper.find('.grid-add-row').hide();

        // Add custom button "Add Item"
        frm.add_custom_button('Add Item', function() {
            // Get all valid Purchase Orders with workflow_state = 'Ready to Ship'
            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Purchase Order',
                    filters: {
                        workflow_state: 'Ready to Ship' // Only show POs with workflow_state 'Ready to Ship'
                    },
                    fields: ['name'],
                    limit_page_length: 100
                },
                callback: function(r) {
                    if (r.message && r.message.length > 0) {
                        let po_options = r.message.map(po => po.name);

                        // Create dialog with increased width
                        let d = new frappe.ui.Dialog({
                            title: 'Select Purchase Order Items',
                            size: 'extra-large',
                            fields: [
                                {
                                    label: 'Select Purchase Order',
                                    fieldname: 'po_select',
                                    fieldtype: 'Select',
                                    options: po_options,
                                    reqd: 1,
                                    change: function() {
                                        refreshTable(d);
                                    }
                                },
                                {
                                    label: 'Items List',
                                    fieldname: 'items_table',
                                    fieldtype: 'HTML'
                                }
                            ],
                            primary_action_label: 'Add Selected Items',
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
                                        title: 'Error',
                                        message: 'Please select at least one item!',
                                        indicator: 'red'
                                    });
                                    return;
                                }

                                // Check for duplicate po_line
                                let existing_po_lines = frm.doc.items ? frm.doc.items.map(item => item.po_line) : [];
                                let duplicates = selected_items.filter(item => existing_po_lines.includes(item.name));
                                if (duplicates.length > 0) {
                                    frappe.msgprint({
                                        title: 'Error',
                                        message: 'The following items already exist in Transport Order Line: ' + duplicates.map(d => d.line).join(', '),
                                        indicator: 'red'
                                    });
                                    return;
                                }

                                // Add selected items to Transport Order Line child table
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

                                // Refresh child table and update total
                                frm.refresh_field('items');
                                calculate_total(frm);
                                d.hide();
                                setTimeout(function() {
                                    frappe.msgprint({
                                        title: 'Success',
                                        message: 'Selected items added successfully to Transport Order!',
                                        indicator: 'green'
                                    });
                                }, 1500);
                            }
                        });

                        // Disable "Add Selected Items" button by default
                        d.get_primary_btn().prop('disabled', true);

                        // Define function to refresh table
                        function refreshTable(dialog) {
                            let po_name = dialog.get_value('po_select');
                            if (!po_name) {
                                dialog.fields_dict.items_table.$wrapper.empty();
                                dialog.get_primary_btn().prop('disabled', true);
                                return;
                            }

                            frappe.call({
                                method: 'hksoho.byrydens.transport_order_api.get_po_items',
                                args: {
                                    po_name: po_name
                                },
                                callback: function(r) {
                                    let $container = dialog.fields_dict.items_table.$wrapper;
                                    $container.empty();

                                    if (r.message && Array.isArray(r.message) && r.message.length > 0) {
                                        let table = $(`
                                            <table class="table table-bordered" style="width: 100%;">
                                                <thead>
                                                    <tr>
                                                        <th style="width: 5%;">
                                                            <input type="checkbox" id="select_all_items">
                                                            Select
                                                        </th>
                                                        <th style="width: 5%;">Line</th>
                                                        <th style="width: 15%;">Article #</th>
                                                        <th style="width: 25%;">Article Name</th>
                                                        <th style="width: 10%;">Qty</th>
                                                        <th style="width: 10%;">Ctns</th>
                                                        <th style="width: 10%;">CBM</th>
                                                        <th style="width: 10%;">Gross Kg</th>
                                                        <th style="width: 10%;">Unit Price</th>
                                                    </tr>
                                                </thead>
                                                <tbody></tbody>
                                            </table>
                                        `);

                                        table.find('#select_all_items').on('change', function() {
                                            table.find('tbody input[name="item_select"]').prop('checked', $(this).prop('checked'));
                                            let any_checked = table.find('tbody input[name="item_select"]:checked').length > 0;
                                            dialog.get_primary_btn().prop('disabled', !any_checked);
                                        });

                                        let tbody = table.find('tbody');
                                        r.message.forEach(item => {
                                            let qty = (item.booked_qty || 0) - (item.delivery_qty || 0);
                                            tbody.append(`
                                                <tr>
                                                    <td><input type="checkbox" name="item_select" value="${item.name}" 
                                                        data-line="${item.line || ''}" 
                                                        data-article-number="${item.article_number || ''}" 
                                                        data-article-name="${item.article_name || ''}" 
                                                        data-qty="${qty}" 
                                                        data-ctns="${item.ctns_on_pallet || 0}" 
                                                        data-cbm="${item.carton_cbm || 0}" 
                                                        data-gross-kg="${item.carton_gross_kg || 0}" 
                                                        data-unit-price="${item.unit_price || 0}"></td>
                                                    <td>${item.line || ''}</td>
                                                    <td>${item.article_number || ''}</td>
                                                    <td>${item.article_name || ''}</td>
                                                    <td>${qty}</td>
                                                    <td>${item.ctns_on_pallet || 0}</td>
                                                    <td>${item.carton_cbm || 0}</td>
                                                    <td>${item.carton_gross_kg || 0}</td>
                                                    <td>${item.unit_price || 0}</td>
                                                </tr>
                                            `);
                                        });

                                        table.find('tbody input[name="item_select"]').on('change', function() {
                                            let any_checked = table.find('tbody input[name="item_select"]:checked').length > 0;
                                            dialog.get_primary_btn().prop('disabled', !any_checked);
                                            let all_checked = table.find('tbody input[name="item_select"]').length === table.find('tbody input[name="item_select"]:checked').length;
                                            table.find('#select_all_items').prop('checked', all_checked);
                                        });

                                        if (tbody.find('tr').length === 0) {
                                            $container.html('<p>No items to display</p>');
                                            dialog.get_primary_btn().prop('disabled', true);
                                        } else {
                                            $container.append(table);
                                            dialog.get_primary_btn().prop('disabled', true);
                                        }
                                    } else {
                                        $container.html('<p>No items to display</p>');
                                        dialog.get_primary_btn().prop('disabled', true);
                                    }
                                }
                            });
                        }

                        d.show();
                        d.fields_dict.items_table.$wrapper.empty();
                    } else {
                        frappe.msgprint({
                            title: 'No Data',
                            message: 'No Purchase Orders with workflow_state "Ready to Ship" found.',
                            indicator: 'orange'
                        });
                    }
                }
            });
        });

        // Add custom button "Vendor Invoice" (visible in all workflow states)
        frm.add_custom_button('Vendor Invoice', function() {
            // Get unique PO numbers from Transport Order Line
            let po_numbers = [...new Set(frm.doc.items ? frm.doc.items.map(item => item.po_number) : [])];
            if (po_numbers.length === 0) {
                frappe.msgprint({
                    title: 'No Data',
                    message: 'No Purchase Order items found in Transport Order to update invoice details.',
                    indicator: 'orange'
                });
                return;
            }

            // Create dialog for entering invoice details
            let d = new frappe.ui.Dialog({
                title: 'Enter Vendor Invoice Details',
                size: 'large',
                fields: [
                    {
                        label: 'Select Purchase Order',
                        fieldname: 'po_select',
                        fieldtype: 'Select',
                        options: po_numbers,
                        reqd: 1
                    },
                    {
                        label: 'Invoice Received',
                        fieldname: 'invoice_received',
                        fieldtype: 'Check',
                        default: 0
                    },
                    {
                        label: 'Invoice Number',
                        fieldname: 'invoice_no',
                        fieldtype: 'Data',
                        depends_on: 'eval:doc.invoice_received==1'
                    },
                    {
                        label: 'Invoice Currency',
                        fieldname: 'invoice_currency',
                        fieldtype: 'Link',
                        options: 'Currency',
                        depends_on: 'eval:doc.invoice_received==1'
                    },
                    {
                        label: 'Invoice Date',
                        fieldname: 'invoice_date',
                        fieldtype: 'Date',
                        depends_on: 'eval:doc.invoice_received==1'
                    },
                    {
                        label: 'Invoice Due Date',
                        fieldname: 'invoice_due_date',
                        fieldtype: 'Date',
                        depends_on: 'eval:doc.invoice_received==1'
                    },
                    {
                        label: 'Invoice Paid',
                        fieldname: 'invoice_paid',
                        fieldtype: 'Check',
                        default: 0,
                        depends_on: 'eval:doc.invoice_received==1'
                    },
                    {
                        label: 'Exchange Rate to SEK',
                        fieldname: 'exchange_rate_to_sek',
                        fieldtype: 'Float',
                        depends_on: 'eval:doc.invoice_received==1'
                    }
                ],
                primary_action_label: 'Apply',
                primary_action: function() {
                    let values = d.get_values();
                    if (!values) return;

                    let po_name = values.po_select;
                    let updated = false;

                    // Update invoice fields for all rows with the selected PO
                    frm.doc.items.forEach(row => {
                        if (row.po_number === po_name) {
                            row.invoice_received = values.invoice_received;
                            if (values.invoice_received) {
                                row.invoice_no = values.invoice_no;
                                row.invoice_currency = values.invoice_currency;
                                row.invoice_date = values.invoice_date;
                                row.invoice_due_date = values.invoice_due_date;
                                row.invoice_paid = values.invoice_paid;
                                row.exchange_rate_to_sek = values.exchange_rate_to_sek;
                            } else {
                                row.invoice_no = null;
                                row.invoice_currency = null;
                                row.invoice_date = null;
                                row.invoice_due_date = null;
                                row.invoice_paid = 0;
                                row.exchange_rate_to_sek = null;
                            }
                            updated = true;
                        }
                    });

                    if (updated) {
                        frm.refresh_field('items');
                        frm.dirty();
                        frappe.msgprint({
                            title: 'Success',
                            message: 'Invoice details updated successfully for the selected Purchase Order!',
                            indicator: 'green'
                        });
                        d.hide();
                    } else {
                        frappe.msgprint({
                            title: 'No Updates',
                            message: 'No items found matching the selected Purchase Order.',
                            indicator: 'orange'
                        });
                    }
                }
            });

            // Show/hide invoice fields based on invoice_received
            d.fields_dict.invoice_received.$input.on('change', function() {
                let invoice_received = d.get_value('invoice_received');
                let fields = ['invoice_no', 'invoice_currency', 'invoice_date', 'invoice_due_date', 'invoice_paid', 'exchange_rate_to_sek'];
                fields.forEach(field => {
                    d.set_df_property(field, 'hidden', invoice_received ? 0 : 1);
                });
            });

            d.show();
        });

        // Show/Hide "Add Item" button based on workflow_state
        let add_item_button = frm.$wrapper.find('.btn:contains("Add Item")');
        if (frm.doc.workflow_state === "Unconfirmed" || frm.doc.workflow_state === "Empty TO Head") {
            add_item_button.css('display', 'inline-block');
        } else {
            add_item_button.css('display', 'none');
        }

        // Show "(Select)" hyperlink next to the Vessel label
        let vessel_field = frm.get_field('vessel').$wrapper;
        vessel_field.find('.select-vessel-link').remove();
        vessel_field.find('.control-label').append(`
            <a href="#" class="select-vessel-link" style="margin-left: 5px; font-size: 12px; color: #007bff; text-decoration: none;">(Select)</a>
        `);
        vessel_field.find('.select-vessel-link').on('click', function(e) {
            e.preventDefault();
            let selected_row = null;
            let dialog = new frappe.ui.Dialog({
                title: 'Select Vessel',
                size: 'extra-large',
                fields: [
                    { fieldtype: 'HTML', fieldname: 'vessel_html' }
                ],
                primary_action_label: 'Add New',
                primary_action: function() {
                    frappe.new_doc('Vessels Time Table', {}, function() {
                        dialog.hide();
                    });
                }
            });

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
                                    <input type="text" id="vessel_filter" placeholder="Vessel" class="form-control">
                                    <span class="clear-filter" data-filter="vessel_filter">X</span>
                                </th>
                                <th style="width: 100px;">
                                    <input type="text" id="voyage_filter" placeholder="Voyage" class="form-control">
                                    <span class="clear-filter" data-filter="voyage_filter">X</span>
                                </th>
                                <th style="width: 120px;">
                                    <input type="text" id="loading_port_filter" placeholder="Load Port" class="form-control">
                                    <span class="clear-filter" data-filter="loading_port_filter">X</span>
                                </th>
                                <th style="width: 120px;">
                                    <input type="text" id="destination_port_filter" placeholder="Dest Port" class="form-control">
                                    <span class="clear-filter" data-filter="destination_port_filter">X</span>
                                </th>
                                <th style="width: 100px;"></th>
                                <th style="width: 100px;">
                                    <div class="eta-filter-container">
                                        <span>&gt;</span>
                                        <input type="date" id="eta_date_filter" placeholder="ETA >=" class="form-control">
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
                                    <a href="#" onclick="frappe.new_doc('Vessels Time Table', {}, function() { dialog.hide(); });">(Add New)</a> (${records.length} records)
                                </td>
                            </tr>
                        </tfoot>
                    </table>
                    </div>
                `;
                if (initial) {
                    dialog.fields_dict.vessel_html.$wrapper.html(html);
                    const debounced_load_data = debounce(load_data, 300);
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
                    frappe.show_alert({ message: 'Selected Vessel: ' + selected_row.vessel, indicator: 'green' });
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
                    frappe.db.get_list('Vessels Time Table', {
                        fields: ['name', 'vessel', 'voyage', 'loading_port', 'destination_port', 'etd_date', 'eta_date', 'carrier', 'cfs_close'],
                        filters: filters,
                        limit: 100
                    }).then(records => {
                        let promises = records.map(row => {
                            return Promise.all([
                                row.loading_port ? frappe.db.get_value('Load-Dest Port', row.loading_port, ['name', 'loc_code']) : Promise.resolve({ message: { name: '', loc_code: '' } }),
                                row.destination_port ? frappe.db.get_value('Load-Dest Port', row.destination_port, ['name', 'loc_code']) : Promise.resolve({ message: { name: '', loc_code: '' } })
                            ]).then(([loading_port_res, destination_port_res]) => {
                                row.loading_port_name = loading_port_res.message ? loading_port_res.message.name : '';
                                row.loading_port_loc_code = loading_port_res.message ? loading_port_res.message.loc_code : '';
                                row.destination_port_name = destination_port_res.message ? destination_port_res.message.name : '';
                                row.destination_port_loc_code = destination_port_res.message ? destination_port_res.message.loc_code : '';
                                return row;
                            });
                        });

                        Promise.all(promises).then(updated_records => {
                            selected_row = null;
                            render_table(updated_records);
                        });
                    });
                });
            }

            render_table([], true);
            load_data();
            dialog.show();
        });

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
    invoice_due_date: function(frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        if (row.invoice_date && row.invoice_due_date && row.invoice_due_date < row.invoice_date) {
            frappe.msgprint({
                title: 'Error',
                message: 'Invoice Due Date cannot be earlier than Invoice Date',
                indicator: 'red'
            });
            frappe.model.set_value(cdt, cdn, 'invoice_due_date', null);
        }
    }
});

function toggleVesselSection(frm) {
    frm.set_df_property('vessel_section', 'hidden', frm.doc.add_vessel_now == 1 ? 0 : 1);
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
    frm.set_value('total_value', parseFloat(total.toFixed(2)));
}