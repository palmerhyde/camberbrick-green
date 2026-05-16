# Camberbrick Green — Brick Discovery Application MVP

## Overview

Camberbrick Green Brick Discovery is a local-first web application for managing LEGO part discovery, categorization, storage, and retrieval.

The system is designed around a core operational question:

> Do we own this LEGO part, and where should it be stored?

This is **not** intended to be a precise inventory/counting application.

The system prioritizes:

- discoverability
- retrieval ergonomics
- low-friction intake
- semantic search
- physical storage guidance
- progressive intelligence growth

rather than:

- exact inventory accounting
- color-perfect stock management
- retail-style inventory systems

---

# Core Philosophy

## Canonical Truth

The application primarily tracks:

```text
part_id exists? yes/no
```

along with:

```text
where does it belong?
where is it stored?
what category is it?
```

Exact quantities and colors are intentionally deprioritized for MVP.

---

# Physical Storage Philosophy

## Existing Storage Systems

Current physical storage includes:

- 4 × Akro-Mils 64-drawer units
- 4 × Akro-Mils 24-drawer units
- plastic shoe boxes by Brick Architect top-level category
- ziplock bags by subcategory
- smaller ziplocks by individual part
- optional overflow bags
- possible future binder-based long-tail storage

---

# Hard Operational Rules

## Rule 1 — One Drawer = One Part

```text
One Akro-Mils drawer may only contain one LEGO part.
```

Previous experiments with mixed-part drawers created retrieval friction and poor ergonomics.

This rule is considered foundational.

---

## Rule 2 — Density Determines Storage Tier

### High-frequency / high-volume parts

Stored in:

```text
Akro-Mils drawers
```

### Overflow Quantity

Stored separately as:

```text
overflow reserve
```

### Low-density / Long-tail Parts

Stored in:

```text
part ziplock
→ subcategory bag
→ category shoe box
```

---

# Long-Tail Binder Concept

Potential future storage tier:

```text
binders with multi-pocket flexible pages
```

Purpose:

- discoverability
- semantic browsing
- visual memory
- collection completion
- long-tail organization

Potential categories:

- minifig tools
- accessories
- weapons
- articulation
- clips/bars
- decorative parts
- printed tiles

---

# Product Vision

This project is fundamentally:

```text
LEGO Memory Infrastructure
```

rather than:

```text
LEGO Inventory Accounting
```

The goal is to externalize collection memory.

---

# Brick Discovery Workflow

## Primary Scan Workflow

```text
Take photo on phone
→ send image to backend
→ backend sends image to Brickognize
→ Brickognize returns candidate matches
→ user confirms correct part
→ app checks local registry
```

---

# Known Part Flow

If the part already exists:

```text
Show:
- part ID
- part name
- category/subcategory
- storage locations
- overflow locations
```

---

# Unknown Part Flow

If the part is unknown:

```text
Confirm Brickognize match
→ create new part
→ assign Brick Architect category/subcategory
→ assign storage location
→ optionally print label
→ save forever
```

---

# BrickLink Seed Import

Only the part ID matters.

Seed logic:

```text
For each ITEM:
  if ITEMTYPE == "P":
    create/update part
    known_owned = true
```

Ignore:
- color
- quantity
- condition

for ownership purposes.

---

# Brick Architect Taxonomy

Top-level categories:

```text
Basic
Wall
SNOT
Angle
Curve
Articulation
Minifig
Nature
Vehicle
Technic
Electronics
DUPLO
```

Maintain taxonomy locally as:

```text
brick_architect_taxonomy.json
```

---

# Progressive Mapping Philosophy

```text
Seed known parts aggressively
Refine categories lazily
Learn from real usage
```

---

# Suggested Technical Stack

## Backend

```text
Python
FastAPI
```

## Database

```text
SQLite
```

## Frontend

```text
Simple mobile-first HTML
Optional HTMX
```

## Recognition

```text
Brickognize
```

## Future Metadata

```text
Rebrickable
```

---

# Mobile-First Development

```text
Laptop = local server
Phone = real client
```

Use native mobile browser camera support:

```html
<input type="file" accept="image/*" capture="environment">
```

---

# Recommended Database Schema

```sql
CREATE TABLE parts (
    part_id TEXT PRIMARY KEY,
    name TEXT,
    known_owned BOOLEAN DEFAULT 1,
    brickognize_name TEXT,
    created_at TEXT,
    updated_at TEXT
);
```

```sql
CREATE TABLE categories (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);
```

```sql
CREATE TABLE subcategories (
    id INTEGER PRIMARY KEY,
    category_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    UNIQUE(category_id, name)
);
```

```sql
CREATE TABLE locations (
    id INTEGER PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    type TEXT NOT NULL,
    description TEXT
);
```

```sql
CREATE TABLE part_categories (
    part_id TEXT PRIMARY KEY,
    category_id INTEGER,
    subcategory_id INTEGER
);
```

```sql
CREATE TABLE part_locations (
    part_id TEXT NOT NULL,
    location_id INTEGER NOT NULL,
    role TEXT DEFAULT 'primary',
    notes TEXT,
    PRIMARY KEY (part_id, location_id)
);
```

---

# Recommended Location Types

```text
akro_drawer
shoebox
subcategory_bag
part_bag
overflow_bag
binder
binder_page
binder_pocket
tray
temporary
```

---

# Future Features

- Brother label printing
- semantic search
- Rebrickable enrichment
- Stud.io integration
- build readiness analysis
- AI conversational search
- MQTT sorting/factory automation
- binder ontology navigation

---

# Key Design Principle

The application should feel like:

```text
an intelligent LEGO workshop assistant
```

not:

```text
an ERP inventory system
```
