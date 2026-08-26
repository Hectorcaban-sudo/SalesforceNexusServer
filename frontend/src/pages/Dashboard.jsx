import { useEffect, useState } from 'react'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, LineChart, Line,
} from 'recharts'
import { Building2, Activity, CheckCircle2, Layers, RefreshCw, Send, AlertTriangle } from 'lucide-react'
import api from '../lib/api'
import { Sparkline, StatusBadge, timeAgo } from '../components/UI'

const STATUS_COLORS = {
  received: '#3d8bfd', queued: '#ffb648', processing: '#29d1e8', processed: '#3d8bfd',
  publishing: '#ffb648', published: '#33d685', failed: '#ff5470',
}

export default function Dashboard() {
  const [summary, setSummary] = useState(null)
  const [stats, setStats] = useState(null)
  const [txns, setTxns] = useState([])
  const [activeOrg, setActiveOrg] = useState('all')

  async function load() {
    const [s, st, t] = await Promise.all([
      api.get('/dashboard/summary'),
      api.get('/transactions/stats'),
      api.get('/transactions', { params: { limit: 8 } }),
    ])
    setSummary(s.data)
    setStats(st.data)
    setTxns(t.data)
  }

  useEffect(() => {
    load()
    const id = setInterval(load, 5000)
    return () => clearInterval(id)
  }, [])

  async function resync() {
    await api.post('/orgs/resync')
    load()
  }

  if (!summary || !stats) {
    return <div className="empty-state">Loading dashboard…</div>
  }

  const trend = summary.hourly_transaction_trend.map((v, i) => ({ hour: `${i}h`, value: v }))
  const byOrg = Object.entries(stats.by_org).map(([name, value]) => ({ name, value }))
  const byStatus = Object.entries(stats.by_status)

  return (
    <div>
      <div className="page-title-row">
        <div>
          <h1>Operations Dashboard</h1>
          <p>Live view of Salesforce event traffic across all connected orgs</p>
        </div>
        <button className="btn" onClick={resync}><RefreshCw size={14} /> Resync connections</button>
      </div>

      {/* Greeting + ticker row */}
      <div className="top-grid">
        <div className="panel greeting-card">
          <div className="avatar-lg"><Building2 size={20} color="var(--text-secondary)" /></div>
          <div>
            <h4>Hello, Admin</h4>
            <p>{summary.app_name} · {summary.total_orgs} org{summary.total_orgs === 1 ? '' : 's'} configured</p>
          </div>
        </div>

        <div className="ticker-row">
          <TickerCard
            label="Connected Orgs" icon={<Building2 size={14} color="var(--accent-blue)" />} iconBg="rgba(61,139,253,.12)"
            value={`${summary.connected_orgs}/${summary.total_orgs}`}
            sub={`${summary.total_event_configs} channel(s) configured`}
            data={trend.slice(-12).map((d) => d.value)}
            color="var(--accent-blue)"
          />
          <TickerCard
            label="Events / hour" icon={<Activity size={14} color="var(--accent-cyan)" />} iconBg="rgba(41,209,232,.12)"
            value={summary.transactions_last_hour}
            sub={`${summary.total_transactions} total processed`}
            data={trend.slice(-12).map((d) => d.value)}
            color="var(--accent-cyan)"
          />
          <TickerCard
            label="Success Rate" icon={<CheckCircle2 size={14} color="var(--accent-green)" />} iconBg="rgba(51,214,133,.12)"
            value={`${stats.success_rate}%`}
            sub={`${stats.failed} failed`}
            data={trend.slice(-12).map((d) => Math.max(0, d.value - (d.value > 2 ? 1 : 0)))}
            color="var(--accent-green)"
          />
          <TickerCard
            label="Queue Depth" icon={<Layers size={14} color="var(--accent-orange)" />} iconBg="rgba(255,182,72,.12)"
            value={summary.inbound_queue_depth + summary.outbound_queue_depth}
            sub={`${summary.inbound_queue_depth} in · ${summary.outbound_queue_depth} out`}
            data={trend.slice(-12).map((d) => d.value % 3)}
            color="var(--accent-orange)"
          />
        </div>
      </div>

      {/* Main grid: stream + status */}
      <div className="dash-grid">
        <div className="panel">
          <div className="tabs-row">
            <div className={`tab-pill ${activeOrg === 'all' ? 'active' : ''}`} onClick={() => setActiveOrg('all')}>All Orgs</div>
            {summary.orgs.map((o) => (
              <div key={o.id} className={`tab-pill ${activeOrg === o.id ? 'active' : ''}`} onClick={() => setActiveOrg(o.id)}>
                {o.name}
              </div>
            ))}
          </div>
          <div className="stream-body">
            <div className="stream-chart-area">
              <ResponsiveContainer width="100%" height={230}>
                <BarChart data={trend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="hour" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} axisLine={false} tickLine={false} interval={3} />
                  <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 10 }} axisLine={false} tickLine={false} width={26} />
                  <Tooltip contentStyle={{ background: 'var(--bg-panel-alt)', border: '1px solid var(--border-light)', borderRadius: 8, fontSize: 12 }} />
                  <Bar dataKey="value" fill="var(--accent-blue)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="stream-side">
              <div className="side-stat">
                <div className="k">Inbound queue</div>
                <div className="v">{summary.inbound_queue_depth}</div>
              </div>
              <div className="side-stat">
                <div className="k">Outbound queue</div>
                <div className="v">{summary.outbound_queue_depth}</div>
              </div>
              <div className="side-stat">
                <div className="k">Event channels</div>
                <div className="v">{summary.total_event_configs}</div>
              </div>
              <div className="side-actions">
                <button className="btn btn-primary btn-sm" onClick={resync}><RefreshCw size={13} /> Resync</button>
                <a href="#/events" className="btn btn-sm" style={{ textDecoration: 'none' }}><Send size={13} /> Manage events</a>
              </div>
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header"><h3>Transactions by status</h3></div>
          <div className="legend-list" style={{ paddingTop: 16 }}>
            {byStatus.length === 0 && <div className="empty-state">No transactions yet</div>}
            {byStatus.map(([status, count]) => {
              const max = Math.max(...byStatus.map(([, c]) => c), 1)
              return (
                <div key={status}>
                  <div className="legend-row">
                    <div className="legend-left">
                      <span className="legend-dot" style={{ background: STATUS_COLORS[status] || '#5d6a82' }} />
                      {status}
                    </div>
                    <span className="legend-val">{count}</span>
                  </div>
                  <div style={{ height: 5, background: 'var(--bg-panel-alt)', borderRadius: 4, marginTop: 5 }}>
                    <div style={{ height: '100%', width: `${(count / max) * 100}%`, background: STATUS_COLORS[status] || '#5d6a82', borderRadius: 4 }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Bottom row */}
      <div className="bottom-grid">
        <div className="panel">
          <div className="panel-header"><h3>Transaction volume (24h)</h3></div>
          <div className="chart-panel-body">
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={trend}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis dataKey="hour" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} axisLine={false} tickLine={false} interval={5} />
                <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 10 }} axisLine={false} tickLine={false} width={24} />
                <Tooltip contentStyle={{ background: 'var(--bg-panel-alt)', border: '1px solid var(--border-light)', borderRadius: 8, fontSize: 12 }} />
                <Line type="monotone" dataKey="value" stroke="var(--accent-cyan)" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header"><h3>Activity by org</h3></div>
          <div className="chart-panel-body">
            {byOrg.length === 0 ? <div className="empty-state">No activity yet</div> : (
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={byOrg} layout="vertical" margin={{ left: 10 }}>
                  <XAxis type="number" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis type="category" dataKey="name" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} axisLine={false} tickLine={false} width={90} />
                  <Tooltip contentStyle={{ background: 'var(--bg-panel-alt)', border: '1px solid var(--border-light)', borderRadius: 8, fontSize: 12 }} />
                  <Bar dataKey="value" fill="var(--accent-purple)" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div className="panel">
          <div className="panel-header"><h3>Recent transactions</h3></div>
          <div className="scrollbox" style={{ maxHeight: 220 }}>
            {txns.length === 0 && (
              <div className="empty-state"><AlertTriangle size={16} style={{ marginBottom: 6 }} /><br />No transactions recorded yet</div>
            )}
            {txns.map((t) => (
              <div key={t.id} className="log-row" style={{ gridTemplateColumns: '1fr auto', fontFamily: 'var(--font-sans)' }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 12.5 }}>{t.channel.split('/').pop()}</div>
                  <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>{t.org_name} · {timeAgo(t.created_at)}</div>
                </div>
                <StatusBadge status={t.status} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function TickerCard({ label, icon, iconBg, value, sub, data, color }) {
  return (
    <div className="panel ticker-card">
      <div className="ticker-top">
        <div className="label">
          <span className="ticker-icon" style={{ background: iconBg }}>{icon}</span>
          {label}
        </div>
      </div>
      <div className="ticker-value">{value}</div>
      <div className="ticker-delta up">{sub}</div>
      <Sparkline data={data} color={color} />
    </div>
  )
}
