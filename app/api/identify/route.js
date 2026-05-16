/**
 * POST /api/identify
 * Accepts multipart form data with an image file,
 * proxies it to Brickognize, returns the top matches.
 */
export async function POST(request) {
  try {
    const formData = await request.formData()
    const image = formData.get('image')

    if (!image) {
      return Response.json({ error: 'No image provided' }, { status: 400 })
    }

    // Forward to Brickognize
    const brickognizeForm = new FormData()
    brickognizeForm.append('query_image', image)

    const res = await fetch('https://api.brickognize.com/predict/', {
      method: 'POST',
      headers: { accept: 'application/json' },
      body: brickognizeForm,
    })

    if (!res.ok) {
      const text = await res.text()
      console.error('Brickognize error:', res.status, text)
      return Response.json({ error: 'Brickognize request failed', detail: text }, { status: 502 })
    }

    const data = await res.json()

    // Brickognize returns { items: [{ id, name, score, img_url }, ...] }
    return Response.json(data)
  } catch (err) {
    console.error('Identify error:', err)
    return Response.json({ error: err.message }, { status: 500 })
  }
}
