import { getPart, addPart, updateQty, getAllParts } from '../../../lib/collection'

// GET /api/collection?id=3001  → check if a part is in collection
// GET /api/collection           → list all parts
export async function GET(request) {
  const { searchParams } = new URL(request.url)
  const id = searchParams.get('id')
  if (id) {
    const part = getPart(id)
    return Response.json({ found: !!part, part })
  }
  return Response.json({ parts: getAllParts() })
}

// POST /api/collection  { id, name, qty, location, category }
export async function POST(request) {
  const body = await request.json()
  const { id, name, qty, location, category } = body
  if (!id || !location) {
    return Response.json({ error: 'id and location are required' }, { status: 400 })
  }
  const part = addPart({ id, name: name || id, qty: qty || 1, location, category: category || '' })
  return Response.json({ part })
}

// PATCH /api/collection  { id, qty }
export async function PATCH(request) {
  const { id, qty } = await request.json()
  const part = updateQty(id, qty)
  if (!part) return Response.json({ error: 'Part not found' }, { status: 404 })
  return Response.json({ part })
}
