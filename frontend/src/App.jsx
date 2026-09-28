import { useEffect, useState } from 'react'

function useMonitor() {
  const [connected, setConnected] = useState(false)
  const [alerts, setAlerts] = useState([])
  const [history, setHistory] = useState([])
  const [stats, setStats] = useState(null)

  useEffect(() => {
    let ws, retry, poll, closed = false
    const apply = (m) => {
      if (m.type === 'init') { setAlerts(m.alerts); setHistory(m.history); setStats(m.stats) }
      else if (m.type === 'stats') { setStats(m.stats); setHistory((h) => [...h.slice(-119), m.stats]) }
      else if (m.type === 'alert') setAlerts((a) => [m.alert, ...a].slice(0, 200))
    }
    const loadState = async () => {
      try {
        const data = await (await fetch('/api/state')).json()
        apply({ type: 'init', ...data })
      } catch {}
    }
    const startPolling = () => {
      if (poll) return
      loadState()
      poll = setInterval(loadState, 800)
    }
    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/ws`)
      ws.onopen = () => { if (closed) return; setConnected(true); clearInterval(poll); poll = null }
      ws.onmessage = (e) => apply(JSON.parse(e.data))
      ws.onclose = () => {
        if (closed) return
        setConnected(false); startPolling(); retry = setTimeout(connect, 800)
      }
    }
    connect()
    return () => { closed = true; clearTimeout(retry); clearInterval(poll); ws && ws.close() }
  }, [])

  return { connected, alerts, history, stats }
}

const pct = (v) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`)

function Chart({ data }) {
  const W = 600, H = 180, P = 6
  const pts = data.slice(-120)
  const maxY = Math.max(0.1, ...pts.map((p) => Math.max(p.rate, p.threshold || 0))) * 1.15
  const x = (i) => P + (i / Math.max(1, pts.length - 1)) * (W - 2 * P)
  const y = (v) => H - P - (v / maxY) * (H - 2 * P)
  const line = (k) =>
    pts.map((p, i) => (p[k] == null ? null : `${x(i)},${y(p[k])}`)).filter(Boolean).join(' ')
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="chart">
      <polyline points={line('threshold')} className="l-thr" />
      <polyline points={line('mean')} className="l-base" />
      <polyline points={line('rate')} className="l-rate" />
    </svg>
  )
}

export default function App() {
  const { connected, alerts, history, stats } = useMonitor()
  const status = !stats ? '…' : !stats.ready ? 'LEARNING' : stats.severity || 'NORMAL'

  return (
    <div className="wrap">
      <header>
        <h1>Log Anomaly Detector</h1>
        <span className={`pill ${connected ? 'on' : 'off'}`}>{connected ? 'live' : 'reconnecting…'}</span>
      </header>

      <section className="cards">
        <div className="card"><label>Error rate (window)</label><b>{pct(stats?.rate)}</b></div>
        <div className="card">
          <label>Baseline</label>
          <b>{stats?.ready ? pct(stats.mean) : `learning ${Math.round((stats?.warmup || 0) * 100)}%`}</b>
        </div>
        <div className="card"><label>Lines in window</label><b>{stats?.events ?? '—'}</b></div>
        <div className={`card st-${status}`}><label>Status</label><b>{status}</b></div>
      </section>

      <section className="panel">
        <div className="legend">
          <i className="d rate" /> error rate <i className="d base" /> baseline <i className="d thr" /> alert threshold
        </div>
        <Chart data={history} />
      </section>

      <section className="panel">
        <h2>Alert feed <small>{alerts.length}</small></h2>
        {alerts.length === 0 && <p className="empty">No alerts yet. Waiting for anomalies…</p>}
        <ul className="feed">
          {alerts.map((a) => (
            <li key={a.id} className={`alert ${a.status === 'resolved' ? 'resolved' : `sev-${a.severity}`}`}>
              <span className="badge">{a.status === 'resolved' ? 'RESOLVED' : a.severity}</span>
              <span className="msg">{a.message}</span>
              <time>{new Date(a.timestamp * 1000).toLocaleTimeString()}</time>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
