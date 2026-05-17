# Camberbrick Green — UI Redesign Spec
## Phases 5, 6, 7

---

## Context

Camberbrick Green is a local-first LEGO collection management app built with FastAPI + SQLite + Jinja2 + HTMX. It runs on a laptop and is used from a phone browser over local Wi-Fi.

The primary workflow:
1. Take a photo of a LEGO part on your phone
2. Brickognize identifies it → top 3 candidates shown
3. Tap the correct part → app checks collection
4. If found: shows storage location
5. If not found: lets you add it with a storage type

The goal is to make the app look and feel like **BrickArchitect's Parts Guide** (https://brickarchitect.com/parts/), which is the reference taxonomy the entire physical storage system is based on.

---

## What BrickArchitect looks like (design reference)

Observed from https://brickarchitect.com/parts/ and https://brickarchitect.com/parts/3001:

### Visual language
- **Background**: Pure white everywhere. Very light grey (#f5f5f5) for alternating/inset sections
- **Text**: Near-black (#111–#222) for headings and body. Medium grey (#777–#999) for metadata, IDs, secondary labels
- **Accent colour**: Minimal — almost no colour used. Links are a muted blue
- **No heavy UI chrome**: No dark buttons, no thick borders, no card shadows. Separation is achieved with whitespace and very light rules
- **Typography**: Clean sans-serif, strong size hierarchy. Part names are large and prominent. Part numbers/IDs are small and grey, printed below the name
- **Feel**: Reference publication, not an app. Encyclopaedic. Information-dense but never cluttered

### Category index page
- Grid of category cards (2–3 across)
- Each card: representative LEGO part image + category name in bold + one-line description
- 12 top-level categories: Basic, Wall, SNOT, Angle, Curve, Articulation, Minifig, Nature, Vehicle, Technic, Electronics, DUPLO

### Part grid (subcategory level)
- Dense image-first grid, 2–4 columns depending on screen width
- Each card: square part image (white background, no border) + part number below in grey + name below that
- Minimal chrome — no outlines, no buttons on the card itself
- Tap the card to go to part detail

### Part detail page
- Breadcrumb navigation at top: `← Parts Guide › Basic › Brick › 2×4 Brick`
- Large centred part image
- Part title prominently: `2×4 Brick (Part 3001)`
- Date range indicator: `1954–2026 CURRENT`
- Statistics section: ranking, piece count, sets, available colours
- External links: LEGO Pick a Brick, BrickLink, Rebrickable, Brickset, LDraw
- Printable Brother label templates with QR codes

---

## Current state of the codebase (after Phases 5 + 6)

### Tech stack
- **Backend**: Python 3, FastAPI, Jinja2 templates, SQLite
- **Frontend**: Plain HTML + HTMX (htmx.org v2.0.3) + a single `static/style.css`
- **No JS framework** — HTMX handles all dynamic UI via HTML fragment swaps
- **Mobile-first**, max-width 480px shell

### File structure
```
main.py                      # FastAPI app entry point + lifespan
database.py                  # SQLite schema, seed, + full BA taxonomy seed
requirements.txt
static/
  style.css                  # All CSS (single file, BA design language)
routers/
  identify.py                # POST /identify → Brickognize → _candidates.html
  lookup.py                  # POST /lookup, POST /add-part, GET+POST /part/{id}/edit
  parts.py                   # GET /part/{id} — JSON only (Rebrickable + BA enrichment)
  collection.py              # GET/POST/PATCH /collection + DB helpers
  storage.py                 # GET/POST /storage CRUD
  library.py                 # GET /library, /library/{cat}, /library/{cat}/{sub}
templates/
  base.html                  # Shell with HTMX script
  scan.html                  # Main scan screen (camera + manual lookup)
  library.html               # Category index — 2-col BA category grid
  library_category.html      # Subcategory list within a category
  library_subcategory.html   # 2-col part image grid within a subcategory
  edit_part.html             # Edit part storage location
  storage.html               # Storage type management
  preview.html               # Static-only preview (served by preview_server.js on port 8001)
  partials/
    _candidates.html         # 3 Brickognize match cards (HTMX response)
    _result.html             # Found-in-collection result (HTMX response)
    _not_found.html          # Not-in-collection + add form (HTMX response)
    _added.html              # Confirmation after adding (HTMX response)
    _error.html              # Error state (HTMX response)
```

### Database schema
```sql
storage_types  (id, name, code, photo_path, purchase_url, notes, sort_order)
parts          (part_id, name, known_owned, brickognize_name, img_url, created_at, updated_at)
categories     (id, name)
subcategories  (id, category_id, name)
locations      (id, code, type, description, storage_type_id)
part_categories (part_id, category_id, subcategory_id)
part_locations  (part_id, location_id, role, qty)
```

### Key design decisions
- **No quantity tracking in UI** — qty column exists in DB but is never shown. "In collection or not" is the only state that matters
- **BrickArchitect is the only category system** — Rebrickable is used for part name and image only, never for category. If BA does not return a category, it is left blank. Never fall back to Rebrickable's taxonomy
- **Auto-submit on photo selection** — no separate "Identify" button tap needed
- **Location = storage type** — no individual drawer/slot tracking yet. The BA category tells you where in the unit to look
- **Storage type short codes** (AL, AS, etc.) are shown in all UI instead of full names
- **Category mapping saved on add** — when a new part is added via `/add-part`, the BA breadcrumb string (e.g. `Basic › Brick`) is parsed and saved to `part_categories`. Parts added before Phase 6 have no category mapping and won't appear in the category browse — they are only in the flat collection

---

## Phase 5 — Visual overhaul ✅ COMPLETE

**What was done**: Full rewrite of `static/style.css` to match BA's editorial design language, plus corresponding template updates across all 9 templates.

### CSS design system (key classes)

**Layout**
- `.shell` — max-width 480px centred container, thin side borders (#e0e0e0)
- `.screen` — page wrapper, no top-level padding (each section handles its own)
- `.site-header` — top bar with `.site-name` (🧱 CAMBERBRICK, uppercase) and `.site-header-links`
- `.breadcrumb` — `Home › Category › Current` nav bar with `.breadcrumb-sep` and `.breadcrumb-current`
- `.page-header` — section below breadcrumb with `.page-title` (22px bold) and `.page-subtitle` (13px grey)
- `.page-content` — generic padded content area (1.25rem sides)

**Part hero** (used on result, not-found, edit screens)
- `.part-hero` — centred layout (not side-by-side). Image above, text below
- `.part-hero-img` — 128×128px, object-fit contain, centred
- `.part-hero-img-fallback` — 128×128px emoji fallback
- `.part-number` — small grey caps e.g. `PART #3001`
- `.part-title` — 21px bold, centred
- `.part-category-line` — 13px grey, centred

**Status section**
- `.status-section` — padded block with bottom border
- `.status-badge` — small green caps `✓ IN YOUR COLLECTION`. Add `.new` for amber "not found" variant
- `.location-code` — 36px bold, the storage code (e.g. AL)
- `.location-name` — 13px grey, full storage type name

**Buttons**
- `.btn-primary` — outlined dark (#111 border + fill), white text — clearly tappable but not heavy
- `.btn-secondary` — light border (#d0d0d0), white fill
- `.btn-ghost` — no border, grey text
- `.link-btn` — blue text link, `.muted` variant for grey

**Candidates**
- `.candidate-list` — flex column, top border
- `.candidate-card` — full-width button, bottom border separator (no card border)
- `.candidate-part-num`, `.candidate-name`, `.candidate-score`, `.candidate-chevron`

**Library list** (still used for edit_part context)
- `.part-list` / `.part-card` — flex rows with bottom border separators
- `.part-thumb` / `.part-thumb-fallback`, `.part-card-info`, `.part-card-meta`
- `.storage-badge` — bold storage code. `.empty` variant for grey dash

**Forms**
- `.field-label` — small grey uppercase label
- `.field-input` — 1px border, 4px radius, no outline on focus (border changes colour)
- `.upload-zone` — dashed border, light grey bg, tap to open camera
- `.manual-row` + `.manual-input` + `.manual-btn`

**Other**
- `.error-banner` — left red border, no background fill
- `.message-banner` — light green bg for success messages
- `.loading-center` / `.spinner` / `.loading-text`
- `.empty-state` — centred grey placeholder text

### Template structure (all screens)

Every page now has this shell:
```
.site-header    ← CAMBERBRICK branding + nav links
.breadcrumb     ← Home › ... › Current (on sub-pages)
.page-header    ← page title + subtitle
[content]       ← varies by page
```

HTMX partials (in `partials/`) replace `.shell` innerHTML so they include the full site-header + breadcrumb themselves.

---

## Phase 6 — Category-based library ✅ COMPLETE

**What was done**: Replaced the flat `/library` part list with a 3-level browse hierarchy (Category → Subcategory → Part grid). Full BA taxonomy seeded into the DB.

### Routes (in `routers/library.py`)

```
GET /library                       → category index (library.html)
GET /library/{cat_slug}            → subcategory list (library_category.html)
GET /library/{cat_slug}/{sub_slug} → part image grid (library_subcategory.html)
```

### Category slug mapping

Defined as `BA_CATEGORIES` in `routers/library.py`. Slugs are stable (used in URLs):

| Slug | Name |
|------|------|
| basic | Basic |
| wall | Wall |
| snot | SNOT |
| angle | Angle |
| curve | Curve |
| articulation | Articulation |
| minifig | Minifig |
| nature | Nature |
| vehicle | Vehicle |
| technic | Technic |
| electronics | Electronics |
| duplo | DUPLO |

Subcategory slugs are generated dynamically with `_sub_slug(name)` → lowercase, hyphens.

### Taxonomy seeded (in `database.py`)

`_seed_taxonomy()` runs on every startup via `init_db()`. Uses `INSERT OR IGNORE` — safe on existing databases. Seeds all 12 categories and their subcategories:

```
Basic:        Brick, Plate, Tile, Slope, Wedge, Round, Arch,
              Modified Brick, Modified Plate, Modified Tile
Wall:         Panel, Window, Door, Fence
SNOT:         Bracket, Modified Brick, Modified Plate
Angle:        Hinge, Turntable, Swivel Plate
Curve:        Arch, Dome, Cylinder
Articulation: Ball Joint, Bar & Clip, Tow Ball, Pin & Connector
Minifig:      Head, Torso, Leg, Accessory, Hair & Hat, Visor & Helmet
Nature:       Plant, Animal, Rock & Ground
Vehicle:      Wheel & Tyre, Axle & Mudguard, Cockpit & Windscreen, Hull & Body
Technic:      Beam, Connector, Gear, Pin & Axle, Panel & Plate
Electronics:  Brick & Hub, Light, Motor & Servo
DUPLO:        Brick, Figure, Animal & Nature, Vehicle & Accessory
```

### Category mapping helper

`_upsert_part_category(conn, part_id, category_str)` in `routers/collection.py`:
- Parses a BA breadcrumb string like `"Basic › Brick"` into category_id + subcategory_id
- Upserts into `part_categories` (ON CONFLICT replaces)
- Called from `add_part` in `routers/lookup.py` whenever a new part is added

### CSS additions (to `static/style.css`)

```
.category-grid       — 2-col CSS grid, border-separated cells
.category-card       — each category tile (name + count)
.category-card-count — grey by default, .has-parts = green
.subcat-list         — flex column
.subcat-row          — name + count + › chevron
.part-grid           — 2-col CSS grid
.part-grid-card      — image + part number + name
.part-grid-img-wrap  — square aspect-ratio image container
.part-grid-storage   — absolute-positioned storage code badge overlay
.part-grid-num       — small grey part number
.part-grid-name      — 13px bold name
```

---

## Phase 7 — Part detail page

**Goal**: Replace the HTMX `_result.html` partial with a proper full-page part detail that matches BA's layout. Make `/part/{id}` the canonical page for any part.

### What needs to change

1. **Part detail page** (`/part/{id}`) — currently returns JSON. Convert to an HTML page:
   - Full `.site-header` + `.breadcrumb`: `Home › Library › Basic › Brick › 2×4 Brick`
   - The breadcrumb should use the stored `part_categories` data to build `Library › {cat} › {sub}`
   - Large centred part image (from `img_url` stored in DB, or Rebrickable)
   - Part title + number prominent (same `.part-hero` pattern)
   - Storage location shown clearly: `.location-code` (e.g. AL) + `.location-name` (full name)
   - Collection status: `✓ In collection` or `⊕ Not in collection` (with link to add)
   - External links row: BrickLink, Rebrickable, BrickArchitect (small grey links)
   - "Edit location" link → `/part/{id}/edit`

2. **Scan result flow update** — `_result.html` and `_not_found.html` currently replace the full shell via HTMX. After adding a part (or when looking up a known part), redirect to `/part/{id}` instead of showing the inline partial. Options:
   - Use an HTMX `HX-Redirect` response header to push to `/part/{id}` after lookup/add
   - Or keep the partials for the immediate HTMX response but add a "View full detail" link to `/part/{id}`
   - The simpler option (recommended for Phase 7): keep partials as-is, add a prominent link from `_result.html` to `/part/{id}`, and build the full detail page independently

3. **The `/part/{id}` route** currently lives in `routers/parts.py` and returns JSON. It needs to:
   - Check if the part is in the local collection (via `_get_part_with_location`)
   - If yes: show stored name, image, location, category
   - If no: fetch from Rebrickable (existing `get_part` logic) + show "not in collection" state
   - Render `part_detail.html`

### Template to create: `templates/part_detail.html`

This is a full-page template (extends `base.html`), not a partial. It should use the existing Phase 5 CSS classes throughout.

---

## Starting instructions for a new session (Phase 7)

1. Read `documents/vision.md` for the product philosophy
2. Read `documents/redesign-spec.md` (this file) for full context — Phases 5 and 6 are complete, start on Phase 7
3. Read `main.py` to understand the current route structure
4. Read `routers/parts.py` — this is where `/part/{id}` lives (currently returns JSON, needs to become HTML)
5. Read `routers/lookup.py` — `_result.html` and `_not_found.html` partials are served from here; the scan flow HTMX wiring is here
6. Read `templates/partials/_result.html` — understand what the current found-part screen shows
7. Read `static/style.css` for the full CSS design system before writing any new HTML
8. Do not use any JS frameworks or CSS frameworks — plain CSS only
9. Keep HTMX wiring intact — the scan flow must keep working
10. The reference site is https://brickarchitect.com/parts/3001 for the part detail page design
