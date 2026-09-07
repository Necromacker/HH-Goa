import { useMemo, useState } from 'react'
import './App.css'

const API = 'http://127.0.0.1:8000'

const PLATFORM_RULES = [
  { name: 'Instagram', domains: ['instagram.com'] },
  { name: 'Facebook', domains: ['facebook.com', 'fb.com', 'fb.watch'] },
  { name: 'X / Twitter', domains: ['x.com', 'twitter.com', 't.co'] },
  { name: 'YouTube', domains: ['youtube.com', 'youtu.be'] },
  { name: 'TikTok', domains: ['tiktok.com'] },
  { name: 'LinkedIn', domains: ['linkedin.com'] },
  { name: 'Pinterest', domains: ['pinterest.com', 'pin.it'] },
  { name: 'Reddit', domains: ['reddit.com'] },
  { name: 'Threads', domains: ['threads.net'] },
  { name: 'Snapchat', domains: ['snapchat.com'] },
  { name: 'VK', domains: ['vk.com'] },
  { name: 'Weibo', domains: ['weibo.com'] },
  { name: 'Tumblr', domains: ['tumblr.com'] },
  { name: 'Quora', domains: ['quora.com'] },
  { name: 'Medium', domains: ['medium.com'] },
  { name: 'Telegram', domains: ['t.me', 'telegram.org'] },
  { name: 'WhatsApp', domains: ['whatsapp.com'] },
  { name: 'Discord', domains: ['discord.com', 'discord.gg'] },
  { name: 'Twitch', domains: ['twitch.tv'] },
  { name: 'Spotify', domains: ['spotify.com'] },
]

const PLATFORM_COLORS = {
  Instagram: '#df3f78', Facebook: '#1877f2', 'X / Twitter': '#101010',
  YouTube: '#f00000', TikTok: '#101010', LinkedIn: '#0a66c2',
  Pinterest: '#e60023', Reddit: '#ff4500', Threads: '#101010',
  Snapchat: '#d7bd00', VK: '#4c75a3', Weibo: '#e6162d', Tumblr: '#35465c',
  Quora: '#b92b27', Medium: '#101010', Telegram: '#0088cc',
  WhatsApp: '#25d366', Discord: '#5865f2', Twitch: '#9146ff', Spotify: '#1db954',
}

function detectPlatform(url) {
  if (!url) return null
  const value = url.toLowerCase()
  return PLATFORM_RULES.find((rule) => rule.domains.some((domain) => (
    value.includes(`://${domain}`) || value.includes(`://${'www.' + domain}`)
  )))?.name || null
}

function ArrowIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 19 19 5M9 5h10v10" /></svg>
}

function SearchResult({ result }) {
  const platform = detectPlatform(result.url)
  const label = platform || (() => {
    try { return new URL(result.url).hostname.replace(/^www\./, '') } catch { return 'Source' }
  })()

  return (
    <article className="result-card">
      <div className="result-image">
        {result.thumbnail_url ? (
          <img src={result.thumbnail_url} alt={result.title || `${label} result`} loading="lazy" />
        ) : <div className="image-placeholder">No preview</div>}
      </div>
      <div className="result-meta">
        <div>
          <p className="result-source" style={{ '--tag-color': PLATFORM_COLORS[platform] || '#111' }}>{label}</p>
          {result.title && <p className="result-title">{result.title}</p>}
        </div>
        <a className="open-link" href={result.url} target="_blank" rel="noreferrer" aria-label={`Open ${label} result`}>
          <ArrowIcon />
        </a>
      </div>
    </article>
  )
}

export default function App() {
  const [imageUrl, setImageUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [results, setResults] = useState(null)

  const previewUrl = imageUrl.trim()
  const hasValidInput = /^https?:\/\//i.test(previewUrl)
  const allResults = useMemo(() => {
    if (!results) return []
    const sources = [
      results.yandex?.info_pages, results.yandex?.similar_images,
      results.google?.matching_pages, results.google?.similar_images,
    ]
    const seen = new Set()
    return sources.flat().filter((item) => {
      if (!item?.url || seen.has(item.url)) return false
      seen.add(item.url)
      return true
    })
  }, [results])

  async function search(event) {
    event.preventDefault()
    if (!hasValidInput) return
    setLoading(true)
    setError(null)
    setResults(null)
    try {
      const response = await fetch(`${API}/api/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_url: previewUrl, engine: 'both', amount: 30 }),
      })
      if (!response.ok) throw new Error(`Backend ${response.status}`)
      setResults(await response.json())
    } catch (err) {
      setError(`Search failed: ${err.message}. Is the backend running on ${API}?`)
    } finally {
      setLoading(false)
    }
  }

  function updateUrl(event) {
    setImageUrl(event.target.value)
    setResults(null)
    setError(null)
  }

  function startOver() {
    setResults(null)
    setError(null)
  }

  return (
    <main className="app-shell">
      <nav className="top-nav" aria-label="Primary navigation">
        <a className="brand" href="#top" onClick={startOver}>image<span>trace</span></a>
        <div className="nav-steps" aria-label="Search progress">
          <span className={!results ? 'active' : ''}>01 / Search</span>
          <span className={results ? 'active' : ''}>02 / Results</span>
        </div>
      </nav>
      {!results ? (
        <section className="search-screen" id="top">
          <header className="hero">
            <p className="eyebrow">REVERSE IMAGE SEARCH</p>
            <h1>Find where your<br />image appears.</h1>
            <p>Paste a public image URL to discover matching pages and social posts across the web.</p>
          </header>
          <form className="search-form" onSubmit={search}>
            <label htmlFor="image-url">Image URL</label>
            <div className="url-row">
              <input id="image-url" type="url" value={imageUrl} onChange={updateUrl}
                placeholder="https://example.com/image.jpg" autoComplete="url" />
              <button type="submit" disabled={loading || !hasValidInput} aria-label="Search image URL">
                {loading ? 'Searching…' : <><span>Search</span><ArrowIcon /></>}
              </button>
            </div>
          </form>
          {error && <p className="error">{error}</p>}
        </section>
      ) : (
        <section className="results-screen" id="top" aria-labelledby="step-two">
          <header className="results-intro">
            <div>
              <p className="eyebrow">SEARCH RESULTS</p>
              <h1 id="step-two">Matches for your image.</h1>
            </div>
            <button className="new-search" onClick={startOver}>New search</button>
          </header>
          <div className="query-image">
            <img src={previewUrl} alt="Searched image" />
            <p>Source image</p>
          </div>
          <section className="results-section">
            <div className="results-head">
              <h2>Found pages</h2>
              <p>{allResults.length} result{allResults.length === 1 ? '' : 's'}</p>
            </div>
            {allResults.length ? (
              <div className="result-grid">
                {allResults.map((result, index) => <SearchResult key={`${result.url}-${index}`} result={result} />)}
              </div>
            ) : <p className="empty">No matching pages were found for this image.</p>}
          </section>
        </section>
      )}
    </main>
  )
}
