import { getAllParts } from '../../../lib/collection'

// GET /api/library → list all parts in the local collection
export async function GET() {
  return Response.json({ parts: getAllParts() })
}
