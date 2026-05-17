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

The app is currently functional but looks like a generic mobile app. The owner wants it to look and feel like **BrickArchitect's Parts Guide** (https://brickarchitect.com/parts/), which is the reference taxonomy the entire physical storage system is based on.

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

## What Camberbrick Green currently has

### Tech stack
- **Backend**: Python 3, FastAPI, Jinja2 templates, SQLite
- **Frontend**: Plain HTML + HTMX (htmx.org v2.0.3) + a single `static/style.css`
- **No JS framework** — HTMX handles all dynamic UI via HTML fragment swaps
- **Mobile-first**, max-width 480px shell

### File structure
```
main.py                    # FastAPI app, page routes
database.py                # SQLite schema + seed
requirements.txt
static/
  style.css                # All CSS (single file)
routers/
  identify.py              # POST /identify → Brickognize → _candidates.html
  lookup.py                # POST /lookup, POST /add-part, GET+POST /part/{id}/edit
  parts.py                 # GET /part/{id} (Rebrickable + BrickArchitect enrichment)
  collection.py            # GET/POST/PATCH /collection
  storage.py               # GET/POST /storage CRUD
templates/
  base.html                # Shell with HTMX script
  scan.html                # Main scan screen (camera + manual lookup)
  library.html             # Flat part list (current)
  edit_part.html           # Edit part storage location
  storage.html             # Storage type management
  partials/
    _candidates.html       # 3 Brickognize match cards (HTMX response)
    _result.html           # Found-in-collection result (HTMX response)
    _not_found.html        # Not-in-collection + add form (HTMX response)
    _added.html            # Confirmation after adding (HTMX response)
    _error.html            # Error state (HTMX response)
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

### Storage types (user-configured)
| Code | Name |
|------|------|
| AL | Akro-Mils 64-drawer |
| AS | Akro-Mils 24-drawer |
| BB | Bead boxes |
| SS | Shoe boxes |
| OF | Overflow |

Storage types are managed by the user at `/storage`. The seeding only runs when the table is empty — never overwrites user data.

### Key design decisions made so far
- **No quantity tracking in UI** — qty column exists in DB but is hidden everywhere. "In collection or not" is the only state that matters for now
- **BrickArchitect category is the only category system** — Rebrickable is used for part name and image only, never for category. If BrickArchitect does not return a category for a part, the category is left blank. Never fall back to Rebrickable's taxonomy
- **Auto-submit on photo selection** — no extra "Identify" button tap needed
- **Location = storage type** — no individual drawer/slot tracking yet. The BA category tells you where in the unit to look
- **Storage type short codes** (AL, AS, etc.) shown in library and result screens instead of full name

---

## Redesign Plan

### Phase 5 — Visual overhaul (CSS + typography)

**Goal**: Make the existing screens look like BrickArchitect without changing any routes or data flows.

**What changes**:
- Rewrite `static/style.css` with BA's design language:
  - White backgrounds, light grey for inset sections
  - Dark text, grey metadata
  - No heavy dark buttons — use lighter outlined or text-style buttons
  - Remove thick card borders → use whitespace + very light 1px rules
  - Editorial typography: larger part names, smaller grey IDs
  - Breadcrumb-style header navigation (› separators)
- Update all templates to use new class names / structure
- Keep all HTMX wiring intact — this is purely visual

**Does not change**: routes, DB schema, HTMX behaviour, any business logic

---

### Phase 6 — Category-based library

**Goal**: Replace the flat part list with a BA-style browse hierarchy: Category → Subcategory → Part grid.

**What changes**:

1. **Category index** (`/library`):
   - 12 BA category tiles in a grid (2-wide on mobile)
   - Each tile shows: category name + count of owned parts in that category
   - Tapping a category goes to subcategory view

2. **Subcategory view** (`/library/basic`, `/library/snot`, etc.):
   - List of subcategories within that category
   - Each shows owned part count
   - Tapping goes to part grid

3. **Part grid** (`/library/basic/brick`):
   - 2-column image grid (BA style)
   - Each card: part image (square, white bg) + part number + name
   - ✓ badge + storage code overlay on owned parts
   - Tapping goes to part detail

4. **DB changes needed**:
   - Seed the full BA taxonomy (12 categories × N subcategories) into `categories` / `subcategories`
   - Ensure `part_categories` is populated on add/edit

**Requires**: seeding the full taxonomy, new route hierarchy, new templates for each level

---

### Phase 7 — Part detail page

**Goal**: Replace the HTMX `_result.html` partial with a proper full-page part detail that matches BA's layout.

**What changes**:

1. **Part detail page** (`/part/{id}`):
   - Breadcrumb: `← Library › Basic › Brick › 2×4 Brick`
   - Large centred part image (from Rebrickable or Brickognize)
   - Part title + number prominent
   - BA category breadcrumb fetched live
   - Storage location shown clearly (code + full storage type name)
   - Collection status badge (✓ In collection / ⊕ Add to collection)
   - External links: BrickLink, Rebrickable, BrickArchitect
   - "Edit location" link

2. **Scan result flow update**:
   - After identifying + confirming a candidate, navigate to `/part/{id}` instead of showing the HTMX partial
   - Keeps the detail page as the canonical view for any part

---

## Starting instructions for a new session

1. Read `documents/vision.md` for the product philosophy
2. Read `documents/redesign-spec.md` (this file) for the full context and plan
3. The codebase is at the repo root — read `main.py`, `static/style.css`, and the templates to understand the current state before making changes
4. Start with **Phase 5** (visual overhaul) — it is self-contained and does not require DB or route changes
5. The reference site is https://brickarchitect.com/parts/ — the goal is to match its aesthetic: white, editorial, image-forward, reference-publication feel
6. Do not use any JS frameworks or CSS frameworks (no Tailwind, no Bootstrap) — plain CSS only, matching the current approach
7. Keep HTMX wiring intact throughout — the scan flow must continue to work
