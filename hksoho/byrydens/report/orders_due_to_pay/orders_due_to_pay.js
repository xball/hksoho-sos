frappe.query_reports["Orders Due to Pay"] = {
    filters: [],  // 移除頂部 filter box
    
    onload: function(report) {
        // 隱藏所有 dropdown 和 filter 相關功能
        setTimeout(function() {
            // 隱藏 filter row
            $('.dt-row-filter').remove();
            
            // 隱藏每個欄位標題的 dropdown 按鈕
            $('.dt-dropdown').remove();
            
            // 移除 resize handle（調整欄位寬度的把手）
            $('.dt-cell__resize-handle').remove();
            
            // 隱藏 dropdown container
            $('.dt-dropdown-container').remove();
        }, 200);
    },
    formatter: function(value, row, column, data, default_formatter) {
        if (column.fieldname === "details" && data && data.details) {
            const month_name = data.month.split(' ')[0];   // 取出 "March"
            return `<button class="btn btn-xs btn-primary" 
                            onclick="showDuePODetails('${data.year}', '${month_name}')">
                    View Details
                    </button>`;
        }
        return default_formatter(value, row, column, data);
    }

};

function showDuePODetails(year, month) {
    frappe.call({
        method: "hksoho.byrydens.utils.get_due_po_details",
        args: { year: year, month_name: month },
        callback: function(r) {
            if (r.message && r.message.data && r.message.data.length > 0) {
                // 計算總額（按幣別分組）
                let currency_totals = {};
                
                r.message.data.forEach(function(row) {
                    if (row.undelivered_value) {
                        let curr = row.currency || 'Unknown';
                        currency_totals[curr] = (currency_totals[curr] || 0) + row.undelivered_value;
                    }
                });
                
                // 建立 HTML 表格
                let html = `
                    <div style="overflow-x: auto;">
                        <table class="table table-bordered table-hover" style="width: 100%; margin-top: 10px;">
                            <thead style="background-color: #f5f5f5;">
                                <tr>
                                    <th>PO Number</th>
                                    <th>Partner ID</th>
                                    <th>Partner Name</th>
                                    <th>Ship Date</th>
                                    <th>Status</th>
                                    <th>Currency</th>
                                    <th style="text-align: right;">Undelivered Value</th>
                                </tr>
                            </thead>
                            <tbody>
                `;
                
                // 加入每一行資料
                r.message.data.forEach(function(row) {
                    html += `
                        <tr>
                            <td><a href="/app/purchase-order/${row.po_number}" target="_blank">${row.po_number}</a></td>
                            <td>${row.partner_id || ''}</td>
                            <td>${row.partner_name || ''}</td>
                            <td>${frappe.datetime.str_to_user(row.po_shipdate) || ''}</td>
                            <td><span class="badge badge-primary">${row.po_status || ''}</span></td>
                            <td>${row.currency || ''}</td>
                            <td style="text-align: right;">${format_currency(row.undelivered_value, row.currency)}</td>
                        </tr>
                    `;
                });
                
                // 加入合計行
                html += `
                            </tbody>
                            <tfoot style="background-color: #f0f0f0; font-weight: bold;">
                                <tr>
                                    <td colspan="6" style="text-align: right; padding-right: 15px;">Total by Currency:</td>
                                    <td style="text-align: right;">
                `;
                
                // 顯示各幣別的合計
                Object.keys(currency_totals).sort().forEach(function(curr) {
                    html += `<div>${curr}: ${format_currency(currency_totals[curr], curr)}</div>`;
                });
                
                html += `
                                    </td>
                                </tr>
                            </tfoot>
                        </table>
                    </div>
                `;
                
                // 顯示 Dialog
                let dialog = new frappe.ui.Dialog({
                    title: r.message.title || `${month} ${year} - Orders Due to Pay`,
                    size: "extra-large",
                    fields: [{
                        fieldtype: "HTML",
                        options: html
                    }],
                    primary_action_label: "Close",
                    primary_action: function() {
                        dialog.hide();
                    }
                });
                
                dialog.show();
                
            } else {
                frappe.msgprint({
                    title: "No Data",
                    message: `No due PO found in ${month} ${year}`,
                    indicator: "blue"
                });
            }
        },
        error: function(err) {
            frappe.msgprint("API Error: " + (err.message || "Check method path"));
        }
    });
}
