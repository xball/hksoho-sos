// Product Information Sheet already draws its own header.
// /printview?no_letterhead=1 is the correct layout. Desk /app/print otherwise
// defaults to the company letterhead and wkhtmltopdf extra margins.
//
// Print Designer replaces PrintView after this file may have run, and the
// print Page script is cached in localStorage — so we patch the live class
// and also force the Letter Head input on the print route.

(function product_sheet_print_match_printview() {
	const DOCTYPE = "Product Sheet";

	function no_letterhead_label() {
		return __("No Letterhead");
	}

	function is_product_sheet(ctx) {
		return !!(ctx && ctx.frm && ctx.frm.doctype === DOCTYPE);
	}

	function patch_proto(proto) {
		if (!proto || proto._hksoho_pis_letterhead) return;
		proto._hksoho_pis_letterhead = true;

		const orig_default = proto.set_default_letterhead;
		proto.set_default_letterhead = function () {
			if (is_product_sheet(this)) {
				if (this.letterhead_selector) {
					this.letterhead_selector.val(no_letterhead_label());
				}
				return;
			}
			return orig_default.apply(this, arguments);
		};

		const orig_get = proto.get_letterhead;
		proto.get_letterhead = function () {
			if (is_product_sheet(this)) {
				return no_letterhead_label();
			}
			return orig_get.apply(this, arguments);
		};
	}

	function try_patch() {
		try {
			if (frappe.ui && frappe.ui.form && frappe.ui.form.PrintView) {
				patch_proto(frappe.ui.form.PrintView.prototype);
			}
		} catch (e) {
			/* PrintView not ready */
		}
	}

	function force_letterhead_input() {
		try {
			const route = frappe.get_route ? frappe.get_route() : [];
			if (!route || route[0] !== "print" || route[1] !== DOCTYPE) return;
			const label = no_letterhead_label();
			document.querySelectorAll(".print-preview-sidebar input").forEach((input) => {
				if (input.getAttribute("placeholder") !== __("Letter Head") && input.placeholder !== "Letter Head") {
					return;
				}
				if (input.value === label) return;
				input.value = label;
				$(input).trigger("change");
			});
		} catch (e) {
			/* ignore */
		}
	}

	try_patch();
	setInterval(try_patch, 250);
	setTimeout(force_letterhead_input, 200);
	setTimeout(force_letterhead_input, 800);

	if (frappe.router && frappe.router.on) {
		frappe.router.on("change", () => {
			try_patch();
			setTimeout(force_letterhead_input, 200);
			setTimeout(force_letterhead_input, 800);
		});
	}
})();
