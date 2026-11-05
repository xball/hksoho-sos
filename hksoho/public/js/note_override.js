// Copyright (c) 2026, HKSoHo and contributors
// For license information, please see license.txt

// Note form tweaks:
//  1. Hide the legacy `public` checkbox (access is governed by the Share dialog).
//  2. Treat an "Everyone" share row as if it were a share for the current user,
//     because frappe's perm.js only applies `docinfo.shared` rows whose `user`
//     matches the session user.
//  3. Keep the Private / Shared / Public pill in the form header in sync.

(function () {
	// ------------------------------------------------------------------
	// 2. Everyone shares must grant read / write / share in the UI too.
	// ------------------------------------------------------------------
	if (!frappe.perm._get_perm.__hksoho_note_patched) {
		const original_get_perm = frappe.perm._get_perm;

		frappe.perm._get_perm = function (doctype, doc) {
			if (doctype === "Note" && doc && doc.name) {
				try {
					const docinfo = frappe.model.get_docinfo(doctype, doc.name);
					const shared = docinfo && docinfo.shared;
					if (Array.isArray(shared)) {
						const user = frappe.session.user;
						const known = new Set(shared.map((s) => s && s.name));

						shared.slice().forEach((s) => {
							if (!s || !s.everyone || s.user === user) return;
							const key = `${s.name}::${user}`;
							if (known.has(key)) return;

							// Synthetic clone scoped to the current user.
							shared.push(
								Object.assign({}, s, {
									user: user,
									__hksoho_everyone: true,
									name: key,
								})
							);
							known.add(key);
						});
					}
				} catch (e) {
					console.error("Note share permission patch failed", e);
				}
			}
			return original_get_perm.apply(this, arguments);
		};

		frappe.perm._get_perm.__hksoho_note_patched = true;
	}

	// ------------------------------------------------------------------
	// 3. Derive the status pill from the share list.
	// ------------------------------------------------------------------
	function compute_status(rows) {
		const shared = (rows || []).filter(Boolean);
		if (shared.some((s) => s.everyone)) return "Public";
		if (shared.length) return "Shared";
		return "Private";
	}

	function shared_rows(frm) {
		// Prefer the Share dialog's in-memory list when it is loaded so the pill
		// updates instantly; fall back to the server docinfo.
		const live = frm.shared && frm.shared.shared;
		if (Array.isArray(live)) return live;
		const docinfo = frappe.model.get_docinfo(frm.doctype, frm.docname);
		return (docinfo && docinfo.shared) || [];
	}

	function apply_status(frm) {
		if (!frm || !frm.doc) return;
		const status = compute_status(shared_rows(frm));
		if (frm.doc.share_status === status) return;

		frm.doc.share_status = status;
		if (frm.toolbar) frm.toolbar.set_indicator();
	}

	// ------------------------------------------------------------------
	// 1 + wiring
	// ------------------------------------------------------------------
	frappe.ui.form.on("Note", {
		refresh(frm) {
			frm.set_df_property("public", "hidden", 1);

			if (!frm.__hksoho_status_wired) {
				frm.__hksoho_status_wired = true;

				// The Share dialog calls shared.refresh() after every toggle.
				if (frm.shared && !frm.shared.__hksoho_refresh_patched) {
					frm.shared.__hksoho_refresh_patched = true;
					const original_shared_refresh = frm.shared.refresh.bind(frm.shared);
					frm.shared.refresh = function () {
						const result = original_shared_refresh.apply(null, arguments);
						try {
							apply_status(frm);
						} catch (e) {
							console.error("Note share status refresh failed", e);
						}
						return result;
					};
				}

				// Authoritative refresh once the dialog closes / docinfo reloads.
				if (frm.sidebar && !frm.sidebar.__hksoho_reload_patched) {
					frm.sidebar.__hksoho_reload_patched = true;
					const original_reload = frm.sidebar.reload_docinfo.bind(frm.sidebar);
					frm.sidebar.reload_docinfo = function (callback) {
						return original_reload(function (docinfo) {
							if (callback) callback(docinfo);
							try {
								apply_status(frm);
							} catch (e) {
								console.error("Note share status refresh failed", e);
							}
						});
					};
				}
			}

			apply_status(frm);
		},
	});
})();
