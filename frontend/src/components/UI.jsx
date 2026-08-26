import { ResponsiveContainer, LineChart, Line } from 'recharts'

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
