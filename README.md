# HKSoHo

Custom [Frappe](https://frappe.io) ERP application for **By Rydéns** sourcing operations — purchase orders, quality inspection, transport logistics, product master data, and legacy XPIN data migration.

Built on **Frappe v15** by [HKSoHo](mailto:paul@hksoho.net).

## Modules

| Module | Purpose |
|--------|---------|
| **byrydens** | Core business logic — POs, QC, shipping, products, partners |
| **xpin** | Legacy XPIN data model and one-off migration/import scripts |
| **HKSoHo** | App shell and shared utilities |

## Features

### Purchase Order Management

- Purchase Order header with buyer, supplier, ports, delivery terms, QC/booking status, and workflow states
- Line-level quantity tracking: requested → confirmed → booked → delivered → remaining
- PO types: Standard, Sample, New Item, Spareparts
- Automatic totals, ship-week calculation, and ship-date propagation to lines
- QC status tracking per line (`qc_accepted_qty`, `qc_rejected_qty`, `qc_update_status`)
- Hourly CSV import from legacy XPIN flat files on FTP
- Manual single-PO reload from FTP (`reload_single_po_from_txt`)
- Reverse sync to **Pyramid ERP** — exports `.txt` files when `sync_back_pyramid` is enabled
- Email notification on PO submit (`PO notify`)
- **Reports:** PO Detail, PO Normal List, Undelivered Items, Orders Due to Pay
- **Workspace:** Purchase Orders

### Quality Inspection

- Reusable **Inspection Templates** with checklist items in four categories: Carton, Construction, Product, Shade
- Per-line **Inspection** records with AQL qty, pass/fail, reinspection flag, and template results
- **Inspection Events** — schedule multi-PO inspections with calendar view and child line rows
- **Item Inspection Wizard** web form for guided field QC entry (supplier → PO → line → checklist)
- Email invitations to inspectors with `.ics` calendar attachments
- Hourly timezone-aware reminder emails to inspectors
- Daily job auto-completes event lines when matching Inspection records exist
- API to increment accepted qty on PO lines after inspection (`update_qc_accepted_qty`)
- **Reports:** Inspection Report -A, Inspection Detail (workspace)
- **Workspace:** Purchase Orders (inspection shortcuts)

### Transport & Logistics

- **Transport Order** header with forwarder, vessel, container, ETD/ETA, booking, and workflow
- **Transport Order Line** — shipped PO lines with qty, vendor invoice fields, and SEK exchange rates
- **Vessels** and **Vessels Time Table** — sailing schedules (CFS close, ETD, ETA, free days)
- **Load Dest Port** reference data
- Workflow states: Empty TO Head, Unconfirmed, Confirmed, Ready to Ship, Partial Shipout, Shipped, ETA Passed, Arrived, Undelivered, Delivered
- APIs to pick ready-to-ship PO lines, batch-update invoice fields, and sync vessel dates to PO ship dates
- Web forms for external transport order data entry
- **Reports:** Shipment on Water Report with Status, TO Details (workspace)
- **Workspace:** Transports

### Products & Article Master

- **Product** catalog with dimensions, packaging, tariff codes, supplier, and primary image
- **Product Attachment** — multi-file attachments linkable to multiple products
- **Article Master** — detailed lighting specifications (lampholder, bulb, cable, shade, certifications)
- **Customer Quotation** and **Internal Evaluation** — cost build-up worksheets (freight, customs, royalty, selling price)
- Sync product images, CBM, weight, and HS code from Product to PO lines
- Hourly product CSV import from FTP
- Embedded PO history on Product form (current system + legacy XPIN)
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

## Workspaces

| Workspace | Key shortcuts |
|-----------|---------------|
| Partners | Partner, roles, permissions |
| Products | Product, Product Attachment, Article Master, Customer Quotation, Internal Evaluation |
| Purchase Orders | PO list, Inspection wizard, Inspection list, Inspection Event calendar, Undelivered Items |
| Transports | Transport Order, Vessels, Vessels Time Table, TO Details report |

## Integrations

### Microsoft 365 Email

Outbound email is routed through Microsoft Graph API using OAuth credentials in `site_config.json`:

- `ms365_client_id`
- `ms365_client_secret`
- `ms365_tenant_id`
- `ms365_user_email`

Implementation: `hksoho/utils/ms365_smtp_wrapper.py`, `hksoho/utils/email_utils.py`

### Pyramid ERP (export)

When a Purchase Order is saved with `sync_back_pyramid` enabled, the app generates `B{sequence}.txt` flat files and writes them to the Pyramid FTP folder and a local copy.

Implementation: `hksoho/byrydens/doctype/purchase_order/purchase_order.py`

### XPIN FTP Import (hourly)

Flat-file imports from a configured FTP directory:

| Source file | Target |
|-------------|--------|
| `xpin_products.txt` | Product, Product Group |
| `xpin_supplier.txt`, `xpin_customer.txt`, `xpin_forwarder.txt` | Partner |
| `xpin_currency.txt` | Currency Rate |
| `po*.txt` | Purchase Order + Items |

Import scripts live under `hksoho/byrydens/importing/`.

## Scheduled Jobs

| Schedule | Job |
|----------|-----|
| Hourly | Product, partner, currency, and PO CSV imports |
| Hourly | Inspection reminder emails (timezone-aware) |
| Daily | Inspection Event status sync — marks lines completed when Inspection records exist |

Configured in `hksoho/hooks.py`.

## Custom APIs

Whitelisted server methods used by web forms and desk UI:

| API module | Key methods |
|------------|---------------|
| `inspection_api.py` | `get_suppliers`, `get_po_items`, `add_po_items_to_inspection_event`, `send_inspection_invitation`, `update_qc_accepted_qty` |
| `transport_order_api.py` | `get_po_items`, `update_to_line_invoice`, `update_vessel_dates` |
| `product_files_api.py` | `get_product_attachments`, `link_attachments_to_products`, `get_po_items_for_product`, `get_xpin_po_items_for_product` |
| `utils.py` | `load_product_images_to_po_items`, `get_due_po_details`, `get_image_datauri` (Jinja) |

## Installation

Requires a Frappe v15 bench:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch main
bench --site your-site install-app hksoho
bench build --app hksoho
bench restart
```

## Configuration

Add the following to your site or common `site_config.json` as needed:

```json
{
  "ms365_client_id": "...",
  "ms365_client_secret": "...",
  "ms365_tenant_id": "...",
  "ms365_user_email": "..."
}
```

FTP import directories are configured per import script (default: `/home/ftpuser/ftp`).

## Contributing

This app uses `pre-commit` for code formatting and linting:

```bash
cd apps/hksoho
pre-commit install
```

Tools: ruff, eslint, prettier, pyupgrade

## License

MIT
