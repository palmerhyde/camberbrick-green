# Camberbrick Green

A mobile-first LEGO part manager. Photograph a piece to identify it, track where it's stored, browse your collection by category, and print shelf labels — all from your phone.

## Features

- **Photo identification** — point your phone camera at a part and Brickognize returns the most likely matches
- **Minifigure support** — minifigures are automatically detected from the scan and handled separately; browse your full minifigure collection grouped by theme on the dedicated Minifigures page
- **Home page cards** — two side-by-side cards show the most recently added minifigure and part; if nothing was added in the last 7 days, each falls back to a daily spotlight (deterministically seeded, stable within a day)
- **Collection tracking** — record which storage drawer or bag each part lives in
- **Inline location editing** — change a part's storage location from its detail page without navigating away
- **Parts library** — browse your entire collection by category and subcategory, sourced from BrickArchitect's taxonomy
- **Uncategorised parts** — parts not found in BrickArchitect's database are collected in a dedicated Uncategorised section so nothing gets lost
- **Label printing** — one-tap printing to a Brother PT-P710BT (P-Touch Cube Plus) on 24mm tape; labels are auto-patched from BrickArchitect's `.lbx` format
- **User-friendly names** — prefers BrickArchitect names ("Hammer Small") over the verbose Rebrickable equivalents
- **Fast navigation** — part metadata is cached on first view; repeat visits are served entirely from the local database

## Quick start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
Copy `.env.example` to `.env` and fill in your keys:
```
REBRICKABLE_API_KEY=your_key_here   # free at https://rebrickable.com/api/
```

### 3. Run
```bash
uvicorn main:app --reload
```

Open http://localhost:8000 in a browser, or on your phone via your machine's local IP (both must be on the same WiFi network):

```bash
# Find your local IP:
ipconfig getifaddr en0   # Mac
ipconfig                 # Windows

# Run accessible to your phone:
uvicorn main:app --reload --host 0.0.0.0
```

## Architecture

| Layer | Tech |
|---|---|
| Backend | Python + FastAPI |
| Database | SQLite |
| Frontend | Jinja2 templates + HTMX (no JS framework) |
| Part recognition | Brickognize API |
| Part metadata + images | Rebrickable API |
| Names, categories, labels | BrickArchitect |
| Label printing | Brother P-touch Editor + AppleScript |

## Storage philosophy

The system tracks **ownership and location**, not precise inventory counts:

- One Akro-Mils drawer holds one LEGO part type (no mixing)
- High-frequency parts → dedicated Akro-Mils drawers
- Long-tail parts → ziplock bag → subcategory bag → category shoebox

See `documents/vision.md` for the full product vision.

## Project structure

```
main.py                        # FastAPI app, startup backfill task
database.py                    # SQLite schema + connection helpers
print_label.applescript        # AppleScript: open .lbx and trigger print
requirements.txt

routers/
  identify.py                  # POST /identify — photo → part candidates
  parts.py                     # GET /part/{id} — detail page + metadata cache
  lookup.py                    # Collection lookup, add, inline location update
  collection.py                # Collection read helpers
  library.py                   # GET /parts — category/subcategory browsing
  minifigures.py               # GET /minifigures + /minifigure/{id} — minifigure browse and detail
  labels.py                    # POST /part/{id}/print-label — fetch, patch, print
  storage.py                   # Storage type management

templates/
  scan.html                    # Home — camera scan page
  part_detail.html             # Part detail with inline location select
  library*.html                # Parts library, category, subcategory pages
  parts_uncategorised.html     # Parts not found in BrickArchitect
  minifigures.html             # Minifigure collection grouped by theme
  minifigure_detail.html       # Minifigure detail with inline location select
  edit_part.html               # (Legacy) full-page location editor
  partials/                    # HTMX response fragments

static/
  style.css                    # Single stylesheet, mobile-first

documents/                     # Vision and architecture docs
```
