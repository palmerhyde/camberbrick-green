"""
Build Anki flashcard decks for learning Brick Architect part categories.

Scrapes all parts from BrickArchitect, then produces three .apkg deck files:
  - anki_easy.apkg   — front: image, back: top-level category (e.g. "BASIC")
  - anki_medium.apkg — front: image, back: level-2 category (e.g. "Basic › Brick")
  - anki_hard.apkg   — front: image, back: full breadcrumb (e.g. "Basic › Brick › 1× Brick")

Images are served directly from BrickArchitect's CDN — no Rebrickable API key needed.

Usage:
    pip install genanki httpx
    python3 scripts/build_anki_decks.py
    # Produces anki_easy.apkg, anki_medium.apkg, anki_hard.apkg in current directory.
    # Upload each to https://ankiweb.net/decks/ to study on any device.
"""

import asyncio
import hashlib
import re
import time
from pathlib import Path
from dataclasses import dataclass, field

import httpx
import genanki

# ── Configuration ─────────────────────────────────────────────────────────────

BA_BASE    = "https://brickarchitect.com"
IMG_BASE   = f"{BA_BASE}/content/cache/parts/normal/50"
OUT_DIR    = Path(".")
RATE_LIMIT = 0.15   # seconds between requests — be polite to BA's server
TIMEOUT    = 15

# All top-level BA categories (slug → display name)
CATEGORIES = {
    "category-1":   "BASIC",
    "category-2":   "WALL",
    "category-7":   "ANGLE",
    "category-8":   "CURVE",
    "category-3":   "SNOT",
    "category-106": "ARTICULATION",
    "category-10":  "MINIFIG",
    "category-11":  "NATURE",
    "category-9":   "VEHICLE",
    "category-12":  "TECHNIC",
    "category-13":  "ELECTRONICS",
    "category-89":  "DUPLO",
}

# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class Part:
    part_id:   str
    name:      str
    img_url:   str
    cat_l1:    str   # e.g. "Basic"
    cat_l2:    str   # e.g. "Basic › Brick"
    cat_l3:    str   # e.g. "Basic › Brick › 1× Brick"  (may equal cat_l2 if no level 3)


# ── Scraping ──────────────────────────────────────────────────────────────────

async def fetch(client: httpx.AsyncClient, url: str) -> str:
    """Fetch a URL with retries."""
    for attempt in range(3):
        try:
            res = await client.get(url, timeout=TIMEOUT, follow_redirects=True)
            if res.status_code == 200:
                return res.text
            print(f"  HTTP {res.status_code} for {url}")
            return ""
        except Exception as e:
            if attempt == 2:
                print(f"  Failed {url}: {e}")
                return ""
            await asyncio.sleep(1)
    return ""


def parse_parts_from_category_page(html: str, top_level_name: str) -> list[Part]:
    """
    Parse a BA category page. Returns Part objects with full breadcrumb.

    The page structure nests h2 (level-2) and h3 (level-3) category names,
    followed by .parts_results blocks containing part links and images.
    We walk through the HTML linearly, tracking the current h2/h3 context.
    """
    parts: list[Part] = []

    # Split on part containers to interleave header context
    # Strategy: find all h2/h3 category headers and part entries, in document order.
    tokens = re.split(
        r'(<h[23] class="partcategoryname"[^>]*>.*?</h[23]>|<a href="https://brickarchitect\.com/parts/[^"]+">.*?</a>)',
        html,
        flags=re.DOTALL,
    )

    current_l2 = top_level_name
    current_l3 = top_level_name

    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue

        # Category header
        h_match = re.match(r'<h(\d) class="partcategoryname"', tok)
        if h_match:
            level = int(h_match.group(1))
            # Extract the last <a> text in the header (avoids the parent breadcrumb text)
            names = re.findall(r'<a[^>]*>([^<]+)</a>', tok)
            cat_name = names[-1].strip() if names else ""
            if level == 2:
                current_l2 = f"{top_level_name} › {cat_name}"
                current_l3 = current_l2   # reset l3 until we see an h3
            elif level == 3:
                current_l3 = f"{current_l2} › {cat_name}"
            continue

        # Part link
        part_match = re.match(r'<a href="https://brickarchitect\.com/parts/([^"]+)">', tok)
        if not part_match:
            continue
        part_id = part_match.group(1)
        # Skip non-part links (e.g. category pages)
        if not re.match(r'^[0-9]', part_id):
            continue

        # Image
        img_match = re.search(r'<img[^>]+src="([^"]+)"', tok)
        img_url = img_match.group(1) if img_match else f"{IMG_BASE}/{part_id}.png"

        # Name (partname div)
        name_match = re.search(r'<div class="partname">([^<]+)</div>', tok)
        name = name_match.group(1).strip() if name_match else part_id

        parts.append(Part(
            part_id=part_id,
            name=name,
            img_url=img_url if img_url.startswith("http") else f"{BA_BASE}{img_url}",
            cat_l1=top_level_name,
            cat_l2=current_l2,
            cat_l3=current_l3,
        ))

    return parts


async def scrape_all_parts() -> list[Part]:
    """Scrape every category page and return deduplicated parts."""
    all_parts: list[Part] = []
    seen: set[str] = set()

    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0 (compatible; AnkiBuilder/1.0)"}) as client:
        for cat_slug, cat_name in CATEGORIES.items():
            url = f"{BA_BASE}/parts/{cat_slug}"
            print(f"Scraping {cat_name} ({cat_slug})…")
            html = await fetch(client, url)
            if not html:
                print(f"  Skipped — no response")
                continue

            parts = parse_parts_from_category_page(html, cat_name.title())
            new_parts = [p for p in parts if p.part_id not in seen]
            seen.update(p.part_id for p in new_parts)
            all_parts.extend(new_parts)
            print(f"  {len(new_parts)} parts (running total: {len(all_parts)})")
            await asyncio.sleep(RATE_LIMIT)

    return all_parts


# ── Image downloading ─────────────────────────────────────────────────────────

async def download_images(parts: list[Part]) -> dict[str, bytes]:
    """Download all part images concurrently (with throttle). Returns part_id → image bytes."""
    results: dict[str, bytes] = {}
    semaphore = asyncio.Semaphore(10)

    async def _get(client: httpx.AsyncClient, part: Part):
        async with semaphore:
            try:
                res = await client.get(part.img_url, timeout=TIMEOUT)
                if res.status_code == 200:
                    results[part.part_id] = res.content
            except Exception as e:
                print(f"  Image failed {part.part_id}: {e}")

    print(f"\nDownloading {len(parts)} images…")
    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
        tasks = [_get(client, p) for p in parts]
        # Process in chunks to show progress
        chunk = 100
        for i in range(0, len(tasks), chunk):
            await asyncio.gather(*tasks[i:i+chunk])
            print(f"  {min(i+chunk, len(tasks))}/{len(tasks)} images fetched")

    print(f"  {len(results)} images downloaded successfully")
    return results


# ── Anki deck generation ──────────────────────────────────────────────────────

def stable_id(seed: str) -> int:
    """Deterministic integer ID from a string (Anki requires integers)."""
    return int(hashlib.md5(seed.encode()).hexdigest()[:8], 16)


CARD_CSS = """
.card {
    font-family: -apple-system, Arial, sans-serif;
    font-size: 18px;
    text-align: center;
    background: #fff;
    color: #222;
}
.part-img { max-width: 250px; max-height: 250px; margin: 20px auto; display: block; }
.part-id  { font-size: 12px; color: #888; margin-top: 4px; }
.category { font-size: 22px; font-weight: bold; margin-top: 20px; color: #1a1a8c; }
.breadcrumb { font-size: 14px; color: #555; margin-top: 6px; }
"""

FRONT_TMPL = "{{FrontSide}}"

FRONT_HTML = """
<img class="part-img" src="{{Image}}">
<div class="part-id">Part #{{PartID}} — {{PartName}}</div>
<br>
<em>What category is this part in?</em>
"""

def back_html(answer_field: str, show_full_breadcrumb: bool = False) -> str:
    crumb = '<div class="breadcrumb">{{FullBreadcrumb}}</div>' if show_full_breadcrumb else ""
    return f"""
{{{{FrontSide}}}}
<hr>
<div class="category">{{{{{{answer_field}}}}}}</div>
{crumb}
"""


def build_deck(
    name: str,
    parts: list[Part],
    images: dict[str, bytes],
    answer_field: str,
    show_breadcrumb: bool,
    deck_seed: str,
) -> genanki.Package:
    model = genanki.Model(
        stable_id(f"ba-model-{deck_seed}"),
        f"BrickArchitect {name}",
        fields=[
            {"name": "PartID"},
            {"name": "PartName"},
            {"name": "Image"},
            {"name": "Category"},
            {"name": "L2Category"},
            {"name": "FullBreadcrumb"},
        ],
        templates=[{
            "name": "Category card",
            "qfmt": FRONT_HTML,
            "afmt": back_html(answer_field, show_breadcrumb),
        }],
        css=CARD_CSS,
    )

    deck = genanki.Deck(stable_id(f"ba-deck-{deck_seed}"), f"LEGO Parts — {name}")
    media_files = []

    for part in parts:
        img_bytes = images.get(part.part_id)
        if not img_bytes:
            continue   # skip parts with no image

        # Save image to a temp file that genanki will bundle
        img_filename = f"ba_{part.part_id}.png"
        img_path = Path("/tmp") / img_filename
        img_path.write_bytes(img_bytes)
        media_files.append(str(img_path))

        note = genanki.Note(
            model=model,
            fields=[
                part.part_id,
                part.name,
                img_filename,
                part.cat_l1,
                part.cat_l2,
                part.cat_l3,
            ],
            guid=genanki.guid_for(f"ba-{deck_seed}-{part.part_id}"),
        )
        deck.add_note(note)

    pkg = genanki.Package(deck)
    pkg.media_files = media_files
    return pkg


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    print("=== Brick Architect Anki Deck Builder ===\n")

    # 1. Scrape
    parts = await scrape_all_parts()
    print(f"\nTotal unique parts scraped: {len(parts)}")

    # Show category breakdown
    from collections import Counter
    l1_counts = Counter(p.cat_l1 for p in parts)
    print("\nParts per top-level category:")
    for cat, count in sorted(l1_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")

    # 2. Download images
    images = await download_images(parts)

    # Filter to parts with images
    parts_with_images = [p for p in parts if p.part_id in images]
    print(f"\nParts with images: {len(parts_with_images)}")

    # 3. Build decks
    print("\nBuilding Anki decks…")

    configs = [
        ("Easy — Top-Level Category",   "Category",     False, "easy"),
        ("Medium — Level 2 Category",   "L2Category",   True,  "medium"),
        ("Hard — Full Breadcrumb",       "FullBreadcrumb", False, "hard"),
    ]

    for deck_name, answer_field, show_crumb, seed in configs:
        pkg = build_deck(deck_name, parts_with_images, images, answer_field, show_crumb, seed)
        out_path = OUT_DIR / f"anki_{seed}.apkg"
        pkg.write_to_file(str(out_path))
        note_count = len([p for p in parts_with_images if p.part_id in images])
        print(f"  ✓ {out_path}  ({note_count} cards)")

    print("\nDone! Upload the .apkg files to https://ankiweb.net/decks/")
    print("Start with anki_easy.apkg, then progress to medium and hard.")


if __name__ == "__main__":
    asyncio.run(main())
