# Camberbrick Green

LEGO part discovery, categorisation, and storage management — photograph a piece, check if you own it, find where it lives.

## Quick start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Add your Rebrickable API key
Get a free key at https://rebrickable.com/api/ (takes ~1 minute)

Edit `.env`:
```
REBRICKABLE_API_KEY=your_actual_key_here
```

### 3. Run
```bash
uvicorn main:app --reload
```

Open http://localhost:8000 on your computer,
**or** open http://YOUR_LOCAL_IP:8000 on your phone
(e.g. http://192.168.1.5:8000 — find your IP with `ipconfig` / `ifconfig`)

## How to access from your phone

Both devices must be on the same WiFi network. Then:
```bash
# Find your machine's local IP:
ipconfig getifaddr en0   # Mac
ipconfig                 # Windows (look for IPv4)
```

Then run with host binding so your phone can reach it:
```bash
uvicorn main:app --reload --host 0.0.0.0
```

## Architecture

| Layer | Tech |
|---|---|
| Backend | Python + FastAPI |
| Database | SQLite |
| Frontend | Jinja2 templates + HTMX |
| Part recognition | Brickognize |
| Part metadata | Rebrickable |
| Category taxonomy | Brick Architect |

## Storage philosophy

The system tracks **ownership and location**, not precise inventory:

- One Akro-Mils drawer = one LEGO part (no mixing)
- High-frequency parts → Akro-Mils drawers
- Long-tail parts → ziplock bag → subcategory bag → category shoebox

See `documents/vision.md` for the full product vision.

## Pre-seeded demo parts
- **3001** (2×4 Brick) → location A3, qty 47
- **3710** (1×4 Plate) → location B7, qty 12

## Project structure

```
main.py                  # FastAPI app entry point
database.py              # SQLite schema + connection helper
requirements.txt
routers/                 # API route handlers
templates/               # Jinja2 HTML templates
static/                  # CSS
data/                    # SQLite database (gitignored)
documents/               # Vision and architecture docs
```
