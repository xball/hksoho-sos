// Copyright (c) 2026, HKSoHo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Product Sheet", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Download PDF"), () => download_product_sheet_pdf(frm), __("Print"));
		calc_qty_20(frm);
	},
	inner_box_length_cm(frm) {
		calc_volume(frm, "inner_box");
	},
	inner_box_width_cm(frm) {
		calc_volume(frm, "inner_box");
	},
	inner_box_height_cm(frm) {
		calc_volume(frm, "inner_box");
	},
	middle_box_length_cm(frm) {
		calc_volume(frm, "middle_box");
	},
	middle_box_width_cm(frm) {
		calc_volume(frm, "middle_box");
	},
	middle_box_height_cm(frm) {
		calc_volume(frm, "middle_box");
	},
	outer_carton_length_cm(frm) {
		calc_volume(frm, "outer_carton");
	},
	outer_carton_width_cm(frm) {
		calc_volume(frm, "outer_carton");
	},
	outer_carton_height_cm(frm) {
		calc_volume(frm, "outer_carton");
	},
	quantity_outer_carton(frm) {
		calc_qty_20(frm);
	},
	outer_carton_volume_m3(frm) {
		calc_qty_20(frm);
	},
	validate(frm) {
		const seen = {};
		for (const row of frm.doc.rohs || []) {
			const code = (row.rohs_document_relevant_code || "").trim();
			if (!code) continue;
			if (seen[code]) {
				frappe.throw(__("RoHS Document Relevant Code {0} is duplicated", [code]));
			}
			seen[code] = true;
		}
	},
});

frappe.ui.form.on("Product Sheet RoHS", {
	rohs_document_relevant_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const code = (row.rohs_document_relevant_code || "").trim();
		if (!code) return;
		const duplicate = (frm.doc.rohs || []).some(
			(other) => other.name !== row.name && (other.rohs_document_relevant_code || "").trim() === code
		);
		if (!duplicate) return;
		frappe.model.set_value(cdt, cdn, "rohs_document_relevant_code", "");
		frappe.msgprint(__("RoHS Document Relevant Code {0} is already in the table", [code]));
	},
});

frappe.ui.form.on("Product Sheet Comment", {
	comments_add(frm, cdt, cdn) {
		const rows = frm.doc.comments || [];
		frappe.model.set_value(cdt, cdn, "comment_no", rows.length);
	},
});

frappe.ui.form.on("Product Sheet Version Control", {
	version_control_add(frm, cdt, cdn) {
		frappe.model.set_value(cdt, cdn, "date", frappe.datetime.get_today());
		if (frm.doc.version) {
			frappe.model.set_value(cdt, cdn, "version", frm.doc.version);
		}
	},
});

function calc_volume(frm, prefix) {
	const l = flt(frm.doc[`${prefix}_length_cm`]);
	const w = flt(frm.doc[`${prefix}_width_cm`]);
	const h = flt(frm.doc[`${prefix}_height_cm`]);
	const volume = l && w && h ? (l * w * h) / 1000000 : 0;
	frm.set_value(`${prefix}_volume_m3`, volume);
}

function calc_qty_20(frm) {
	const volume = flt(frm.doc.outer_carton_volume_m3);
	const qty = flt(frm.doc.quantity_outer_carton);
	const value = volume && qty ? Math.round(28 / (volume * qty)) : 0;
	if (cint(frm.doc.qty_20) !== value) {
		frm.set_value("qty_20", value);
	}
}

function download_product_sheet_pdf(frm) {
	const params = new URLSearchParams({
		doctype: frm.doc.doctype,
		name: frm.doc.name,
		format: "Product Information Sheet",
		no_letterhead: "1",
		letterhead: "No Letterhead",
		_lang: frappe.boot.lang || "en",
	});
	const url = `/api/method/frappe.utils.print_format.download_pdf?${params.toString()}`;

	frappe.show_alert({ message: __("Generating PDF..."), indicator: "blue" });

	fetch(url, { credentials: "same-origin" })
		.then((response) => {
			if (!response.ok) {
				throw new Error(`PDF failed (${response.status})`);
			}
			const ctype = response.headers.get("content-type") || "";
			if (ctype.includes("application/json")) {
				return response.json().then((data) => {
					throw new Error((data && data.message) || "PDF generation failed");
				});
			}
			return response.blob();
		})
		.then((blob) => {
			const object_url = URL.createObjectURL(blob);
			const a = document.createElement("a");
			a.href = object_url;
			a.download = `${frm.doc.name}.pdf`;
			document.body.appendChild(a);
			a.click();
			a.remove();
			URL.revokeObjectURL(object_url);
			frappe.show_alert({ message: __("PDF downloaded"), indicator: "green" });
		})
		.catch((err) => {
			frappe.msgprint({
				title: __("PDF Error"),
				message: err.message || String(err),
				indicator: "red",
			});
		});
}
