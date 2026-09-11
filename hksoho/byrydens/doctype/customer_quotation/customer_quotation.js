// Copyright (c) 2026, HKSoHo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Customer Quotation", {
	refresh(frm) {
		frm.add_custom_button(__("Fetch Files from Article Master"), () => {
			fetch_files_from_article_master(frm);
		});
	},

	articale_master(frm) {
		if (!frm.doc.articale_master) {
			frm.clear_table("print_files");
			frm.refresh_field("print_files");
			return;
		}

		if (!(frm.doc.print_files || []).length) {
			fetch_files_from_article_master(frm);
			return;
		}

		frappe.confirm(
			__("Clear existing Print Files and fetch from the new Article Master?"),
			() => {
				frm.clear_table("print_files");
				frm.refresh_field("print_files");
				fetch_files_from_article_master(frm);
			}
		);
	},
});

frappe.ui.form.on("Customer Quotation File", {
	attach_file(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.attach_file) {
			frappe.model.set_value(cdt, cdn, "file_type", "");
			return;
		}
		const ext = (row.attach_file.split("?")[0].split(".").pop() || "").toUpperCase();
		frappe.model.set_value(cdt, cdn, "file_type", ext);
	},
});

function fetch_files_from_article_master(frm) {
	if (!frm.doc.articale_master) {
		frappe.msgprint(__("Please select an Article Master first."));
		return;
	}

	frappe.call({
		method: "hksoho.byrydens.doctype.customer_quotation.customer_quotation.get_article_master_files",
		args: { article_master: frm.doc.articale_master },
		freeze: true,
		freeze_message: __("Loading files..."),
		callback(r) {
			const files = r.message || [];
			if (!files.length) {
				frappe.msgprint(__("No files found on Article Master {0}", [frm.doc.articale_master]));
				return;
			}

			const existing = new Set(
				(frm.doc.print_files || []).map((row) => row.attach_file).filter(Boolean)
			);
			let added = 0;

			files.forEach((file) => {
				if (!file.attach_file || existing.has(file.attach_file)) {
					return;
				}
				const row = frm.add_child("print_files");
				row.description = file.description;
				row.attach_file = file.attach_file;
				row.file_type = file.file_type;
				row.print = file.print ? 1 : 0;
				existing.add(file.attach_file);
				added += 1;
			});

			frm.refresh_field("print_files");

			if (added) {
				frappe.show_alert({
					message: __("Added {0} file(s) from Article Master", [added]),
					indicator: "green",
				});
			} else {
				frappe.show_alert({
					message: __("All Article Master files are already linked"),
					indicator: "blue",
				});
			}
		},
	});
}
