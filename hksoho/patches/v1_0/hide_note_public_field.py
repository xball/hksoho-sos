# Copyright (c) 2026, HKSoHo and contributors
# For license information, please see license.txt

"""Hide the legacy ``Public`` checkbox and decouple the login notification.

Access to a Note is granted from the Share dialog now, so the ``Public``
checkbox is hidden at the metadata level (a Property Setter survives the
``note.js`` edit-mode toggle, which re-evaluates ``field.hidden``).

``notify_on_login`` (label: "Notify users with a popup when they log in") stays
usable: its ``depends_on: public`` is replaced with ``eval:1`` so it is shown
even though ``public`` is always 0, and ``expire_notification_on`` no longer
requires ``doc.public``.
"""

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def execute():
	# Hide the Public checkbox; sharing is driven by the Share dialog instead.
	make_property_setter("Note", "public", "hidden", 1, "Check")

	# Keep the login notification checkbox visible without `public`.
	make_property_setter("Note", "notify_on_login", "depends_on", "eval:1", "Text")
	make_property_setter(
		"Note",
		"expire_notification_on",
		"depends_on",
		"eval:doc.notify_on_login",
		"Text",
	)

	frappe.clear_cache(doctype="Note")
