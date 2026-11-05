# Copyright (c) 2026, HKSoHo and contributors
# For license information, please see license.txt

"""Shared authorization helpers for the Byrydens API layer.

Frappe's ``frappe.get_doc``, ``frappe.get_all`` and ``frappe.db.sql`` do NOT
enforce permissions (see ``frappe/model/document.py``); permission checking is
the caller's responsibility. Every ``@frappe.whitelist()`` function must
therefore call one of the helpers below before touching data.

Two access models exist in this app:

* Internal staff (purchase, accounts, co-operators) may see all records.
* Restricted users (suppliers) are scoped through ``User Permission`` rows
  where ``allow == "Partner"``. A restricted user with no Partner row is
  treated as *denied*, never as unrestricted.
"""

from __future__ import annotations

import frappe
from frappe import _

# Roles that legitimately need unrestricted access to purchasing data.
INTERNAL_ROLES = frozenset(
	{
		"System Manager",
		"Purchase Master Manager",
		"Purchase Manager",
		"Purchase User",
		"Accounts Manager",
		"Accounts User",
		"Co-operator",
	}
)

PARTNER_ROLE = "Partner Viewer"


def get_user_roles(user: str | None = None) -> set[str]:
	user = user or frappe.session.user
	if user == "Administrator":
		return {"System Manager"}
	return set(frappe.get_roles(user))


def is_internal_user(user: str | None = None) -> bool:
	"""True when the user is trusted staff who may see every record."""
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(get_user_roles(user) & INTERNAL_ROLES)


def require_internal(message: str | None = None, user: str | None = None) -> None:
	"""Abort unless the session user is trusted staff."""
	if not is_internal_user(user):
		frappe.throw(
			message or _("You do not have permission to perform this action."),
			frappe.PermissionError,
		)


def require_system_manager(message: str | None = None) -> None:
	"""Abort unless the session user is a System Manager."""
	frappe.only_for(("System Manager",), message=message)


def allowed_partner_ids(user: str | None = None) -> list[str]:
	"""Partner names the user is explicitly scoped to via User Permission."""
	user = user or frappe.session.user
	return frappe.get_all(
		"User Permission",
		filters={"user": user, "allow": "Partner"},
		pluck="for_value",
	)


def require_partner_scope(user: str | None = None) -> list[str]:
	"""Return the partner names a restricted user may see.

	Internal staff are not partner-scoped: the returned list is empty and
	callers must skip filtering. A restricted user without any Partner scope is
	rejected rather than silently granted the whole dataset.
	"""
	user = user or frappe.session.user
	partners = allowed_partner_ids(user)
	if not partners and not is_internal_user(user):
		frappe.throw(
			_("No supplier is assigned to your account. Please contact your administrator."),
			frappe.PermissionError,
		)
	return partners


def scoped_supplier_clause(partners: list[str], column: str = "po.supplier") -> tuple[str, dict]:
	"""Build an extra ``AND`` clause restricting ``column`` to ``partners``.

	Returns ``("", {})`` for unscoped (internal) callers so the SQL is unchanged.
	"""
	if not partners:
		return "", {}
	return f" AND {column} IN %(allowed_suppliers)s", {"allowed_suppliers": tuple(partners)}


def xpin_supplier_names(partner_ids: list[str]) -> list[str]:
	"""Map Partner names to the display names stored on legacy xpin_po rows."""
	if not partner_ids:
		return []
	rows = frappe.get_all(
		"Partner",
		filters={"name": ["in", partner_ids]},
		pluck="partner_name",
	)
	return [row.strip() for row in rows if row and row.strip()]


def check_doctype_permission(doctype: str, ptype: str = "read", docname: str | None = None) -> None:
	"""Abort unless the session user holds ``ptype`` on ``doctype``/``docname``."""
	if not frappe.has_permission(doctype, ptype, doc=docname):
		frappe.throw(
			_("You do not have permission to {0} {1}.").format(ptype, _(doctype)),
			frappe.PermissionError,
		)
