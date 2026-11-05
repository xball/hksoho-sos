// Copyright (c) 2026, HKSoHo and contributors
// For license information, please see license.txt

// Note list view: show the Private / Shared / Public status pill.
//
// This file is injected through the `doctype_list_js` hook, which is appended
// *after* frappe's own `note_list.js`, so we patch the existing settings
// object instead of replacing it (that would drop `hide_name_column`).

(function () {
	const settings = (frappe.listview_settings["Note"] = frappe.listview_settings["Note"] || {});

	settings.add_fields = Array.from(new Set([...(settings.add_fields || []), "share_status"]));

	settings.get_indicator = function (doc) {
		const status = doc.share_status || (doc.public ? "Public" : "Private");

		if (status === "Public") {
			return [__("Public"), "green", "share_status,=,Public"];
		}
		if (status === "Shared") {
			return [__("Shared"), "blue", "share_status,=,Shared"];
		}
		return [__("Private"), "gray", "share_status,=,Private"];
	};
})();
