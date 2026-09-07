import { useState } from 'react'
import './App.css'

const API = 'http://127.0.0.1:8000'
const SAMPLE = 'https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_272x92dp.png'

function Cards({ items }) {
  if (!items || items.length === 0) return <p className="empty">No matches.</p>
  return (
    <div className="grid">
      {items.map((r, i) => (
        <div className="card" key={i}>
          {r.thumbnail_url ? (
            <img src={r.thumbnail_url} alt={r.title || ''} loading="lazy" />
          ) : (
            <div className="nothumb">no thumb</div>
          )}
          <div className="body">
            <div className="rank">#{r.rank}</div>
            <div className="title">{r.title || 'Untitled'}</div>
            <div className="domain">{r.domain || ''}</div>
            {r.url && (
              <a href={r.url} target="_blank" rel="noreferrer">Open →</a>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function App() {
  const [imageUrl, setImageUrl] = useState(SAMPLE)
  const [filePreview, setFilePreview] = useState(null)
  const [engine, setEngine] = useState('both')
  const [amount, setAmount] = useState(20)
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [tab, setTab] = useState('all')

  function onFile(e) {
    const f = e.target.files?.[0]
    if (f) setFilePreview(URL.createObjectURL(f))
  }

  async function search() {
    if (!imageUrl) return
    setLoading(true)
    setError(null)
    setData(null)
    try {
      const res = await fetch(`${API}/api/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_url: imageUrl, engine, amount: Number(amount) }),
      })
      if (!res.ok) throw new Error(`Backend ${res.status}`)
      setData(await res.json())
    } catch (e) {
      setError(`Search failed: ${e.message}. Is backend running on ${API}?`)
    } finally {
      setLoading(false)
    }
  }

  const yInfo = data?.yandex?.info_pages || []
  const ySim = data?.yandex?.similar_images || []
  const gMatch = data?.google?.matching_pages || []
  const gSim = data?.google?.similar_images || []

  return (
    <div className="wrap">
      <h1>Reverse Image Search</h1>
      <p className="sub">Paste an image URL, search Google Lens + Yandex.</p>

      <div className="panel">
        <label>Image URL</label>
        <input value={imageUrl} onChange={(e) => setImageUrl(e.target.value)} placeholder="https://...jpg" />
        <div className="row">
          <div>
            <label>Or preview a local file</label>
            <input type="file" accept="image/*" onChange={onFile} />
          </div>
          <div>
            <label>Engine</label>
            <select value={engine} onChange={(e) => setEngine(e.target.value)}>
              <option value="both">Both</option>
              <option value="yandex">Yandex</option>
              <option value="google">Google</option>
            </select>
          </div>
          <div>
            <label>Max per list</label>
            <input type="number" min="5" max="100" value={amount} onChange={(e) => setAmount(e.target.value)} />
          </div>
          <button onClick={search} disabled={loading || !imageUrl}>
            {loading ? 'Searching…' : 'Search'}
          </button>
        </div>
        {(filePreview || imageUrl) && (
          <img className="query" src={filePreview || imageUrl} alt="query" />
        )}
        {filePreview && <p className="hint">Note: file is preview-only — search uses the URL field (engines need a public URL).</p>}
      </div>

      {error && <p className="error">{error}</p>}

      {data && (
        <>
          <div className="tabs">
            {['all', 'yandex-info', 'yandex-sim', 'google-match', 'google-sim'].map((t) => (
              <button key={t} className={tab === t ? 'on' : ''} onClick={() => setTab(t)}>{t}</button>
            ))}
          </div>
          {(tab === 'all' || tab === 'yandex-info') && (
            <><h2>Yandex Sites ({yInfo.length})</h2><Cards items={tab === 'all' ? yInfo.slice(0, 8) : yInfo} /></>
          )}
          {(tab === 'all' || tab === 'yandex-sim') && (
            <><h2>Yandex Similar ({ySim.length})</h2><Cards items={tab === 'all' ? ySim.slice(0, 8) : ySim} /></>
          )}
          {(tab === 'all' || tab === 'google-match') && (
            <><h2>Google Exact matches ({gMatch.length})</h2><Cards items={tab === 'all' ? gMatch.slice(0, 8) : gMatch} /></>
          )}
          {(tab === 'all' || tab === 'google-sim') && (
            <><h2>Google Visual matches ({gSim.length})</h2><Cards items={tab === 'all' ? gSim.slice(0, 8) : gSim} /></>
          )}
        </>
      )}
    </div>
  )
}
