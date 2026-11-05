# Copyright (c) 2026, HKSoHo and contributors
# For license information, please see license.txt

"""Note sharing permissions for Byrydens.

Frappe core restricts Note visibility to ``owner`` or ``public = 1`` and
ignores ``DocShare`` completely (see ``frappe/desk/doctype/note/note.py``).
The Share dialog therefore does nothing useful for a private Note.

This module replaces those two core functions at runtime (they are resolved
with ``frappe.get_attr`` on every call, so patching the module attribute is
enough and no core file is touched) so that the Share dialog actually drives
access:

* ``owner`` keeps full access (unchanged).
* Users with a ``DocShare`` row get exactly the rights that were ticked
  (read / write / share).
* ``public = 1`` is still honoured so restoring an old backup or creating
  public notes programmatically never locks anybody out.

It also maintains the hidden ``Note.share_status`` field:

* ``Public``  -- shared with Everyone (or legacy ``public = 1``)
* ``Shared``  -- shared with at least one specific user
* ``Private`` -- not shared at all.

That field is what the list view pill shows, and it is a real column so it can
be filtered and sorted.
"""

from __future__ import annotations

import frappe

PRIVATE = "Private"
SHARED = "Shared"
PUBLIC = "Public"

STATUS_OPTIONS = (PRIVATE, SHARED, PUBLIC)

STATUS_FIELD = "share_status"

# Permission types that are satisfied by "read" on a shared document.
READ_LIKE = frozenset({"read", "select", "print", "email", "report", "export"})

# Permission types that can legitimately be granted through a DocShare row.
SHAREABLE = frozenset({"read", "write", "submit", "share"})


# ---------------------------------------------------------------------------
# Permission hooks (replace the core Note implementations)
# ---------------------------------------------------------------------------


def _current_user(user: str | None = None) -> str:
	return user or frappe.session.user


def _note_owner(doc) -> str:
	return (doc.get("owner") if hasattr(doc, "get") else getattr(doc, "owner", None)) or ""


def _is_new(doc) -> bool:
	is_new = getattr(doc, "is_new", None)
	if callable(is_new):
		try:
			return bool(is_new())
		except Exception:
			return False
	return bool(doc.get("__islocal"))


def _is_shared_with(note: str, user: str, rights: list[str]) -> bool:
	"""True when ``note`` is shared with ``user`` (or Everyone) with ``rights``."""
	try:
		return bool(
			frappe.share.get_shared(
				"Note",
				user,
				rights=rights,
				filters=[["share_name", "=", note]],
				limit=1,
			)
		)
	except Exception:
		frappe.log_error(
			title="Note share permission lookup failed",
			message=f"note={note!r} user={user!r} rights={rights!r}\n{frappe.get_traceback()}",
		)
		# Never fail open/closed on an infrastructure error: fall back to the
		# original core rule so nobody loses access unexpectedly.
		return False


def has_permission(doc, ptype: str | None = "read", user: str | None = None):
	"""Controller permission hook for Note (replaces the core implementation).

	Returns ``True`` to allow, ``False`` to deny, and ``None`` to defer to the
	role permission system (used for permission types that sharing cannot
	grant, such as delete/cancel/amend/create).
	"""
	if isinstance(doc, str | int):
		doc = frappe.get_doc("Note", doc)

	if doc is None:
		return None

	user = _current_user(user)
	if user == "Administrator":
		return True

	flags = getattr(doc, "flags", None)
	if flags is not None and flags.ignore_permissions:
		return True

	# Creation is governed by role permissions.
	if ptype == "create":
		return True

	if _is_new(doc):
		return True

	owner = _note_owner(doc)
	is_owner = bool(owner) and owner.lower() == user.lower()
	is_public = bool(doc.get("public"))
	name = doc.get("name")

	if ptype is None:
		# Whole permission map request (docinfo / client.get_doc_permissions).
		# Mirror core so the UI never over-grants: only owner and public notes
		# get their role permissions evaluated.
		return is_owner or is_public

	if not name:
		return is_owner or is_public

	if is_owner:
		return True

	if ptype in READ_LIKE:
		if is_public:
			return True
		return _is_shared_with(name, user, ["read"])

	if ptype in SHAREABLE:
		return _is_shared_with(name, user, [ptype])

	# delete / cancel / amend / import / ...: never granted by sharing.
	return None


def get_permission_query_conditions(user: str | None = None, doctype: str | None = None) -> str:
	"""Row level condition for Note list / report / search queries."""
	user = _current_user(user)

	conditions = [
		f"`tabNote`.`owner` = {frappe.db.escape(user, percent=False)}",
		"`tabNote`.`public` = 1",
	]

	share = (
		"select 1 from `tabDocShare`"
		" where `tabDocShare`.`share_doctype` = 'Note'"
		" and `tabDocShare`.`share_name` = `tabNote`.`name`"
		" and `tabDocShare`.`read` = 1"
	)
	if user == "Guest":
		share += f" and `tabDocShare`.`user` = {frappe.db.escape(user, percent=False)}"
	else:
		share += (
			" and (`tabDocShare`.`user` = "
			f"{frappe.db.escape(user, percent=False)}"
			" or `tabDocShare`.`everyone` = 1)"
		)

	return "(" + " or ".join(conditions) + f" or exists({share}))"


def apply() -> None:
	"""Swap the core Note permission hooks for ours (idempotent).

	Runs on every request (``before_request``) and every background job
	(``before_job``), so it must stay cheap and must never raise: a failure here
	would break the whole site rather than just Note permissions.
	"""
	try:
		from frappe.desk.doctype.note import note as note_module

		if (
			getattr(note_module, "get_permission_query_conditions", None)
			is not get_permission_query_conditions
		):
			note_module.get_permission_query_conditions = get_permission_query_conditions

		if getattr(note_module, "has_permission", None) is not has_permission:
			note_module.has_permission = has_permission

		Note = note_module.Note
		if getattr(Note, "validate", None) is not patched_note_validate:
			global _original_note_validate
			if _original_note_validate is None:
				_original_note_validate = Note.validate
			Note.validate = patched_note_validate

		if getattr(note_module, "_get_unseen_notes", None) is not patched_get_unseen_notes:
			global _original_get_unseen_notes
			if _original_get_unseen_notes is None:
				_original_get_unseen_notes = note_module._get_unseen_notes
			note_module._get_unseen_notes = patched_get_unseen_notes

		# The popup actually rendered by the desk comes from frappe.boot.
		import frappe.boot as boot_module

		if getattr(boot_module, "get_unseen_notes", None) is not patched_boot_get_unseen_notes:
			global _original_boot_get_unseen_notes
			if _original_boot_get_unseen_notes is None:
				_original_boot_get_unseen_notes = boot_module.get_unseen_notes
			boot_module.get_unseen_notes = patched_boot_get_unseen_notes
	except Exception:
		frappe.log_error(
			title="Note permission patch failed",
			message=frappe.get_traceback(),
		)


# ---------------------------------------------------------------------------
# validate tweak: keep the login notification independent from `public`
# ---------------------------------------------------------------------------

_original_note_validate = None


def patched_note_validate(self):
	"""``Note.validate`` that does not discard ``notify_on_login``.

	Core clears ``notify_on_login`` whenever the note is not public. The Public
	checkbox is hidden now (access comes from the Share dialog), so that rule
	would silently wipe the popup setting on every save.
	"""
	notify_on_login = self.get("notify_on_login")

	_original_note_validate(self)

	# Core only cleared it because `public` is falsy; restore the user's choice.
	if notify_on_login and not self.get("notify_on_login"):
		self.notify_on_login = notify_on_login
		if not self.get("expire_notification_on"):
			creation = self.get("creation") or frappe.utils.nowdate()
			self.expire_notification_on = frappe.utils.add_days(creation, 7)


# ---------------------------------------------------------------------------
# Login popup notifications: only for notes the user may actually read
# ---------------------------------------------------------------------------

_original_get_unseen_notes = None

UNSEEN_NOTES_KEY = "unseen_notes::"


def _readable_note_names(names: list[str], user: str | None = None) -> set[str]:
	"""Subset of ``names`` the user is allowed to read, resolved in one query."""
	if not names:
		return set()

	user = _current_user(user)
	if user == "Administrator":
		return set(names)

	try:
		placeholders = ", ".join(["%s"] * len(names))
		condition = get_permission_query_conditions(user)
		rows = frappe.db.sql(
			f"select `tabNote`.`name` from `tabNote`"
			f" where `tabNote`.`name` in ({placeholders}) and {condition}",
			tuple(names),
		)
		return {row[0] for row in rows}
	except Exception:
		frappe.log_error(
			title="Note popup permission filter failed",
			message=frappe.get_traceback(),
		)
		# Fail closed: never leak the content of an unreadable note.
		return set()


def patched_get_unseen_notes():
	"""``_get_unseen_notes`` restricted to notes the user can actually read.

	Core selects every ``notify_on_login`` note regardless of access, so a
	private note would pop up for the whole company. We keep core's query (it
	also handles ``Note Seen By`` and the expiry window) and filter its cached
	result by our permission rules.
	"""
	if _original_get_unseen_notes is None:
		return []

	_original_get_unseen_notes()

	key = f"{UNSEEN_NOTES_KEY}{frappe.session.user}"
	rows = frappe.cache.get_value(key) or []
	if not rows:
		return rows

	filtered = _filter_readable_notes(rows)
	if len(filtered) != len(rows):
		frappe.cache.set_value(key, filtered)

	return filtered


_original_boot_get_unseen_notes = None


def patched_boot_get_unseen_notes():
	"""``frappe.boot.get_unseen_notes`` with a read-permission filter.

	This is the function ``frappe.sessions.get()`` uses to populate
	``bootinfo.notes``, which ``desk.js`` renders as login popups. It queries
	the database on every boot, so access changes apply on the next page load.
	"""
	if _original_boot_get_unseen_notes is None:
		return []

	rows = _original_boot_get_unseen_notes() or []
	if not rows:
		return rows

	return _filter_readable_notes(rows)


def _filter_readable_notes(rows):
	names = [row.get("name") for row in rows if row.get("name")]
	readable = _readable_note_names(names)
	return [row for row in rows if row.get("name") in readable]


def clear_unseen_notes_cache(user: str | None = None) -> None:
	"""Drop the cached login popups for one user, or for everyone."""
	try:
		if user:
			frappe.cache.delete_value(f"{UNSEEN_NOTES_KEY}{user}")
		else:
			frappe.cache.delete_keys(UNSEEN_NOTES_KEY)
	except Exception:
		frappe.log_error(
			title="Note popup cache clear failed",
			message=f"user={user!r}\n{frappe.get_traceback()}",
		)


def invalidate_unseen_notes_on_share(doc, everyone_share: bool = False, user: str | None = None) -> None:
	"""A share change can grant or revoke a popup, so drop the cached list."""
	if everyone_share:
		clear_unseen_notes_cache()
	elif user:
		clear_unseen_notes_cache(user)


def on_note_update(doc, method: str | None = None) -> None:
	"""Clear cached popups when the notification itself changes."""
	try:
		changed = any(
			doc.has_value_changed(field)
			for field in ("notify_on_login", "notify_on_every_login", "content", "title")
		)
	except Exception:
		# Outside a save lifecycle the comparison is meaningless; skip.
		return

	if changed:
		clear_unseen_notes_cache()


# ---------------------------------------------------------------------------
# share_status maintenance
# ---------------------------------------------------------------------------


def _has_status_column() -> bool:
	try:
		return frappe.db.has_column("Note", STATUS_FIELD)
	except Exception:
		return False


def compute_share_status(note: str, public: bool | None = None) -> str:
	"""Derive the status of ``note`` from its DocShare rows."""
	if public is None:
		public = bool(frappe.db.get_value("Note", note, "public"))

	shares = frappe.get_all(
		"DocShare",
		filters={"share_doctype": "Note", "share_name": note},
		fields=["name", "everyone"],
		limit=0,
	)

	if shares and any(row.everyone for row in shares):
		return PUBLIC
	if shares:
		return SHARED
	if public:
		return PUBLIC
	return PRIVATE


def set_share_status(note: str, status: str | None = None) -> str | None:
	"""Persist the computed status without touching ``modified``."""
	if not _has_status_column() or not note:
		return None

	if status is None:
		status = compute_share_status(note)

	try:
		current = frappe.db.get_value("Note", note, STATUS_FIELD)
		if current != status:
			frappe.db.set_value("Note", note, STATUS_FIELD, status, update_modified=False)
	except Exception:
		frappe.log_error(
			title="Note share status update failed",
			message=f"note={note!r} status={status!r}\n{frappe.get_traceback()}",
		)
		return None

	return status


def sync_note_share_status(doc, method: str | None = None) -> None:
	"""``DocShare`` doc_event: keep ``Note.share_status`` in sync.

	Runs for every DocShare in the system, so bail out immediately for
	anything that is not a Note. Never raises: a status refresh must not be
	able to break sharing.
	"""
	if getattr(doc, "share_doctype", None) != "Note":
		return

	if method == "on_trash":
		# The row still exists here; after_delete recomputes once it is gone.
		return

	note = doc.get("share_name")
	if not note:
		return

	set_share_status(note)

	# A share row can grant or revoke a login popup for that user.
	invalidate_unseen_notes_on_share(
		doc,
		everyone_share=bool(doc.get("everyone")),
		user=doc.get("user") or getattr(doc, "shared_user", None),
	)


def set_status_on_note_insert(doc, method: str | None = None) -> None:
	"""``Note`` after_insert: seed the status field."""
	if getattr(doc, "doctype", None) != "Note":
		return
	set_share_status(doc.get("name"))


def backfill_share_status() -> int:
	"""Recompute ``share_status`` for every Note. Returns the number changed."""
	if not _has_status_column():
		return 0

	rows = frappe.db.sql(
		"""
		select
			n.name as name,
			n.public as public,
			n.`share_status` as share_status,
			count(s.name) as shares,
			coalesce(sum(case when s.everyone = 1 then 1 else 0 end), 0) as everyone_shares
		from `tabNote` n
		left join `tabDocShare` s
			on s.share_doctype = 'Note' and s.share_name = n.name
		group by n.name, n.public, n.`share_status`
		""",
		as_dict=True,
	)

	changed = 0
	for row in rows:
		if row.everyone_shares or row.public:
			status = PUBLIC
		elif row.shares:
			status = SHARED
		else:
			status = PRIVATE

		if row.share_status != status:
			frappe.db.set_value("Note", row.name, STATUS_FIELD, status, update_modified=False)
			changed += 1

	return changed


def reconcile_share_status() -> None:
	"""Daily safety net (restores, manual SQL, older backups)."""
	changed = backfill_share_status()
	if changed:
		frappe.logger("hksoho").info(f"Note share_status reconciled for {changed} note(s)")
