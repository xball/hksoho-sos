// Copyright (c) 2026, HKSoHo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Product Sheet", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Download PDF"), () => download_product_sheet_pdf(frm), __("Print"));
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
});

frappe.ui.form.on("Product Sheet Comment", {
	comments_add(frm, cdt, cdn) {
		const rows = frm.doc.comments || [];
		frappe.model.set_value(cdt, cdn, "comment_no", rows.length);
	},
});

function calc_volume(frm, prefix) {
	const l = flt(frm.doc[`${prefix}_length_cm`]);
	const w = flt(frm.doc[`${prefix}_width_cm`]);
	const h = flt(frm.doc[`${prefix}_height_cm`]);
	const volume = l && w && h ? (l * w * h) / 1000000 : 0;
	frm.set_value(`${prefix}_volume_m3`, volume);
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
