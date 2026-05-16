/**
 * Simple in-memory collection store for prototyping.
 * Replace with SQLite (better-sqlite3) for the real app.
 *
 * Schema:
 *   parts: { [partId]: { id, name, qty, location, category, addedAt } }
 */

// Seed with a couple of demo parts so the "found" flow works immediately
const collection = {
  '3001': { id: '3001', name: '2×4 Brick', qty: 47, location: 'A3', category: 'Basic › Brick › 2× Brick', addedAt: new Date().toISOString() },
  '3710': { id: '3710', name: '1×4 Plate', qty: 12, location: 'B7', category: 'Plates › Basic Plates › 1× Plate', addedAt: new Date().toISOString() },
}

export function getPart(id) {
  return collection[id] || null
}

export function addPart(part) {
  collection[part.id] = { ...part, addedAt: new Date().toISOString() }
  return collection[part.id]
}

export function updateQty(id, qty) {
  if (collection[id]) {
    collection[id].qty = qty
    return collection[id]
  }
  return null
}

export function getAllParts() {
  return Object.values(collection)
}
