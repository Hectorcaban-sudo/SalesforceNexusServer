import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Plus, Workflow, Trash2 } from 'lucide-react'
import api from '../lib/api'

export default function EventPipelines() {
  const { eventId } = useParams()
  const navigate = useNavigate()
  const [event, setEvent] = useState(null)
  const [rows, setRows] = useState([])
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('New pipeline')

  async function load() {
    const [evs, p] = await Promise.all([
      api.get('/events'),
      api.get(`/events/${eventId}/pipelines`),
    ])
    setEvent((evs.data || []).find((e) => e.id === eventId) || null)
    setRows(p.data || [])
  }

  useEffect(() => { load() }, [eventId])

  async function create(e) {
    e.preventDefault()
    setCreating(true)
    try {
      const { data } = await api.post(`/events/${eventId}/pipelines`, { name, enabled: true, flow_graph: { nodes: [], edges: [] } })
      setName('New pipeline')
      navigate(`/events/${eventId}/pipelines/${data.id}/flow`)
    } finally {
      setCreating(false)
    }
  }

  async function toggle(row) {
    await api.put(`/events/${eventId}/pipelines/${row.id}`, { enabled: !row.enabled })
    load()
  }

  async function remove(row) {
    if (!confirm(`Delete pipeline "${row.name}"?`)) return
    try {
      await api.delete(`/events/${eventId}/pipelines/${row.id}`)
      load()
    } catch (err) {
      alert(err?.response?.data?.detail || err.message)
    }
  }

  return (
    <div>
      <div className="page-title-row">
        <div>
          <button className="btn btn-sm" type="button" onClick={() => navigate('/events')}><ArrowLeft size={14} /> Events</button>
          <h1 style={{ marginTop: 10 }}>{event?.channel || 'Event'} pipelines</h1>
          <p>One CometD subscription. Each enabled pipeline walks independently. Child transaction per pipeline when more than one is on.</p>
        </div>
      </div>
      <div className="panel">
        <div className="panel-header"><h3>Pipelines on this event</h3></div>
        <table>
          <thead><tr><th>Pipeline</th><th>Nodes</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={4} className="empty-state">No pipelines yet</td></tr>}
            {rows.map((r) => (
              <tr key={r.id}>
                <td>
                  <strong>{r.name}</strong>
                  {r.description && <div className="muted" style={{ fontSize: 12 }}>{r.description}</div>}
                </td>
                <td>{(r.flow_graph?.nodes || []).length}</td>
                <td>
                  <label className="toggle">
                    <input type="checkbox" checked={!!r.enabled} onChange={() => toggle(r)} />
                    <span>{r.enabled ? 'Enabled' : 'Disabled'}</span>
                  </label>
                </td>
                <td style={{ display: 'flex', gap: 8 }}>
                  <button className="btn btn-sm btn-primary" type="button" onClick={() => navigate(`/events/${eventId}/pipelines/${r.id}/flow`)}>
                    <Workflow size={12} /> Open flow
                  </button>
                  <button className="btn btn-sm btn-danger" type="button" onClick={() => remove(r)}><Trash2 size={12} /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <form onSubmit={create} style={{ display: 'flex', gap: 8, padding: 14, borderTop: '1px solid var(--border)' }}>
          <input required value={name} onChange={(e) => setName(e.target.value)} placeholder="Pipeline name" />
          <button className="btn btn-primary" type="submit" disabled={creating}><Plus size={14} /> New pipeline</button>
        </form>
      </div>
    </div>
  )
}
