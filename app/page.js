'use client'
import { useState, useRef, useCallback } from 'react'
import Link from 'next/link'
import styles from './page.module.css'

const SCREENS = { SCAN: 'scan', SCANNING: 'scanning', RESULT: 'result', ADD: 'add' }

export default function Home() {
  const [screen, setScreen] = useState(SCREENS.SCAN)
  const [showManual, setShowManual] = useState(false)
  const [manualId, setManualId] = useState('')
  const [preview, setPreview] = useState(null)
  const [result, setResult] = useState(null)   // { part, collection, matches }
  const [error, setError] = useState(null)
  const [addForm, setAddForm] = useState({ qty: 1, location: '' })
  const [saving, setSaving] = useState(false)
  const fileRef = useRef()

  const reset = useCallback(() => {
    setScreen(SCREENS.SCAN)
    setPreview(null)
    setResult(null)
    setError(null)
    setManualId('')
    if (fileRef.current) fileRef.current.value = ''
  }, [])

  const handleFile = (e) => {
    const file = e.target.files[0]
    if (!file) return
    setPreview(URL.createObjectURL(file))
  }

  const identify = async (imageFile) => {
    setScreen(SCREENS.SCANNING)
    setError(null)
    try {
      const fd = new FormData()
      fd.append('image', imageFile)
      const res = await fetch('/api/identify', { method: 'POST', body: fd })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Identification failed')

      // Brickognize returns { items: [{id, name, score, img_url}, ...] }
      const topMatch = data.items?.[0]
      if (!topMatch) throw new Error('No matches found — try a clearer photo')

      await loadPartResult(topMatch.id, topMatch.name, Math.round(topMatch.score * 100))
    } catch (err) {
      setError(err.message)
      setScreen(SCREENS.SCAN)
    }
  }

  const lookupManual = async () => {
    const id = manualId.trim()
    if (!id) return
    setScreen(SCREENS.SCANNING)
    setError(null)
    try {
      await loadPartResult(id, null, null)
    } catch (err) {
      setError(err.message)
      setScreen(SCREENS.SCAN)
    }
  }

  const loadPartResult = async (partId, fallbackName, confidence) => {
    // Run part info + collection check in parallel
    const [partRes, collectionRes] = await Promise.all([
      fetch(`/api/part?id=${partId}`),
      fetch(`/api/collection?id=${partId}`),
    ])

    const partData = partRes.ok ? await partRes.json() : { id: partId, name: fallbackName || partId, imgUrl: null }
    const collectionData = await collectionRes.json()

    setResult({
      part: partData,
      collection: collectionData,
      confidence,
    })
    setAddForm({ qty: 1, location: '' })
    setScreen(SCREENS.RESULT)
  }

  const saveToCollection = async () => {
    setSaving(true)
    try {
      const res = await fetch('/api/collection', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: result.part.id,
          name: result.part.name,
          qty: addForm.qty,
          location: addForm.location,
          category: result.part.category || '',
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error)
      // Refresh collection status
      setResult(r => ({ ...r, collection: { found: true, part: data.part } }))
      setScreen(SCREENS.RESULT)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const updateQty = async (newQty) => {
    await fetch('/api/collection', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: result.part.id, qty: newQty }),
    })
    setResult(r => ({ ...r, collection: { ...r.collection, part: { ...r.collection.part, qty: newQty } } }))
  }

  return (
    <div className={styles.shell}>
      {/* ── SCAN ── */}
      {screen === SCREENS.SCAN && (
        <div className={styles.screen}>
          <header className={styles.header}>
            <span className={styles.headerIcon}>🧱</span>
            <h1 className={styles.headerTitle}>Brick Finder</h1>
          </header>

          {error && <div className={styles.errorBanner}>{error}</div>}

          {!preview ? (
            <div className={styles.uploadZone} onClick={() => fileRef.current.click()}>
              <div className={styles.uploadIcon}>📷</div>
              <p className={styles.uploadPrimary}>Tap to photograph a piece</p>
              <p className={styles.uploadSecondary}>Point camera at the LEGO part</p>
            </div>
          ) : (
            <>
              <img src={preview} alt="Preview" className={styles.preview} />
              <button
                className={styles.btnPrimary}
                onClick={() => identify(fileRef.current.files[0])}
              >
                Identify this piece
              </button>
              <button className={styles.btnSecondary} onClick={reset}>
                Clear
              </button>
            </>
          )}

          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            capture="environment"
            style={{ display: 'none' }}
            onChange={handleFile}
          />

          <div className={styles.dividerRow}>
            <span className={styles.dividerLine} />
            <span className={styles.dividerText}>or</span>
            <span className={styles.dividerLine} />
          </div>

          {!showManual ? (
            <button className={styles.linkBtn} onClick={() => setShowManual(true)}>
              Enter part number manually
            </button>
          ) : (
            <div className={styles.manualRow}>
              <input
                className={styles.manualInput}
                type="text"
                placeholder="e.g. 3001"
                value={manualId}
                onChange={e => setManualId(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && lookupManual()}
                autoFocus
              />
              <button className={styles.manualBtn} onClick={lookupManual}>
                Look up
              </button>
            </div>
          )}

          <Link href="/library" className={styles.linkBtn}>
            Browse your library
          </Link>
        </div>
      )}

      {/* ── SCANNING ── */}
      {screen === SCREENS.SCANNING && (
        <div className={styles.screen}>
          <div className={styles.loadingCenter}>
            <div className={styles.spinner} />
            <p className={styles.loadingText}>Identifying piece…</p>
            <p className={styles.loadingSubtext}>Checking Brickognize + your collection</p>
          </div>
        </div>
      )}

      {/* ── RESULT ── */}
      {screen === SCREENS.RESULT && result && (
        <div className={styles.screen}>
          <header className={styles.header}>
            <button className={styles.backBtn} onClick={reset} aria-label="Back">←</button>
            <h1 className={styles.headerTitle}>Part details</h1>
          </header>

          {/* Part hero */}
          <div className={styles.partHero}>
            <div className={styles.partImgBox}>
              {result.part.imgUrl
                ? <img src={result.part.imgUrl} alt={result.part.name} className={styles.partImg} />
                : <span className={styles.partImgFallback}>🧱</span>
              }
            </div>
            <div className={styles.partHeroInfo}>
              <p className={styles.partId}>Part #{result.part.id}</p>
              <p className={styles.partName}>{result.part.name}</p>
              {result.part.category && <p className={styles.partCategory}>Category: {result.part.category}</p>}
              {result.confidence && (
                <div className={styles.confidenceRow}>
                  <div className={styles.confidenceBar}>
                    <div className={styles.confidenceFill} style={{ width: `${result.confidence}%` }} />
                  </div>
                  <span className={styles.confidenceLabel}>{result.confidence}%</span>
                </div>
              )}
              <a
                href={`https://brickarchitect.com/parts/${result.part.id}`}
                target="_blank"
                rel="noreferrer"
                className={styles.extLink}
              >
                BrickArchitect ↗
              </a>
            </div>
          </div>

          {/* Collection status */}
          {result.collection.found ? (
            <div className={styles.statusFound}>
              <p className={styles.statusLabel}>✓ In your collection</p>
              <p className={styles.locationBig}>📦 {result.collection.part.location}</p>
              <div className={styles.qtyRow}>
                <span className={styles.qtyLabel}>Qty:</span>
                <button className={styles.qtyBtn} onClick={() => updateQty(Math.max(0, result.collection.part.qty - 1))}>−</button>
                <span className={styles.qtyValue}>{result.collection.part.qty}</span>
                <button className={styles.qtyBtn} onClick={() => updateQty(result.collection.part.qty + 1)}>+</button>
              </div>
            </div>
          ) : (
            <div className={styles.statusNew}>
              <p className={styles.statusLabel}>✦ New to your collection</p>
              <p className={styles.statusSub}>Not yet in your inventory</p>
            </div>
          )}

          {/* Actions */}
          <div className={styles.actions}>
            {!result.collection.found && (
              <button className={styles.btnPrimary} onClick={() => setScreen(SCREENS.ADD)}>
                + Add to collection
              </button>
            )}
            <a
              href={`https://brickarchitect.com/label/${result.part.id}.lbx`}
              className={styles.btnSecondary}
              style={{ textAlign: 'center', display: 'block' }}
            >
              🖨 Download label (.lbx)
            </a>
            <button className={styles.btnGhost} onClick={reset}>
              Scan another piece
            </button>
          </div>
        </div>
      )}

      {/* ── ADD TO COLLECTION ── */}
      {screen === SCREENS.ADD && result && (
        <div className={styles.screen}>
          <header className={styles.header}>
            <button className={styles.backBtn} onClick={() => setScreen(SCREENS.RESULT)} aria-label="Back">←</button>
            <h1 className={styles.headerTitle}>Add to collection</h1>
          </header>

          <div className={styles.addCard}>
            <p className={styles.addPartName}>{result.part.name}</p>
            <p className={styles.partId}>Part #{result.part.id}</p>
            {result.part.category && <p className={styles.partCategory}>{result.part.category}</p>}
          </div>

          <label className={styles.fieldLabel}>Storage location</label>
          <input
            className={styles.fieldInput}
            type="text"
            placeholder="e.g. A3, B12, Drawer 4"
            value={addForm.location}
            onChange={e => setAddForm(f => ({ ...f, location: e.target.value }))}
            autoFocus
          />

          <label className={styles.fieldLabel}>Quantity</label>
          <div className={styles.qtyPicker}>
            <button className={styles.qtyBtn} onClick={() => setAddForm(f => ({ ...f, qty: Math.max(1, f.qty - 1) }))}>−</button>
            <span className={styles.qtyValue}>{addForm.qty}</span>
            <button className={styles.qtyBtn} onClick={() => setAddForm(f => ({ ...f, qty: f.qty + 1 }))}>+</button>
          </div>

          {error && <div className={styles.errorBanner}>{error}</div>}

          <button
            className={styles.btnPrimary}
            onClick={saveToCollection}
            disabled={!addForm.location || saving}
            style={{ marginTop: '1.5rem' }}
          >
            {saving ? 'Saving…' : 'Save to collection'}
          </button>
        </div>
      )}
    </div>
  )
}
