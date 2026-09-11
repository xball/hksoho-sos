# HKSoHo

Custom [Frappe](https://frappe.io) ERP application for **By Rydéns** sourcing operations — purchase orders, quality inspection, transport logistics, product master data, and legacy XPIN data migration.

| | |
|---|---|
| **Framework** | Frappe **v15** (bench currently on 15.77.x) |
| **App** | `hksoho` (tailor-made) |
| **Production site** | `sos.byrydens.com` |
| **Publisher** | [HKSoHo](mailto:paul@hksoho.net) |
| **License** | MIT |

Companion apps on this bench (not part of this repo): `print_designer`, `frappe_desk_theme`, `infintrix_theme`, `drive`.

## Modules

| Module | Path | Purpose |
|--------|------|---------|
| **byrydens** | `hksoho/byrydens/` | Core business logic — POs, QC, shipping, products, partners |
| **xpin** | `hksoho/xpin/` | Legacy XPIN DocTypes and one-off migration/import scripts |
| **HKSoHo** | `hksoho/hksoho/` | App shell DocTypes / shared placeholders |

Declared in `hksoho/modules.txt`.

## Features

### Purchase Order Management

- Purchase Order header with buyer, supplier, ports, delivery terms, QC/booking status
- PO is **not** submittable (`is_submittable = 0`); lifecycle is driven by **PO-Workflow** on the live site (not exported as app fixtures)
- Line-level quantity tracking: requested → confirmed → booked → delivered → remaining
- PO types: Standard, Sample, New Item, Spareparts
- Automatic totals, ship-week calculation, and ship-date propagation to lines
- QC status tracking per line (`qc_accepted_qty`, `qc_rejected_qty`, `qc_update_status`)
- Hourly CSV import from legacy XPIN flat files on FTP (updates allowed only when workflow is `Draft` or `Submitted`)
- Manual single-PO reload from FTP (`reload_single_po_from_txt`)
- Reverse sync to **Pyramid ERP** — exports `.txt` files when `sync_back_pyramid` is enabled (skips `Draft`)
- Email notification **`PO notify`** — live site uses event **Value Change** (repo export still says `Submit`; do not rely on Submit)
- **Reports:** PO Detail, PO Normal List, Undelivered Items, Orders Due to Pay
- **Workspace:** Purchase Orders

**PO-Workflow states (live):** Draft → Submitted → Supplier Confirmed → Ready to QC → QC Checked → Ready to Ship → Booked QTY → Partial Shipout → Shipout → Rejected / Cancelled

### Quality Inspection

- Reusable **Inspection Templates** with checklist items in four categories: Carton, Construction, Product, Shade
- Per-line **Inspection** records with AQL qty, pass/fail, reinspection flag, and template results
- **Inspection Events** — schedule multi-PO inspections with calendar view and child line rows
- **Item Inspection Wizard** web form for guided field QC entry (supplier → PO → line → checklist) — **published on live**; repo JSON may show `published: 0`
- Live site also has **`item-inspection-wizard2`** (site-only; not in the app tree)
- Email invitations to inspectors with `.ics` calendar attachments
- Hourly timezone-aware reminder emails to inspectors
- Daily job auto-completes event lines when matching Inspection records exist
- API to increment accepted qty on PO lines after inspection (`update_qc_accepted_qty`)
- **Reports:** Inspection Report -A
- **Workspace:** Purchase Orders (inspection shortcuts)

### Transport & Logistics

- **Transport Order** header with forwarder, vessel, container, ETD/ETA, booking
- Lifecycle driven by **TO-Workflow** on the live site (not exported as app fixtures)
- **Transport Order Line** — shipped PO lines with qty, vendor invoice fields, and SEK exchange rates
- **Vessels** and **Vessels Time Table** — sailing schedules (CFS close, ETD, ETA, free days)
- **Load Dest Port** reference data
- APIs to pick ready-to-ship / partial-shipout PO lines, batch-update invoice fields, and sync vessel dates to PO ship dates
- Transport web forms exist in the app but are **unpublished on live**
- **Reports:** Shipment On Water Report with status (canonical). Legacy JS-only tree `hksoho/report/shipment_on_water_report` is incomplete — do not use
- **Workspace:** Transports

**TO-Workflow states (live):** Unconfirmed → Empty TO Head → Confirmed → Shipped → ETA Passed → Arrived → Undelivered → Delivered / Cancelled

### Products & Article Master

- **Product** catalog with dimensions, packaging, tariff codes, supplier, and primary image
- **Product Attachment** — multi-file attachments linkable to multiple products
- **Article Master** — detailed lighting specifications (lampholder, bulb, cable, shade, certifications)
- **Customer Quotation** and **Internal Evaluation** — cost build-up worksheets (freight, customs, royalty, selling price)
- Sync product images, CBM, weight, and HS code from Product to PO lines
- Hourly product CSV import from FTP (uses `partner_import_*` site_config keys — naming is historical)
- Supplier-scoped product visibility APIs (`get_supplier_allowed_articles`, etc.)
- Embedded PO history on Product form (current system + legacy XPIN)
- **Reports:** Supplier Products
- **Workspace:** Products

### Partners & Master Data

- Unified **Partner** DocType: Supplier, Buyer, Customer, Agent/Buyer, Transporter
- FSC/BSCI compliance tracking
- **Payment Term**, **Delivery Term**, and **Currency Rate** reference tables
- Hourly partner and currency CSV imports from FTP
- **Workspace:** Partners

### Legacy XPIN Data

- Separate DocTypes preserving historical POs, order items, inspection records, and file attachments
- Excel and batch import tooling for one-time migration
- Cross-reference APIs on Product form for legacy PO line history
- **Workspace:** XPIN

## Workspaces

| Workspace | Key shortcuts |
|-----------|---------------|
| Partners | Partner, roles, permissions |
| Products | Product, Product Attachment, Article Master, Customer Quotation, Internal Evaluation |
| Purchase Orders | PO list, Inspection wizard, Inspection list, Inspection Event calendar, Undelivered Items |
| Transports | Transport Order, Vessels, Vessels Time Table, TO Details |
| Reports | Orders Due To Pay, Shipment On Water, Undelivered Items |
| Utilities | ToDo, Drive, Note |
| XPIN | XPIN PO, XPIN Files, XPIN Inspection Items |

## Integrations

### Microsoft 365 Email

Outbound email is routed through Microsoft Graph API using OAuth credentials in `site_config.json` (key names only — never commit secrets):

- `ms365_client_id`
- `ms365_client_secret`
- `ms365_tenant_id`
- `ms365_user_email`

Implementation: `hksoho/utils/ms365_smtp_wrapper.py`, `hksoho/utils/email_utils.py`

### Pyramid ERP (export)

When a Purchase Order is saved with `sync_back_pyramid` enabled (and not `Draft`), the app generates `B{sequence}.txt` flat files.

Hardcoded output dirs in `purchase_order.py` (not site-config driven):

- `/home/ftpuser/topyramid`
- `/home/frappe/topyramid`

### XPIN FTP Import (hourly)

Flat-file imports from directories configured in `site_config.json` (defaults shown):

| Config keys | Default | Used by |
|-------------|---------|---------|
| `partner_import_input_dir` / `partner_import_proceed_dir` / `partner_import_image_dir` | `/home/ftpuser/ftp`, `/home/ftpuser/done`, `/home/ftpuser/ftp/img` | Product, partner, product-group, primary photo |
| `po_import_input_dir` / `po_import_proceed_dir` | `/home/ftpuser/ftp`, `/home/ftpuser/done` | PO import |
| `currency_import_input_dir` / `currency_import_proceed_dir` | `/home/ftpuser/ftp`, `/home/ftpuser/done` | Currency rates |

| Source file | Target |
|-------------|--------|
| `xpin_products.txt` | Product, Product Group |
| `xpin_supplier.txt`, `xpin_customer.txt`, `xpin_forwarder.txt` | Partner |
| `xpin_currency.txt` | Currency Rate |
| `po*.txt` | Purchase Order + Items |

Import scripts: `hksoho/byrydens/importing/`. Product-group helper: `import_csv2pgroup.py` (manual / supporting; not on the hourly scheduler).

### Object storage (XPIN PO files)

Production stores large XPIN PO file trees under site private files, commonly backed by S3-compatible storage (e.g. Lightsail/S3 bucket linked under `private/files/xpin/po`). Configure outside the app; **never store credentials in the repo or bench markdown files**.

## Scheduled Jobs

Configured in `hksoho/hooks.py`:

| Schedule | Job |
|----------|-----|
| Hourly | `import_csv2product.execute` |
| Hourly | `import_csv2partner.execute` |
| Hourly | `import_csv2currency.execute` |
| Hourly | `import_csv2po.execute` |
| Hourly | `utils.send_daily_inspection_reminders` |
| Daily | `inspection_check.execute` (Inspection Event line completion sync) |

## Custom APIs

Whitelisted server methods used by web forms and desk UI:

| Module | Key methods |
|--------|-------------|
| `inspection_api.py` | `get_suppliers`, `get_po_items`, `get_po_items_qcstatus`, `add_po_items_to_inspection_event`, `send_inspection_invitation`, `update_qc_accepted_qty` |
| `transport_order_api.py` | `get_po_items`, `update_to_line_invoice`, `update_vessel_dates`, maintenance helpers `fix_po_item_order_status_*` (treat as destructive; prefer dry-run) |
| `product_files_api.py` | `get_product_attachments`, `link_attachments_to_products`, `get_po_items_for_product`, `get_xpin_po_items_for_product`, supplier visibility helpers |
| `utils.py` | `load_product_images_to_po_items`, `make_product_images_public`, `get_due_po_details`, `get_image_datauri` (Jinja) |
| `import_csv2po.py` | `reload_single_po_from_txt` |
| `xpin/import_xpin_po.py` | `import_xpin_po_from_xlsx` |

## Web Forms

| Web Form | DocType | Route | Live publish |
|----------|---------|-------|--------------|
| Item Inspection Wizard | Inspection | `item-inspection-wizard` | **Published** on live (repo export may say 0) |
| item-inspection-wizard2 | Inspection | `item-inspection-wizard2` | **Published** on live; **site-only** (not in app) |
| Transport Order Detail | Transport Order | `transport-order-detail` | Unpublished on live |
| Transport Order 2 Detail | Transport Order | `transport-order2-detail` | Unpublished on live |

Folder name `transport-order-detial` is a historical typo.

## Desk UI assets

- CSS: `/assets/hksoho/css/custom2.css` (included via `app_include_css` in `hooks.py`)
- JS: `hksoho/public/js/hksoho.js`

## Installation

Requires a Frappe v15 bench:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch main
bench --site your-site install-app hksoho
bench build --app hksoho
bench restart
```

**Note:** Active Workflows (`PO-Workflow`, `TO-Workflow`), live Notification event, and published web forms live primarily in the **site DB**. There are no fixtures in `hooks.py` — a fresh install will not recreate production workflow/notification/publish state automatically.

## Configuration

Add the following to your site or common `site_config.json` as needed (values are secrets — keep out of git):

```json
{
  "ms365_client_id": "...",
  "ms365_client_secret": "...",
  "ms365_tenant_id": "...",
  "ms365_user_email": "...",
  "partner_import_input_dir": "/home/ftpuser/ftp",
  "partner_import_proceed_dir": "/home/ftpuser/done",
  "partner_import_image_dir": "/home/ftpuser/ftp/img",
  "po_import_input_dir": "/home/ftpuser/ftp",
  "po_import_proceed_dir": "/home/ftpuser/done",
  "currency_import_input_dir": "/home/ftpuser/ftp",
  "currency_import_proceed_dir": "/home/ftpuser/done"
}
```

## Production safety

This app runs on a live production site. Prefer minimal, reversible changes. **Take a site backup before any database-related work** (DocType/schema, patches, fixtures, SQL, migrations):

```bash
bench --site sos.byrydens.com backup
# or with files:
bench --site sos.byrydens.com backup --with-files
```

See also [SPEC.md](SPEC.md) for the full technical inventory.

## Known issues

High / ops (needs explicit approval to change production):

- Plaintext cloud credentials must not live in bench markdown (e.g. avoid committing key material under the bench root)
- Production `developer_mode` should normally be off unless actively customizing
- `fix_po_item_order_status_for_shipped_to(dry_run=False)` mutates by default — safer default is `True`

Medium (documented; code fix only if approved):

- Orphan incomplete report client under `hksoho/report/shipment_on_water_report/`
- Duplicate `'Undelivered'` in Transport Order `read_only_depends_on`
- PO FTP import skips states beyond `Draft`/`Submitted`
- Pyramid export paths hardcoded; product import reuses `partner_import_*` key names
- Workflows / notification publish state not fixture-exported; app git may be dirty vs `upstream/main`

## Contributing

```bash
cd apps/hksoho
pre-commit install
```

Tools: ruff, eslint, prettier, pyupgrade

## License

MIT
