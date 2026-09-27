import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Plus, Workflow, Trash2, Pencil, X } from 'lucide-react'
import api from '../lib/api'

export default function EventPipelines() {
  const { eventId } = useParams()
  const navigate = useNavigate()
  const [event, setEvent] = useState(null)
  const [rows, setRows] = useState([])
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [editing, setEditing] = useState(null)
  const [editName, setEditName] = useState('')
  const [editDesc, setEditDesc] = useState('')
  const [savingEdit, setSavingEdit] = useState(false)

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
      const { data } = await api.post(`/events/${eventId}/pipelines`, {
        name: name.trim(),
        description: description.trim(),
        enabled: true,
        flow_graph: { nodes: [], edges: [] },
      })
      setName('')
      setDescription('')
      navigate(`/events/${eventId}/pipelines/${data.id}/flow`)
    } finally {
      setCreating(false)
    }
  }

  function startEdit(row) {
    setEditing(row)
    setEditName(row.name || '')
    setEditDesc(row.description || '')
  }

  async function saveEdit(e) {
    e.preventDefault()
    if (!editing) return
    setSavingEdit(true)
    try {
      await api.put(`/events/${eventId}/pipelines/${editing.id}`, {
        name: editName.trim(),
        description: editDesc.trim(),
      })
      setEditing(null)
      await load()
    } finally {
      setSavingEdit(false)
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
          <p>Name and describe each pipeline. One CometD subscription; enabled pipelines walk in list order.</p>
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
                  <div className="muted" style={{ fontSize: 12 }}>{r.description || 'No description'}</div>
                </td>
                <td>{(r.flow_graph?.nodes || []).length}</td>
                <td>
                  <label className="toggle">
                    <input type="checkbox" checked={!!r.enabled} onChange={() => toggle(r)} />
                    <span>{r.enabled ? 'Enabled' : 'Disabled'}</span>
                  </label>
                </td>
                <td style={{ display: 'flex', gap: 8 }}>
                  <button className="btn btn-sm" type="button" onClick={() => startEdit(r)}><Pencil size={12} /> Edit</button>
                  <button className="btn btn-sm btn-primary" type="button" onClick={() => navigate(`/events/${eventId}/pipelines/${r.id}/flow`)}>
                    <Workflow size={12} /> Open flow
                  </button>
                  <button className="btn btn-sm btn-danger" type="button" onClick={() => remove(r)}><Trash2 size={12} /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <form onSubmit={create} style={{ display: 'grid', gap: 8, padding: 14, borderTop: '1px solid var(--border)', gridTemplateColumns: '1fr 2fr auto' }}>
          <input required value={name} onChange={(e) => setName(e.target.value)} placeholder="Pipeline name" />
          <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description (what this pipeline does)" />
          <button className="btn btn-primary" type="submit" disabled={creating || !name.trim()}><Plus size={14} /> New pipeline</button>
        </form>
      </div>

      {editing && (
        <div className="modal-overlay" onClick={() => setEditing(null)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480 }}>
            <div className="modal-header">
              <h3>Edit pipeline</h3>
              <button className="btn btn-sm" type="button" onClick={() => setEditing(null)}><X size={14} /></button>
            </div>
            <form onSubmit={saveEdit}>
              <div className="panel-body">
                <div className="field">
                  <label>Name</label>
                  <input required value={editName} onChange={(e) => setEditName(e.target.value)} />
                </div>
                <div className="field">
                  <label>Description</label>
                  <textarea rows={3} value={editDesc} onChange={(e) => setEditDesc(e.target.value)} placeholder="What this pipeline does" />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn" onClick={() => setEditing(null)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={savingEdit || !editName.trim()}>
                  {savingEdit ? 'Saving…' : 'Save'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
