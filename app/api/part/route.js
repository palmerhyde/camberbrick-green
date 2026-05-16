/**
 * GET /api/part?id=3001
 * Fetches part details from Rebrickable (name, image URL, category).
 */
export async function GET(request) {
  const { searchParams } = new URL(request.url)
  const partId = searchParams.get('id')

  if (!partId) {
    return Response.json({ error: 'No part id provided' }, { status: 400 })
  }

  const apiKey = process.env.REBRICKABLE_API_KEY
  if (!apiKey || apiKey === 'your_key_here') {
    console.error('REBRICKABLE_API_KEY missing or invalid:', apiKey)
    return Response.json({
      error: 'REBRICKABLE_API_KEY not set in .env.local',
      debug: apiKey ? 'API key appears to be placeholder or empty' : 'API key is undefined',
      cwd: process.cwd(),
      nodeEnv: process.env.NODE_ENV,
    }, { status: 500 })
  }

  async function getBrickArchitectCategory(partId) {
    try {
      const res = await fetch(`https://brickarchitect.com/parts/${partId}`)
      if (!res.ok) return ''
      const html = await res.text()
      const navMatch = html.match(/<div class="chapternav">([\s\S]*?)<\/div>/i)
      if (!navMatch) return ''
      const anchors = [...navMatch[1].matchAll(/<a[^>]*>([^<]+)<\/a>/gi)].map(m => m[1].trim())
      if (anchors.length <= 1) return ''
      return anchors.slice(1).join(' › ')
    } catch (err) {
      console.error('BrickArchitect category fetch error:', err)
      return ''
    }
  }

  try {
    const res = await fetch(
      `https://rebrickable.com/api/v3/lego/parts/${partId}/`,
      {
        headers: {
          Authorization: `key ${apiKey}`,
          Accept: 'application/json',
        },
      }
    )

    if (!res.ok) {
      return Response.json({ error: 'Part not found', status: res.status }, { status: 404 })
    }

    const data = await res.json()
    const rebrickableCategory = data.part_category?.name || data.part_cat_name || data.part_category || data.category || ''
    const brickarchitectCategory = await getBrickArchitectCategory(partId)
    const category = brickarchitectCategory || rebrickableCategory

    return Response.json({
      id: data.part_num,
      name: data.name,
      category,
      rebrickableCategory,
      brickarchitectCategory,
      imgUrl: data.part_img_url,
      partUrl: data.part_url,
      brickarchitectUrl: `https://brickarchitect.com/parts/${data.part_num}`,
    })
  } catch (err) {
    console.error('Part fetch error:', err)
    return Response.json({ error: err.message }, { status: 500 })
  }
}
