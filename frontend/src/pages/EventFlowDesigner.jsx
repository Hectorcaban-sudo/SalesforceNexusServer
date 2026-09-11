import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, Link } from 'react-router-dom'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
  MarkerType,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  ArrowLeft, Save, RotateCcw, Radio, ShieldCheck, Cpu, ArrowUpFromLine,
  Share2, BellRing, Plus, X,
} from 'lucide-react'
import api from '../lib/api'

/* ─── Custom node components ─── */

function NodeShell({ accent, icon: Icon, title, subtitle, badge, selected, onRemove }) {
  return (
    <div
      className={`flow-node ${selected ? 'selected' : ''}`}
      style={{ '--node-accent': accent }}
    >
      <Handle type="target" position={Position.Left} className="flow-handle" />
      <div className="flow-node-head">
        <div className="flow-node-icon" style={{ background: `${accent}22`, color: accent }}>
          <Icon size={14} />
        </div>
        <div className="flow-node-titles">
          <div className="flow-node-title">{title}</div>
          {subtitle && <div className="flow-node-sub">{subtitle}</div>}
        </div>
        {onRemove && (
          <button type="button" className="flow-node-remove" onClick={(e) => { e.stopPropagation(); onRemove() }} title="Remove">
            <X size={12} />
          </button>
        )}
      </div>
      {badge && <div className="flow-node-badge">{badge}</div>}
      <Handle type="source" position={Position.Right} className="flow-handle" />
    </div>
  )
}

function SourceNode({ data, selected }) {
  return (
    <NodeShell
      accent="#f97316"
      icon={Radio}
      title={data.label}
      subtitle={data.subtitle}
      badge={data.badge}
      selected={selected}
    />
  )
}

function RuleNode({ data, selected }) {
  return (
    <NodeShell
      accent="#a78bfa"
      icon={ShieldCheck}
      title={data.label}
      subtitle={data.subtitle}
      badge={data.badge}
      selected={selected}
    />
  )
}

function ProcessorNode({ data, selected }) {
  return (
    <NodeShell
      accent="#3b82f6"
      icon={Cpu}
      title={data.label}
      subtitle={data.subtitle}
      badge={data.badge}
      selected={selected}
    />
  )
}

function PublishNode({ data, selected }) {
  return (
    <NodeShell
      accent="#22c55e"
      icon={ArrowUpFromLine}
      title={data.label}
      subtitle={data.subtitle}
      badge={data.badge}
      selected={selected}
      onRemove={data.onRemove}
    />
  )
}

function IntegrationNode({ data, selected }) {
  return (
    <NodeShell
      accent="#8b5cf6"
      icon={Share2}
      title={data.label}
      subtitle={data.subtitle}
      badge={data.badge}
      selected={selected}
      onRemove={data.onRemove}
    />
  )
}

function AlertNode({ data, selected }) {
  return (
    <NodeShell
      accent="#ef4444"
      icon={BellRing}
      title={data.label}
      subtitle={data.subtitle}
      badge={data.badge}
      selected={selected}
      onRemove={data.onRemove}
    />
  )
}

const nodeTypes = {
  source: SourceNode,
  rule: RuleNode,
  processor: ProcessorNode,
  publish: PublishNode,
  integration: IntegrationNode,
  alert: AlertNode,
}

const defaultEdgeOptions = {
  type: 'smoothstep',
  animated: false,
  style: { stroke: '#64748b', strokeWidth: 1.5 },
  markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16, color: '#64748b' },
}

function buildGraph({ event, orgName, rules, processors, pubs, integrations, alerts, selected }) {
  const nodes = []
  const edges = []

  nodes.push({
    id: 'source',
    type: 'source',
    position: { x: 40, y: 180 },
    data: {
      label: event.channel,
      subtitle: `Subscribe · Org: ${orgName}`,
      badge: event.enabled ? 'Enabled' : 'Disabled',
    },
    draggable: true,
  })

  const rule = rules.find((r) => r.id === selected.ruleId)
  nodes.push({
    id: 'rule',
    type: 'rule',
    position: { x: 320, y: 180 },
    data: {
      label: rule ? rule.name : 'No rule',
      subtitle: rule ? 'GoRules gate' : 'Always process',
      badge: rule ? 'Optional' : 'Bypass',
    },
    draggable: true,
  })
  edges.push({ id: 'e-source-rule', source: 'source', target: 'rule', ...defaultEdgeOptions })

  const mode = selected.processingMode || ''
  const proc = processors.find((p) => p.id === selected.processorId)
  let procLabel = 'Global default'
  let procSub = 'Admin Configuration'
  let procBadge = 'Default'
  if (mode === 'local') { procLabel = 'Local processor'; procSub = 'processing_mode: local'; procBadge = 'Local' }
  else if (mode === 'dss_client') { procLabel = 'Dataiku DSS'; procSub = 'processing_mode: dss_client'; procBadge = 'DSS' }
  else if (mode === 'langflow') { procLabel = 'Langflow'; procSub = 'processing_mode: langflow'; procBadge = 'AI' }
  else if (mode === 'custom_script') {
    procLabel = proc?.name || 'Custom script'
    procSub = 'processing_mode: custom_script'
    procBadge = 'Script'
  } else if (mode === 'sharepoint_file') {
    procLabel = 'SharePoint File'
    procSub = selected.processorId ? `action: ${selected.processorId.slice(0, 8)}…` : 'processing_mode: sharepoint_file'
    procBadge = 'SP File'
  } else if (mode === 'sharepoint_list') {
    procLabel = 'SharePoint List'
    procSub = selected.processorId ? `action: ${selected.processorId.slice(0, 8)}…` : 'processing_mode: sharepoint_list'
    procBadge = 'SP List'
  }

  nodes.push({
    id: 'processor',
    type: 'processor',
    position: { x: 600, y: 180 },
    data: { label: procLabel, subtitle: procSub, badge: procBadge },
    draggable: true,
  })
  edges.push({ id: 'e-rule-proc', source: 'rule', target: 'processor', ...defaultEdgeOptions })

  const fanX = 920
  let fanY = 40
  const gap = 100

  if (selected.autoPublish) {
    selected.publishIds.forEach((id) => {
      const p = pubs.find((x) => x.id === id)
      if (!p) return
      const nid = `publish-${id}`
      nodes.push({
        id: nid,
        type: 'publish',
        position: { x: fanX, y: fanY },
        data: {
          label: p.channel,
          subtitle: 'Salesforce Platform Event',
          badge: 'Publish',
          refId: id,
        },
        draggable: true,
      })
      edges.push({ id: `e-proc-${nid}`, source: 'processor', target: nid, ...defaultEdgeOptions })
      fanY += gap
    })
  }

  selected.integrationIds.forEach((id) => {
    const i = integrations.find((x) => x.id === id)
    if (!i) return
    const nid = `integration-${id}`
    nodes.push({
      id: nid,
      type: 'integration',
      position: { x: fanX, y: fanY },
      data: {
        label: i.name,
        subtitle: `${i.type}${i.body_mode === 'template' ? ' · custom template' : ''}`,
        badge: 'Integration',
        refId: id,
      },
      draggable: true,
    })
    edges.push({ id: `e-proc-${nid}`, source: 'processor', target: nid, ...defaultEdgeOptions })
    fanY += gap
  })

  selected.alertIds.forEach((id) => {
    const a = alerts.find((x) => x.id === id)
    if (!a) return
    const nid = `alert-${id}`
    nodes.push({
      id: nid,
      type: 'alert',
      position: { x: fanX, y: fanY },
      data: {
        label: a.name,
        subtitle: a.scope || 'alert',
        badge: 'Alert',
        refId: id,
      },
      draggable: true,
    })
    edges.push({ id: `e-proc-${nid}`, source: 'processor', target: nid, ...defaultEdgeOptions })
    fanY += gap
  })

  return { nodes, edges }
}

export default function EventFlowDesigner() {
  const { eventId } = useParams()
  const navigate = useNavigate()

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [dirty, setDirty] = useState(false)

  const [event, setEvent] = useState(null)
  const [orgs, setOrgs] = useState([])
  const [configs, setConfigs] = useState([])
  const [integrations, setIntegrations] = useState([])
  const [alerts, setAlerts] = useState([])
  const [processors, setProcessors] = useState([])
  const [rules, setRules] = useState([])
  const [spFileActions, setSpFileActions] = useState([])
  const [spListActions, setSpListActions] = useState([])

  const [selected, setSelected] = useState({
    ruleId: '',
    processingMode: '',
    processorId: '',
    autoPublish: true,
    publishIds: [],
    integrationIds: [],
    alertIds: [],
  })

  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [selectedNodeId, setSelectedNodeId] = useState(null)

  const orgName = useMemo(() => {
    if (!event) return ''
    return orgs.find((o) => o.id === event.org_id)?.name || event.org_id
  }, [event, orgs])

  const pubs = useMemo(
    () => configs.filter((c) => c.direction === 'publish' && event && c.org_id === event.org_id),
    [configs, event],
  )
  const routableIntegrations = useMemo(
    () => integrations.filter((i) => !i.alert_only),
    [integrations],
  )
  const transactionAlerts = useMemo(
    () => alerts.filter((a) => a.scope === 'transaction'),
    [alerts],
  )

  const rebuild = useCallback((sel, ev, ctx) => {
    if (!ev) return
    const graph = buildGraph({
      event: ev,
      orgName: ctx.orgName,
      rules: ctx.rules,
      processors: ctx.processors,
      pubs: ctx.pubs,
      integrations: ctx.integrations,
      alerts: ctx.alerts,
      selected: sel,
    })
    // Attach remove handlers
    graph.nodes = graph.nodes.map((n) => {
      if (n.type === 'publish' || n.type === 'integration' || n.type === 'alert') {
        return {
          ...n,
          data: {
            ...n.data,
            onRemove: () => {
              setSelected((prev) => {
                const next = { ...prev }
                if (n.type === 'publish') next.publishIds = prev.publishIds.filter((id) => id !== n.data.refId)
                if (n.type === 'integration') next.integrationIds = prev.integrationIds.filter((id) => id !== n.data.refId)
                if (n.type === 'alert') next.alertIds = prev.alertIds.filter((id) => id !== n.data.refId)
                return next
              })
              setDirty(true)
            },
          },
        }
      }
      return n
    })
    setNodes(graph.nodes)
    setEdges(graph.edges)
  }, [setNodes, setEdges])

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const [o, c, i, p, a, r, sf, sl] = await Promise.all([
          api.get('/orgs'),
          api.get('/events'),
          api.get('/integrations'),
          api.get('/processors'),
          api.get('/alerts'),
          api.get('/rules'),
          api.get('/sharepoint/file-actions').catch(() => ({ data: [] })),
          api.get('/sharepoint/list-actions').catch(() => ({ data: [] })),
        ])
        if (cancelled) return
        const ev = c.data.find((x) => x.id === eventId)
        if (!ev) {
          setError('Event channel not found')
          setLoading(false)
          return
        }
        if (ev.direction !== 'subscribe') {
          setError('Flow designer is only available for subscribe channels')
          setLoading(false)
          return
        }
        setOrgs(o.data)
        setConfigs(c.data)
        setIntegrations(i.data)
        setProcessors(p.data)
        setAlerts(a.data)
        setRules(r.data)
        setSpFileActions(sf.data || [])
        setSpListActions(sl.data || [])
        setEvent(ev)

        const sel = {
          ruleId: ev.rule_id || '',
          processingMode: ev.processing_mode || '',
          processorId: ev.processor_id || '',
          autoPublish: ev.auto_publish !== false,
          publishIds: [...(ev.route_publish_channel_ids || [])],
          integrationIds: [...(ev.route_integration_ids || [])],
          alertIds: [...(ev.route_alert_ids || [])],
        }
        setSelected(sel)
        setDirty(false)
      } catch (err) {
        if (!cancelled) setError(err?.response?.data?.detail || err.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [eventId])

  // Rebuild graph when selection or reference data changes
  useEffect(() => {
    if (!event) return
    rebuild(selected, event, {
      orgName,
      rules,
      processors,
      pubs,
      integrations,
      alerts,
    })
  }, [selected, event, orgName, rules, processors, pubs, integrations, alerts, rebuild])

  function updateSelected(patch) {
    setSelected((prev) => ({ ...prev, ...patch }))
    setDirty(true)
  }

  function toggleId(listKey, id) {
    setSelected((prev) => {
      const list = prev[listKey]
      const next = list.includes(id) ? list.filter((x) => x !== id) : [...list, id]
      return { ...prev, [listKey]: next }
    })
    setDirty(true)
  }

  async function save() {
    if (!event) return
    setSaving(true)
    setError(null)
    try {
      await api.put(`/events/${event.id}`, {
        route_publish_channel_ids: selected.autoPublish ? selected.publishIds : [],
        route_integration_ids: selected.integrationIds,
        route_alert_ids: selected.alertIds,
        processing_mode: selected.processingMode || '',
        processor_id: ['custom_script','sharepoint_file','sharepoint_list'].includes(selected.processingMode) ? selected.processorId : '',
        rule_id: selected.ruleId || '',
        auto_publish: selected.autoPublish,
      })
      setDirty(false)
    } catch (err) {
      setError(err?.response?.data?.detail || err.message)
    } finally {
      setSaving(false)
    }
  }

  function resetFromServer() {
    if (!event) return
    setSelected({
      ruleId: event.rule_id || '',
      processingMode: event.processing_mode || '',
      processorId: event.processor_id || '',
      autoPublish: event.auto_publish !== false,
      publishIds: [...(event.route_publish_channel_ids || [])],
      integrationIds: [...(event.route_integration_ids || [])],
      alertIds: [...(event.route_alert_ids || [])],
    })
    setDirty(false)
  }

  const onNodeClick = useCallback((_, node) => {
    setSelectedNodeId(node.id)
  }, [])

  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null)
  }, [])

  if (loading) {
    return <div className="empty-state">Loading flow…</div>
  }

  if (error && !event) {
    return (
      <div className="panel">
        <div className="empty-state">{error}</div>
        <div style={{ textAlign: 'center', marginBottom: 20 }}>
          <Link to="/events" className="btn">Back to Event Config</Link>
        </div>
      </div>
    )
  }

  return (
    <div className="flow-page">
      <div className="flow-toolbar">
        <div className="flow-toolbar-left">
          <button type="button" className="btn btn-sm" onClick={() => navigate('/events')}>
            <ArrowLeft size={14} /> Events
          </button>
          <div>
            <div className="flow-breadcrumb">
              Events / <code>{event?.channel}</code> / Flow
            </div>
            <h1 className="flow-title">Event Flow Designer</h1>
            <p className="flow-subtitle">Subscribe → process → route. Visual layout of existing pipeline steps.</p>
          </div>
        </div>
        <div className="flow-toolbar-right">
          {dirty && <span className="flow-dirty">Unsaved changes</span>}
          <button type="button" className="btn" onClick={resetFromServer} disabled={!dirty || saving}>
            <RotateCcw size={14} /> Reset
          </button>
          <button type="button" className="btn btn-primary" onClick={save} disabled={!dirty || saving}>
            <Save size={14} /> {saving ? 'Saving…' : 'Save flow'}
          </button>
        </div>
      </div>

      {error && (
        <div className="flow-error">{error}</div>
      )}

      <div className="flow-body">
        {/* Palette / config sidebar */}
        <aside className="flow-sidebar">
          <div className="flow-sidebar-section">
            <div className="flow-sidebar-label">Pipeline</div>
            <div className="field">
              <label>Rule gate</label>
              <select
                value={selected.ruleId}
                onChange={(e) => updateSelected({ ruleId: e.target.value })}
              >
                <option value="">No rule — always process</option>
                {rules.map((r) => (
                  <option key={r.id} value={r.id}>{r.name}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>Processor</label>
              <select
                value={selected.processingMode}
                onChange={(e) => updateSelected({
                  processingMode: e.target.value,
                  processorId: ['custom_script', 'sharepoint_file', 'sharepoint_list'].includes(e.target.value)
                    ? selected.processorId
                    : '',
                })}
              >
                <option value="">Global default</option>
                <option value="local">Local</option>
                <option value="dss_client">Dataiku DSS</option>
                <option value="langflow">Langflow</option>
                <option value="custom_script">Custom script</option>
                <option value="sharepoint_file">SharePoint File (primary)</option>
                <option value="sharepoint_list">SharePoint List (primary)</option>
              </select>
            </div>
            {selected.processingMode === 'custom_script' && (
              <div className="field">
                <label>Uploaded processor</label>
                <select
                  value={selected.processorId}
                  onChange={(e) => updateSelected({ processorId: e.target.value })}
                >
                  <option value="">Select…</option>
                  {processors.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </div>
            )}
            {selected.processingMode === 'sharepoint_file' && (
              <div className="field">
                <label>SharePoint file action</label>
                <select
                  value={selected.processorId}
                  onChange={(e) => updateSelected({ processorId: e.target.value })}
                >
                  <option value="">Select file action…</option>
                  {spFileActions.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </div>
            )}
            {selected.processingMode === 'sharepoint_list' && (
              <div className="field">
                <label>SharePoint list action</label>
                <select
                  value={selected.processorId}
                  onChange={(e) => updateSelected({ processorId: e.target.value })}
                >
                  <option value="">Select list action…</option>
                  {spListActions.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </div>
            )}
            <div className="field" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input
                type="checkbox"
                style={{ width: 16 }}
                checked={selected.autoPublish}
                onChange={(e) => updateSelected({ autoPublish: e.target.checked })}
              />
              <label style={{ margin: 0 }}>Auto-publish to Salesforce</label>
            </div>
          </div>

          <div className="flow-sidebar-section">
            <div className="flow-sidebar-label">
              Publish channels
              {!selected.autoPublish && <span style={{ fontWeight: 400, color: 'var(--text-muted)' }}> (disabled)</span>}
            </div>
            <div style={{ opacity: selected.autoPublish ? 1 : 0.4, pointerEvents: selected.autoPublish ? 'auto' : 'none' }}>
              {pubs.length === 0 && <div className="empty-state" style={{ padding: '8px 0', fontSize: 12 }}>No publish channels for this org</div>}
              {pubs.map((p) => (
                <label key={p.id} className="flow-check">
                  <input
                    type="checkbox"
                    checked={selected.publishIds.includes(p.id)}
                    onChange={() => toggleId('publishIds', p.id)}
                  />
                  <code>{p.channel}</code>
                </label>
              ))}
            </div>
          </div>

          <div className="flow-sidebar-section">
            <div className="flow-sidebar-label">Integration hooks</div>
            {routableIntegrations.length === 0 && (
              <div className="empty-state" style={{ padding: '8px 0', fontSize: 12 }}>No integrations yet</div>
            )}
            {routableIntegrations.map((i) => (
              <label key={i.id} className="flow-check">
                <input
                  type="checkbox"
                  checked={selected.integrationIds.includes(i.id)}
                  onChange={() => toggleId('integrationIds', i.id)}
                />
                <span>{i.name}</span>
                <span className="flow-check-meta">
                  ({i.type === 'sharepoint_file' ? 'SharePoint File' : i.type === 'sharepoint_list' ? 'SharePoint List' : i.type})
                </span>
              </label>
            ))}
          </div>

          <div className="flow-sidebar-section">
            <div className="flow-sidebar-label">Alerts</div>
            {transactionAlerts.length === 0 && (
              <div className="empty-state" style={{ padding: '8px 0', fontSize: 12 }}>No transaction alerts</div>
            )}
            {transactionAlerts.map((a) => (
              <label key={a.id} className="flow-check">
                <input
                  type="checkbox"
                  checked={selected.alertIds.includes(a.id)}
                  onChange={() => toggleId('alertIds', a.id)}
                />
                <span>{a.name}</span>
              </label>
            ))}
          </div>

          <div className="flow-sidebar-hint">
            Phase 1 nodes map to existing event config fields. Saving writes the same routing API as the classic form.
          </div>
        </aside>

        {/* Canvas */}
        <div className="flow-canvas">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            minZoom={0.4}
            maxZoom={1.5}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={18} size={1} color="rgba(148,163,184,0.15)" />
            <Controls showInteractive={false} />
            <MiniMap
              nodeStrokeWidth={2}
              pannable
              zoomable
              style={{ background: 'var(--bg-panel)' }}
            />
          </ReactFlow>
        </div>
      </div>
    </div>
  )
}
