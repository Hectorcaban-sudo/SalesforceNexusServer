import { ResponsiveContainer, LineChart, Line } from 'recharts'
import { useState } from 'react'

export function Sparkline({ data, color = 'var(--accent-blue)' }) {
  const points = (data || []).map((v, i) => ({ i, v }))
  return (
    <div className="spark-wrap">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points}>
          <Line type="monotone" dataKey="v" stroke={color} strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

const STATUS_MAP = {
  connected: 'green',
  published: 'green',
  processed: 'blue',
  processing: 'blue',
  queued: 'orange',
  connecting: 'orange',
  publishing: 'orange',
  received: 'blue',
  disconnected: 'gray',
  failed: 'red',
  error: 'red',
}

export function StatusBadge({ status }) {
  const tone = STATUS_MAP[status] || 'gray'
  return (
    <span className={`badge badge-${tone}`}>
      <span className="badge-dot" />
      {status}
    </span>
  )
}

export function timeAgo(ts) {
  const diff = Date.now() / 1000 - ts
  if (diff < 60) return `${Math.floor(diff)}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

export function fmtTime(ts) {
  return new Date(ts * 1000).toLocaleString()
}

/**
 * Shows `text` truncated to `maxLength`; if it's longer, hovering reveals
 * the full content in a floating popup positioned above the trigger.
 */
export function TruncatedWithPopup({ text, maxLength = 80, mono = true }) {
  const [hover, setHover] = useState(false)
  const str = typeof text === 'string' ? text : JSON.stringify(text, null, 2)
  if (!str) return null
  if (str.length <= maxLength) {
    return <span className={mono ? 'mono' : ''}>{str}</span>
  }
  return (
    <span
      style={{ position: 'relative', cursor: 'help', borderBottom: '1px dotted var(--text-muted)' }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <span className={mono ? 'mono' : ''}>{str.slice(0, maxLength)}…</span>
      {hover && (
        <div className="hover-popup">
          <pre>{str}</pre>
        </div>
      )}
    </span>
  )
}
