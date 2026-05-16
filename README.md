# Brick Finder

LEGO collection manager — photograph a piece, check if you have it, find where it's stored.

## Quick start

### 1. Install dependencies
```bash
npm install
```

### 2. Add your Rebrickable API key
Get a free key at https://rebrickable.com/api/ (takes ~1 minute)

Edit `.env.local`:
```
REBRICKABLE_API_KEY=your_actual_key_here
```

### 3. Run
```bash
npm run dev
```

Open http://localhost:3000 on your computer,
**or** open http://YOUR_LOCAL_IP:3000 on your phone
(e.g. http://192.168.1.5:3000 — find your IP with `ipconfig` / `ifconfig`)

## How to access from your phone

Both devices must be on the same WiFi network. Then:
```bash
# Find your machine's local IP:
ipconfig getifaddr en0   # Mac
ipconfig                 # Windows (look for IPv4)
```

Then browse to `http://<your-ip>:3000` on your phone.

## What's real vs stubbed

| Feature | Status |
|---|---|
| Photo → Brickognize identify | ✅ Real API |
| Part image + name | ✅ Real (Rebrickable) |
| Collection check | ✅ Real (in-memory, pre-seeded with 3001 + 3710) |
| Add to collection | ✅ Real (in-memory) |
| Label download (.lbx) | ✅ Real (links to BrickArchitect) |
| Persistent storage | ⏳ Next step — swap lib/collection.js for SQLite |

## Pre-seeded demo parts
- **3001** (2×4 Brick) → location A3, qty 47
- **3710** (1×4 Plate) → location B7, qty 12

Try scanning and then manually entering `3024` to see the "new part" flow.

## Next steps
1. Replace `lib/collection.js` with `better-sqlite3`
2. Add BrickArchitect category scraping to `/api/part`
3. Add collection list / browse screen
4. Wire up Brother printer via P-Touch SDK
