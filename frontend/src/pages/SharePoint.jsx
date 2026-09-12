import { useEffect, useMemo, useState } from 'react'
import { Plus, Trash2, Pencil, Cloud, RefreshCw, Search, FlaskConical } from 'lucide-react'
import api from '../lib/api'
import { useProject, belongsToProject } from '../lib/ProjectContext'

const EMPTY_CONN = { name: '', tenant_id: '', client_id: '', client_secret: '', enabled: true }
const EMPTY_FILE = {
  name: '', connection_id: '', enabled: true,
  site_id: '', site_name: '', drive_id: '', drive_name: '',
  folder_path_template: '{{ year }} NBF Reports/{{ business }} Projects',
  file_name_template: '{{ title }}.{{ extension }}',
  create_missing_folders: true, check_in_after_upload: true,
  file_source: 'salesforce_content_version',
  content_document_id_template: '{{ payload.ContentDocumentId }}',
  file_url_template: '',
  metadata_map_text: '{\n  "Title": "{{ title }}"\n}',
  salesforce_record_id_template: '{{ payload.LinkedEntityId }}',
  salesforce_object: 'Opportunity',
}
const EMPTY_LIST = {
  name: '', connection_id: '', enabled: true,
  site_id: '', site_name: '', list_id: '', list_name: '',
  operation: 'create',
  item_id_template: '',
  lookup_field: '',
  lookup_value_template: '',
  field_map_text: '{\n  "Title": "{{ payload.Name }}"\n}',
}

function parseMap(text) {
  if (!text || !text.trim()) return {}
  const obj = JSON.parse(text)
  if (typeof obj !== 'object' || Array.isArray(obj)) throw new Error('Map must be a JSON object')
  return obj
}

export default function SharePoint() {
  const { projectId, project } = useProject()
  const [tab, setTab] = useState('connections')
  const [conns, setConns] = useState([])
  const visibleConns = useMemo(
    () => (conns || []).filter((row) => belongsToProject(row, projectId, project)),
    [conns, projectId, project],
  )
  const [files, setFiles] = useState([])
  const visibleFiles = useMemo(
    () => (files || []).filter((row) => belongsToProject(row, projectId, project)),
    [files, projectId, project],
  )
  const [lists, setLists] = useState([])
  const visibleLists = useMemo(
    () => (lists || []).filter((row) => belongsToProject(row, projectId, project)),
    [lists, projectId, project],
  )
  const [modal, setModal] = useState(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  // Graph pickers
  const [sites, setSites] = useState([])
  const [drives, setDrives] = useState([])
  const [spLists, setSpLists] = useState([])
  const [loadingSites, setLoadingSites] = useState(false)
  const [loadingDrives, setLoadingDrives] = useState(false)
  const [loadingLists, setLoadingLists] = useState(false)
  const [siteSearch, setSiteSearch] = useState('*')
  const [sitePathHostname, setSitePathHostname] = useState('')
  const [sitePathRel, setSitePathRel] = useState('')
  const [discoveryBlocked, setDiscoveryBlocked] = useState(false)
  const [testingConn, setTestingConn] = useState(null) // id or 'form'
  const [testMsg, setTestMsg] = useState(null)

  async function load() {
    const [c, f, l] = await Promise.all([
      api.get('/sharepoint/connections'),
      api.get('/sharepoint/file-actions'),
      api.get('/sharepoint/list-actions'),
    ])
    setConns(c.data)
    setFiles(f.data)
    setLists(l.data)
  }

  useEffect(() => { load().catch((e) => setError(e.message)) }, [])

  async function testSavedConnection(id) {
    setTestingConn(id)
    setTestMsg(null)
    setError(null)
    try {
      const { data } = await api.post(`/sharepoint/connections/${id}/test`)
      setTestMsg({ ok: true, text: data.message || 'OK' })
    } catch (err) {
      setTestMsg({ ok: false, text: err?.response?.data?.detail || err.message })
    } finally {
      setTestingConn(null)
    }
  }

  async function testFormCredentials() {
    if (!modal || modal.kind !== 'conn') return
    const f = modal.form
    if (!f.tenant_id || !f.client_id || (!f.client_secret && !modal.id)) {
      setTestMsg({ ok: false, text: 'Tenant ID, Client ID, and Client secret are required to test.' })
      return
    }
    setTestingConn('form')
    setTestMsg(null)
    setError(null)
    try {
      if (modal.id && !f.client_secret) {
        // use saved secret on server
        const { data } = await api.post(`/sharepoint/connections/${modal.id}/test`)
        setTestMsg({ ok: true, text: data.message || 'OK' })
      } else {
        const { data } = await api.post('/sharepoint/connections/test-credentials', {
          name: f.name || 'test',
          tenant_id: f.tenant_id,
          client_id: f.client_id,
          client_secret: f.client_secret,
          enabled: true,
        })
        setTestMsg({ ok: true, text: data.message || 'OK' })
      }
    } catch (err) {
      setTestMsg({ ok: false, text: err?.response?.data?.detail || err.message })
    } finally {
      setTestingConn(null)
    }
  }


  async function loadSites(connectionId, q = '*') {
    if (!connectionId) { setSites([]); return }
    setLoadingSites(true)
    try {
      const { data } = await api.get(`/sharepoint/connections/${connectionId}/sites`, { params: { q } })
      setSites(data || [])
      setDiscoveryBlocked(false)
    } catch (err) {
      setSites([])
      const detail = String(err?.response?.data?.detail || err.message || '')
      // 403 / forbidden: mark browse unavailable, do not surface as a blocking form error
      if (detail.includes('403') || detail.toLowerCase().includes('forbidden')) {
        setDiscoveryBlocked(true)
      } else {
        setError(detail)
      }
    } finally {
      setLoadingSites(false)
    }
  }

  async function resolveSiteByPath(connectionId) {
    if (!connectionId || !sitePathHostname) return
    setLoadingSites(true)
    try {
      const { data } = await api.get(`/sharepoint/connections/${connectionId}/sites-by-path`, {
        params: { hostname: sitePathHostname, path: sitePathRel || '' },
      })
      setSites((prev) => {
        const exists = prev.some((s) => s.id === data.id)
        return exists ? prev : [data, ...prev]
      })
      setField('site_id', data.id)
      if (data.name) setField('site_name', data.name)
      setDiscoveryBlocked(false)
      // Optional cascade — only if browse is allowed
      if (modal?.kind === 'file') loadDrives(connectionId, data.id)
      if (modal?.kind === 'list') loadSpLists(connectionId, data.id)
    } catch (err) {
      const detail = String(err?.response?.data?.detail || err.message || '')
      if (detail.includes('403') || detail.toLowerCase().includes('forbidden')) {
        setDiscoveryBlocked(true)
      } else {
        setError(detail)
      }
    } finally {
      setLoadingSites(false)
    }
  }

  async function loadDrives(connectionId, siteId) {
    if (!connectionId || !siteId) { setDrives([]); return }
    setLoadingDrives(true)
    try {
      const { data } = await api.get(`/sharepoint/connections/${connectionId}/sites/${encodeURIComponent(siteId)}/drives`)
      setDrives(data || [])
    } catch (err) {
      setDrives([])
      const detail = String(err?.response?.data?.detail || err.message || '')
      if (detail.includes('403') || detail.toLowerCase().includes('forbidden')) {
        setDiscoveryBlocked(true)
      }
      // do not setError — manual Drive ID is enough
    } finally {
      setLoadingDrives(false)
    }
  }

  async function loadSpLists(connectionId, siteId) {
    if (!connectionId || !siteId) { setSpLists([]); return }
    setLoadingLists(true)
    try {
      const { data } = await api.get(`/sharepoint/connections/${connectionId}/sites/${encodeURIComponent(siteId)}/lists`)
      setSpLists(data || [])
    } catch (err) {
      setSpLists([])
      const detail = String(err?.response?.data?.detail || err.message || '')
      if (detail.includes('403') || detail.toLowerCase().includes('forbidden')) {
        setDiscoveryBlocked(true)
      }
      // do not setError — manual List ID is enough
    } finally {
      setLoadingLists(false)
    }
  }

  function openCreate(kind) {
    const form = kind === 'conn' ? { ...EMPTY_CONN }
      : kind === 'file' ? { ...EMPTY_FILE, connection_id: conns[0]?.id || '' }
      : { ...EMPTY_LIST, connection_id: conns[0]?.id || '' }
    setModal({ kind, id: null, form })
    setSites([]); setDrives([]); setSpLists([])
    setDiscoveryBlocked(false)
    setError(null)
    setTestMsg(null)
    // Do not auto-call Graph site search — avoids 403 noise when admins block browse.
    // User can click Search explicitly, or paste Site/Drive/List IDs manually.
  }

  function openEdit(kind, row) {
    if (kind === 'conn') {
      setModal({ kind, id: row.id, form: { name: row.name, tenant_id: row.tenant_id, client_id: row.client_id, client_secret: '', enabled: row.enabled } })
      setSites([]); setDrives([]); setSpLists([])
    } else if (kind === 'file') {
      setModal({
        kind, id: row.id,
        form: {
          ...EMPTY_FILE,
          ...row,
          metadata_map_text: JSON.stringify(row.metadata_map || {}, null, 2),
        },
      })
      setSites([]); setDrives([]); setSpLists([])
      // Keep saved IDs; no automatic Graph browse (prevents repeated 403s)
    } else {
      setModal({
        kind, id: row.id,
        form: {
          ...EMPTY_LIST,
          ...row,
          field_map_text: JSON.stringify(row.field_map || {}, null, 2),
        },
      })
      setSites([]); setDrives([]); setSpLists([])
      // Keep saved IDs; no automatic Graph browse (prevents repeated 403s)
    }
    setError(null)
    setDiscoveryBlocked(false)
  }

  async function save(e) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const { kind, id, form } = modal
      if (kind === 'conn') {
        const payload = { ...form }
        if (id) {
          if (!payload.client_secret) delete payload.client_secret
          await api.put(`/sharepoint/connections/${id}`, payload)
        } else {
          await api.post('/sharepoint/connections', payload)
        }
      } else if (kind === 'file') {
        const payload = { ...form }
        payload.metadata_map = parseMap(form.metadata_map_text)
        delete payload.metadata_map_text
        if (id) await api.put(`/sharepoint/file-actions/${id}`, payload)
        else await api.post('/sharepoint/file-actions', payload)
      } else {
        const payload = { ...form }
        payload.field_map = parseMap(form.field_map_text)
        delete payload.field_map_text
        if (id) await api.put(`/sharepoint/list-actions/${id}`, payload)
        else await api.post('/sharepoint/list-actions', payload)
      }
      setModal(null)
      await load()
    } catch (err) {
      setError(err?.response?.data?.detail || err.message)
    } finally {
      setSaving(false)
    }
  }

  async function remove(kind, row) {
    if (!confirm(`Delete "${row.name}"?`)) return
    const path = kind === 'conn' ? `/sharepoint/connections/${row.id}`
      : kind === 'file' ? `/sharepoint/file-actions/${row.id}`
      : `/sharepoint/list-actions/${row.id}`
    await api.delete(path)
    load()
  }

  function setField(key, value) {
    setModal((m) => ({ ...m, form: { ...m.form, [key]: value } }))
  }

  function onConnectionChange(connectionId) {
    setField('connection_id', connectionId)
    setField('site_id', '')
    setField('site_name', '')
    setField('drive_id', '')
    setField('drive_name', '')
    setField('list_id', '')
    setField('list_name', '')
    setSites([]); setDrives([]); setSpLists([])
    setDiscoveryBlocked(false)
    // No auto Graph search — click Search only if you want browse
  }

  function onSiteChange(siteId) {
    setField('site_id', siteId)
    setField('drive_id', '')
    setField('list_id', '')
    const connId = modal.form.connection_id
    if (modal.kind === 'file') loadDrives(connId, siteId)
    if (modal.kind === 'list') loadSpLists(connId, siteId)
  }

  const connName = (id) => conns.find((c) => c.id === id)?.name || id
  const siteLabel = (id) => sites.find((s) => s.id === id)?.name || id
  const driveLabel = (id) => drives.find((d) => d.id === id)?.name || id

  return (
    <div>
      <div className="page-title-row">
        <div>
          <h1>SharePoint Online</h1>
          <p>GCC High connections and reusable File / List processors (Microsoft Graph app-only)</p>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {[
          ['connections', 'Connections'],
          ['files', 'File actions'],
          ['lists', 'List actions'],
        ].map(([k, label]) => (
          <button key={k} type="button" className={`btn btn-sm ${tab === k ? 'btn-primary' : ''}`} onClick={() => setTab(k)}>
            {label}
          </button>
        ))}
      </div>

      {error && !modal && <div className="panel" style={{ color: 'var(--accent-red)', marginBottom: 12 }}>{String(error)}</div>}
      {testMsg && !modal && (
        <div className="panel" style={{ color: testMsg.ok ? 'var(--accent-green, #22c55e)' : 'var(--accent-red)', marginBottom: 12, fontSize: 13 }}>
          {testMsg.text}
        </div>
      )}

      {tab === 'connections' && (
        <>
          <div className="page-title-row" style={{ marginBottom: 12 }}>
            <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: 13 }}>Tenant + app registration (client credentials). Cloud is fixed to GCC High.</p>
            <button className="btn btn-primary" onClick={() => openCreate('conn')}><Plus size={15} /> Add connection</button>
          </div>
          <div className="org-grid">
            {visibleConns.length === 0 && <div className="panel"><div className="empty-state">No SharePoint connections yet.</div></div>}
            {visibleConns.map((c) => (
              <div className="panel org-card" key={c.id}>
                <div className="org-card-top">
                  <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                    <Cloud size={18} color="var(--accent-purple)" />
                    <div>
                      <h4>{c.name}</h4>
                      <div className="url">Tenant {c.tenant_id}</div>
                    </div>
                  </div>
                  <span className={`badge ${c.enabled ? 'badge-green' : 'badge-gray'}`}>{c.enabled ? 'Enabled' : 'Disabled'}</span>
                </div>
                <div className="org-card-meta">
                  <div>Client ID <b style={{ fontSize: 11 }}>{c.client_id}</b></div>
                  <div>Cloud <b>GCC High</b></div>
                </div>
                <div className="org-card-actions">
                  <button className="btn btn-sm" disabled={testingConn === c.id} onClick={() => testSavedConnection(c.id)}>
                    <FlaskConical size={13} /> {testingConn === c.id ? 'Testing…' : 'Test'}
                  </button>
                  <button className="btn btn-sm" onClick={() => openEdit('conn', c)}><Pencil size={13} /> Edit</button>
                  <button className="btn btn-sm btn-icon btn-danger" onClick={() => remove('conn', c)}><Trash2 size={13} /></button>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {tab === 'files' && (
        <>
          <div className="page-title-row" style={{ marginBottom: 12 }}>
            <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: 13 }}>Upload + metadata + check-in. Pick site & library from Graph (no hard-coded IDs required).</p>
            <button className="btn btn-primary" onClick={() => openCreate('file')} disabled={!conns.length}><Plus size={15} /> Add file action</button>
          </div>
          <div className="org-grid">
            {visibleFiles.length === 0 && <div className="panel"><div className="empty-state">No file actions yet.</div></div>}
            {visibleFiles.map((f) => (
              <div className="panel org-card" key={f.id}>
                <div className="org-card-top">
                  <div>
                    <h4>{f.name}</h4>
                    <div className="url">{connName(f.connection_id)} · {f.file_source}</div>
                  </div>
                </div>
                <div className="org-card-meta">
                  <div>Folder <b style={{ fontSize: 11 }}>{f.folder_path_template || '—'}</b></div>
                  <div>Drive <b style={{ fontSize: 11 }}>{f.drive_id ? `${f.drive_id.slice(0, 18)}…` : '—'}</b></div>
                </div>
                <div className="org-card-actions">
                  <button className="btn btn-sm" onClick={() => openEdit('file', f)}><Pencil size={13} /> Edit</button>
                  <button className="btn btn-sm btn-icon btn-danger" onClick={() => remove('file', f)}><Trash2 size={13} /></button>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {tab === 'lists' && (
        <>
          <div className="page-title-row" style={{ marginBottom: 12 }}>
            <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: 13 }}>Create, update, upsert, lookup, or delete list items. Graph browse optional — paste IDs if 403.</p>
            <button className="btn btn-primary" onClick={() => openCreate('list')} disabled={!conns.length}><Plus size={15} /> Add list action</button>
          </div>
          <div className="org-grid">
            {visibleLists.length === 0 && <div className="panel"><div className="empty-state">No list actions yet.</div></div>}
            {visibleLists.map((f) => (
              <div className="panel org-card" key={f.id}>
                <div className="org-card-top">
                  <div>
                    <h4>{f.name}</h4>
                    <div className="url">{connName(f.connection_id)} · {f.operation}</div>
                  </div>
                </div>
                <div className="org-card-actions">
                  <button className="btn btn-sm" onClick={() => openEdit('list', f)}><Pencil size={13} /> Edit</button>
                  <button className="btn btn-sm btn-icon btn-danger" onClick={() => remove('list', f)}><Trash2 size={13} /></button>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {modal && (
        <div className="modal-overlay" onClick={() => setModal(null)}>
          <div className="modal-box" style={{ maxWidth: 680 }} onClick={(e) => e.stopPropagation()}>
            <div className="panel-header">
              <h3>
                {modal.id ? 'Edit' : 'Add'}{' '}
                {modal.kind === 'conn' ? 'connection' : modal.kind === 'file' ? 'file action' : 'list action'}
              </h3>
            </div>
            <form onSubmit={save}>
              <div className="panel-body">
                {error && <div style={{ color: 'var(--accent-red)', fontSize: 13, marginBottom: 10 }}>{String(error)}</div>}

                {modal.kind === 'conn' && (
                  <>
                    {testMsg && (
                      <div style={{
                        fontSize: 12.5, marginBottom: 10, padding: '8px 10px', borderRadius: 8,
                        background: testMsg.ok ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
                        color: testMsg.ok ? 'var(--accent-green, #22c55e)' : 'var(--accent-red)',
                      }}>{testMsg.text}</div>
                    )}
                    <div className="field"><label>Name</label>
                      <input required value={modal.form.name} onChange={(e) => setField('name', e.target.value)} /></div>
                    <div className="field"><label>Tenant ID</label>
                      <input required value={modal.form.tenant_id} onChange={(e) => setField('tenant_id', e.target.value)} /></div>
                    <div className="field"><label>Client ID</label>
                      <input required value={modal.form.client_id} onChange={(e) => setField('client_id', e.target.value)} /></div>
                    <div className="field"><label>Client secret {modal.id && '(leave blank to keep existing)'}</label>
                      <input type="password" value={modal.form.client_secret} onChange={(e) => setField('client_secret', e.target.value)} required={!modal.id} /></div>
                    <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>Cloud is fixed to <b>GCC High</b> (graph.microsoft.us).</p>
                  </>
                )}

                {(modal.kind === 'file' || modal.kind === 'list') && (
                  <>
                    <div className="field"><label>Name</label>
                      <input required value={modal.form.name} onChange={(e) => setField('name', e.target.value)} /></div>

                    <div className="field"><label>Connection</label>
                      <select required value={modal.form.connection_id} onChange={(e) => onConnectionChange(e.target.value)}>
                        <option value="">Select connection…</option>
                        {visibleConns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                      </select>
                    </div>

                    {/* Resource pickers + manual ID fallback */}
                    {discoveryBlocked && !(modal.form.site_id && (modal.kind === 'file' ? modal.form.drive_id : modal.form.list_id)) && (
                      <div style={{
                        fontSize: 12.5, lineHeight: 1.45, marginBottom: 12, padding: '10px 12px',
                        borderRadius: 8, background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)',
                        color: 'var(--text-secondary)',
                      }}>
                        <b style={{ color: 'var(--accent-red)' }}>Graph browse blocked (403).</b>
                        {' '}Enter <b>Site / Drive / List IDs</b> manually below — Graph will not be queried again until you click Search.
                        Runtime upload still uses your app credentials with those IDs.
                      </div>
                    )}

                    <div className="field">
                      <label style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span>Site (browse)</span>
                        <span style={{ fontWeight: 400, fontSize: 11, color: 'var(--text-muted)' }}>
                          {loadingSites ? 'Loading…' : `${sites.length} found`}
                        </span>
                      </label>
                      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                        <input
                          value={siteSearch}
                          onChange={(e) => setSiteSearch(e.target.value)}
                          placeholder="Search sites (e.g. NBF or *)"
                          style={{ flex: 1 }}
                        />
                        <button
                          type="button"
                          className="btn btn-sm"
                          disabled={!modal.form.connection_id || loadingSites}
                          onClick={() => loadSites(modal.form.connection_id, siteSearch || '*')}
                        >
                          <Search size={13} /> Search
                        </button>
                      </div>
                      <select
                        value={modal.form.site_id}
                        onChange={(e) => {
                          const id = e.target.value
                          const s = sites.find((x) => x.id === id)
                          setField('site_id', id)
                          if (s?.name) setField('site_name', s.name)
                          setField('drive_id', '')
                          setField('drive_name', '')
                          setField('list_id', '')
                          setField('list_name', '')
                          if (id) {
                            if (modal.kind === 'file') loadDrives(modal.form.connection_id, id)
                            if (modal.kind === 'list') loadSpLists(modal.form.connection_id, id)
                          }
                        }}
                        disabled={!modal.form.connection_id || sites.length === 0}
                      >
                        <option value="">{sites.length ? 'Select a site…' : 'No sites from Graph — use manual entry'}</option>
                        {modal.form.site_id && !sites.some((s) => s.id === modal.form.site_id) && (
                          <option value={modal.form.site_id}>{modal.form.site_name || modal.form.site_id} (saved)</option>
                        )}
                        {sites.map((s) => (
                          <option key={s.id} value={s.id}>{s.name}{s.web_url ? ` — ${s.web_url}` : ''}</option>
                        ))}
                      </select>
                      <details style={{ marginTop: 8 }} open={discoveryBlocked || undefined}>
                        <summary style={{ fontSize: 12, color: 'var(--text-muted)', cursor: 'pointer' }}>
                          Resolve by hostname + path (still uses Graph)
                        </summary>
                        <div className="form-row-2" style={{ marginTop: 8 }}>
                          <div className="field" style={{ marginBottom: 0 }}>
                            <label>Hostname</label>
                            <input
                              value={sitePathHostname}
                              onChange={(e) => setSitePathHostname(e.target.value)}
                              placeholder="contoso.sharepoint.us"
                            />
                          </div>
                          <div className="field" style={{ marginBottom: 0 }}>
                            <label>Server-relative path</label>
                            <input
                              value={sitePathRel}
                              onChange={(e) => setSitePathRel(e.target.value)}
                              placeholder="sites/IS-HQ_InSNBF"
                            />
                          </div>
                        </div>
                        <button
                          type="button"
                          className="btn btn-sm"
                          style={{ marginTop: 8 }}
                          disabled={!modal.form.connection_id || !sitePathHostname}
                          onClick={() => resolveSiteByPath(modal.form.connection_id)}
                        >
                          <RefreshCw size={13} /> Resolve site
                        </button>
                      </details>
                    </div>

                    {/* Manual IDs — always available; required when browse fails */}
                    <details open style={{ marginBottom: 12 }}>
                      <summary style={{ fontSize: 12.5, fontWeight: 600, cursor: 'pointer', marginBottom: 8 }}>
                        Enter IDs manually (works without Sites.Read.All)
                      </summary>
                      <div className="form-row-2">
                        <div className="field">
                          <label>Site ID <span style={{ color: 'var(--accent-red)' }}>*</span></label>
                          <input
                            required
                            value={modal.form.site_id || ''}
                            onChange={(e) => {
                              setField('site_id', e.target.value)
                              setDiscoveryBlocked(false)
                              setError(null)
                            }}
                            placeholder="Graph site id (guid or composite)"
                          />
                        </div>
                        <div className="field">
                          <label>Site display name (optional)</label>
                          <input
                            value={modal.form.site_name || ''}
                            onChange={(e) => setField('site_name', e.target.value)}
                            placeholder="IS-HQ NBF"
                          />
                        </div>
                      </div>
                      {modal.kind === 'file' && (
                        <div className="form-row-2">
                          <div className="field">
                            <label>Drive ID <span style={{ color: 'var(--accent-red)' }}>*</span></label>
                            <input
                              required
                              value={modal.form.drive_id || ''}
                              onChange={(e) => {
                                setField('drive_id', e.target.value)
                                setDiscoveryBlocked(false)
                                setError(null)
                              }}
                              placeholder="b!...."
                            />
                          </div>
                          <div className="field">
                            <label>Library display name (optional)</label>
                            <input
                              value={modal.form.drive_name || ''}
                              onChange={(e) => setField('drive_name', e.target.value)}
                              placeholder="Documents"
                            />
                          </div>
                        </div>
                      )}
                      {modal.kind === 'list' && (
                        <div className="form-row-2">
                          <div className="field">
                            <label>List ID <span style={{ color: 'var(--accent-red)' }}>*</span></label>
                            <input
                              required
                              value={modal.form.list_id || ''}
                              onChange={(e) => {
                                setField('list_id', e.target.value)
                                setDiscoveryBlocked(false)
                                setError(null)
                              }}
                              placeholder="List GUID"
                            />
                          </div>
                          <div className="field">
                            <label>List display name (optional)</label>
                            <input
                              value={modal.form.list_name || ''}
                              onChange={(e) => setField('list_name', e.target.value)}
                              placeholder="NBF Tracking"
                            />
                          </div>
                        </div>
                      )}
                      <p style={{ fontSize: 11.5, color: 'var(--text-muted)', margin: '4px 0 0' }}>
                        Tip: from SharePoint in the browser, open the library/list → Settings → or use Graph Explorer
                        with your user account to copy IDs. Runtime upload still uses app-only credentials.
                      </p>
                    </details>

                    {modal.kind === 'file' && sites.length > 0 && (
                      <div className="field">
                        <label style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span>Document library (from Graph)</span>
                          <span style={{ fontWeight: 400, fontSize: 11, color: 'var(--text-muted)' }}>
                            {loadingDrives ? 'Loading…' : `${drives.length} libraries`}
                          </span>
                        </label>
                        <select
                          value={modal.form.drive_id}
                          onChange={(e) => {
                            const id = e.target.value
                            const d = drives.find((x) => x.id === id)
                            setField('drive_id', id)
                            if (d?.name) setField('drive_name', d.name)
                          }}
                          disabled={!modal.form.site_id}
                        >
                          <option value="">Select a library…</option>
                          {modal.form.drive_id && !drives.some((d) => d.id === modal.form.drive_id) && (
                            <option value={modal.form.drive_id}>{modal.form.drive_name || modal.form.drive_id} (saved)</option>
                          )}
                          {drives.map((d) => (
                            <option key={d.id} value={d.id}>{d.name}{d.drive_type ? ` (${d.drive_type})` : ''}</option>
                          ))}
                        </select>
                      </div>
                    )}

                    {modal.kind === 'list' && sites.length > 0 && (
                      <div className="field">
                        <label style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span>List (from Graph)</span>
                          <span style={{ fontWeight: 400, fontSize: 11, color: 'var(--text-muted)' }}>
                            {loadingLists ? 'Loading…' : `${spLists.length} lists`}
                          </span>
                        </label>
                        <select
                          value={modal.form.list_id}
                          onChange={(e) => {
                            const id = e.target.value
                            const l = spLists.find((x) => x.id === id)
                            setField('list_id', id)
                            if (l?.name) setField('list_name', l.name)
                          }}
                          disabled={!modal.form.site_id}
                        >
                          <option value="">Select a list…</option>
                          {modal.form.list_id && !spLists.some((l) => l.id === modal.form.list_id) && (
                            <option value={modal.form.list_id}>{modal.form.list_name || modal.form.list_id} (saved)</option>
                          )}
                          {spLists.map((l) => (
                            <option key={l.id} value={l.id}>{l.name}</option>
                          ))}
                        </select>
                      </div>
                    )}

                  </>
                )}

                {modal.kind === 'file' && (
                  <>
                    <div className="field"><label>Folder path (Jinja2)</label>
                      <input value={modal.form.folder_path_template} onChange={(e) => setField('folder_path_template', e.target.value)} /></div>
                    <div className="field"><label>File name (Jinja2)</label>
                      <input value={modal.form.file_name_template} onChange={(e) => setField('file_name_template', e.target.value)} /></div>
                    <div className="field"><label>File source</label>
                      <select value={modal.form.file_source} onChange={(e) => setField('file_source', e.target.value)}>
                        <option value="salesforce_content_version">Salesforce ContentVersion</option>
                        <option value="url">URL</option>
                      </select>
                    </div>
                    {modal.form.file_source === 'salesforce_content_version' ? (
                      <div className="field"><label>ContentDocumentId template</label>
                        <input value={modal.form.content_document_id_template} onChange={(e) => setField('content_document_id_template', e.target.value)} /></div>
                    ) : (
                      <div className="field"><label>File URL template</label>
                        <input value={modal.form.file_url_template} onChange={(e) => setField('file_url_template', e.target.value)} /></div>
                    )}
                    <div className="form-row-2">
                      <div className="field"><label>SF record Id template (optional)</label>
                        <input value={modal.form.salesforce_record_id_template} onChange={(e) => setField('salesforce_record_id_template', e.target.value)} /></div>
                      <div className="field"><label>SF object API name</label>
                        <input value={modal.form.salesforce_object} onChange={(e) => setField('salesforce_object', e.target.value)} /></div>
                    </div>
                    <div className="field"><label>Metadata map (JSON column → Jinja2)</label>
                      <textarea rows={5} value={modal.form.metadata_map_text} onChange={(e) => setField('metadata_map_text', e.target.value)}
                        style={{ fontFamily: 'ui-monospace, monospace', fontSize: 12.5 }} /></div>
                    <div className="field" style={{ display: 'flex', gap: 16 }}>
                      <label style={{ display: 'flex', gap: 6, alignItems: 'center', margin: 0 }}>
                        <input type="checkbox" checked={modal.form.create_missing_folders} onChange={(e) => setField('create_missing_folders', e.target.checked)} style={{ width: 16 }} />
                        Create missing folders
                      </label>
                      <label style={{ display: 'flex', gap: 6, alignItems: 'center', margin: 0 }}>
                        <input type="checkbox" checked={modal.form.check_in_after_upload} onChange={(e) => setField('check_in_after_upload', e.target.checked)} style={{ width: 16 }} />
                        Check in after upload
                      </label>
                    </div>
                  </>
                )}

                {modal.kind === 'list' && (
                  <>
                    <div className="field"><label>Operation</label>
                      <select value={modal.form.operation} onChange={(e) => setField('operation', e.target.value)}>
                        <option value="create">Create</option>
                        <option value="update">Update</option>
                        <option value="upsert">Upsert (lookup then update or create)</option>
                        <option value="lookup">Lookup only</option>
                        <option value="delete">Delete</option>
                      </select>
                    </div>
                    {['update', 'delete'].includes(modal.form.operation) && (
                      <div className="field"><label>Item ID template (Jinja2) — optional if lookup is set</label>
                        <input value={modal.form.item_id_template || ''} onChange={(e) => setField('item_id_template', e.target.value)}
                          placeholder="{{ payload.SharePointItemId__c }}" /></div>
                    )}
                    {['update', 'upsert', 'lookup', 'delete'].includes(modal.form.operation) && (
                      <div className="form-row-2">
                        <div className="field"><label>Lookup field (SharePoint column)</label>
                          <input value={modal.form.lookup_field || ''} onChange={(e) => setField('lookup_field', e.target.value)}
                            placeholder="e.g. OpportunityId" /></div>
                        <div className="field"><label>Lookup value (Jinja2)</label>
                          <input value={modal.form.lookup_value_template || ''} onChange={(e) => setField('lookup_value_template', e.target.value)}
                            placeholder="{{ payload.OpportunityId }}" /></div>
                      </div>
                    )}
                    {modal.form.operation !== 'lookup' && modal.form.operation !== 'delete' && (
                      <div className="field"><label>Field map (JSON field → Jinja2)</label>
                        <textarea rows={5} value={modal.form.field_map_text} onChange={(e) => setField('field_map_text', e.target.value)}
                          style={{ fontFamily: 'ui-monospace, monospace', fontSize: 12.5 }} /></div>
                    )}
                  </>
                )}
              </div>
              <div className="modal-footer">
                <button type="button" className="btn" onClick={() => setModal(null)}>Cancel</button>
                {modal.kind === 'conn' && (
                  <button type="button" className="btn" disabled={testingConn === 'form'} onClick={testFormCredentials}>
                    <FlaskConical size={14} /> {testingConn === 'form' ? 'Testing…' : 'Test connection'}
                  </button>
                )}
                <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
