import { useEffect, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Building2, Radio, ListTree, ScrollText, Search, LogOut, Settings,
  Users as UsersIcon, Share2, BellRing, ShieldCheck, Cloud,
  FolderKanban, Cpu, GitBranch, Plus, Minus, Bell, CircleHelp,
} from 'lucide-react'
import api, { logout } from '../lib/api'
import { useAuth, hasRole } from '../lib/AuthContext'
import { useProject } from '../lib/ProjectContext'
import ProjectSwitcher from './ProjectSwitcher'

const MONITOR_NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/transactions', label: 'Transactions', icon: ListTree },
  { to: '/logs', label: 'System Logs', icon: ScrollText },
]

const PROJECT_NAV = [
  { to: '/orgs', label: 'Salesforce Orgs', icon: Building2 },
  { to: '/events', label: 'Events & flows', icon: Radio },
  { to: '/integrations', label: 'Integrations', icon: Share2, admin: true },
  { to: '/sharepoint', label: 'SharePoint', icon: Cloud, admin: true },
  { to: '/processors', label: 'Processors', icon: Cpu, admin: true },
  { to: '/rules', label: 'Rules', icon: GitBranch, admin: true },
]

const ADMIN_NAV = [
  { to: '/projects', label: 'Projects', icon: FolderKanban },
  { to: '/alerts', label: 'Alerts', icon: BellRing },
  { to: '/users', label: 'Users', icon: UsersIcon },
  { to: '/security', label: 'Security', icon: ShieldCheck },
  { to: '/admin-config', label: 'Admin Configuration', icon: Settings },
]

const ROLE_LABELS = { admin: 'Admin', operator: 'Operator', viewer: 'Viewer' }
const COLLAPSE_KEY = 'nexus_nav_collapsed'

function loadCollapsed() {
  try {
    return JSON.parse(localStorage.getItem(COLLAPSE_KEY) || '{}')
  } catch {
    return {}
  }
}

function NavSection({ id, label, items, collapsed, onToggle }) {
  return (
    <div className="nav-group">
      <button
        type="button"
        className="nav-label"
        onClick={() => onToggle(id)}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          width: '100%', background: 'none', border: 'none', cursor: 'pointer',
          color: 'inherit', padding: 0, font: 'inherit', textAlign: 'left',
        }}
        title={collapsed[id] ? 'Expand' : 'Collapse'}
      >
        <span>{label}</span>
        <span style={{ opacity: 0.7, display: 'inline-flex' }}>
          {collapsed[id] ? <Plus size={12} /> : <Minus size={12} />}
        </span>
      </button>
      {!collapsed[id] && items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) => 'nav-item' + (isActive ? ' active' : '')}
        >
          <item.icon />
          {item.label}
        </NavLink>
      ))}
    </div>
  )
}

export default function Layout({ children }) {
  const navigate = useNavigate()
  const { user } = useAuth()
  const isAdmin = hasRole(user, 'admin')
  const { projects, projectId, project, setProjectId } = useProject()
  const [collapsed, setCollapsed] = useState(loadCollapsed)

  function toggleSection(id) {
    setCollapsed((prev) => {
      const next = { ...prev, [id]: !prev[id] }
      localStorage.setItem(COLLAPSE_KEY, JSON.stringify(next))
      return next
    })
  }

  function handleLogout() {
    logout()
    navigate('/login')
  }

  const projectItems = PROJECT_NAV.filter((i) => !i.admin || isAdmin)

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="mark">SN</div>
          <div className="name">
            Nexus AI Server
            <span>Salesforce Integration</span>
          </div>
        </div>

        <NavSection id="monitor" label="Monitor" items={MONITOR_NAV} collapsed={collapsed} onToggle={toggleSection} />
        <NavSection
          id="project"
          label={project ? ('Project - ' + project.name) : 'Project'}
          items={projectItems}
          collapsed={collapsed}
          onToggle={toggleSection}
        />
        {isAdmin && (
          <NavSection id="admin" label="Administration" items={ADMIN_NAV} collapsed={collapsed} onToggle={toggleSection} />
        )}

        <div className="sidebar-footer">
          <div className="nav-item" onClick={handleLogout}>
            <LogOut />
            Log out
          </div>
        </div>
      </aside>

      <div className="main-col">
        <header className="topbar">
          <div className="topbar-search">
            <Search size={15} />
            Search transactions, orgs, channels…
          </div>
          <div className="topbar-right">
            <ProjectSwitcher />
            <TopbarInbox />
            <DocsHelpLink />
            <div className="user-chip" title={user ? (user.username + ' - ' + (ROLE_LABELS[user.role] || user.role)) : ''}>
              <div className="avatar">{(user?.username || 'A').slice(0, 1).toUpperCase()}</div>
              {user && (
                <span className={'badge badge-' + (user.role === 'admin' ? 'blue' : user.role === 'operator' ? 'orange' : 'gray')}>
                  {ROLE_LABELS[user.role] || user.role}
                </span>
              )}
            </div>
          </div>
        </header>

        <main className="page-content">{children}</main>
      </div>
    </div>
  )
}

function DocsHelpLink() {
  const [docs, setDocs] = useState({ docs_url: '', docs_label: 'Documentation' })
  useEffect(() => {
    api.get('/dashboard/ui-settings').then((r) => setDocs(r.data || {})).catch(() => {})
  }, [])
  const url = (docs.docs_url || '').trim()
  if (!url) {
    return (
      <span className="topbar-icon" title="Set documentation URL in Admin Configuration">
        <CircleHelp size={18} style={{ opacity: 0.45 }} />
      </span>
    )
  }
  return (
    <a className="topbar-icon" href={url} target="_blank" rel="noreferrer" title={docs.docs_label || 'Documentation'}>
      <CircleHelp size={18} />
    </a>
  )
}

function TopbarInbox() {
  const { projectId } = useProject()
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState([])
  async function load() {
    const { data } = await api.get('/dashboard/notifications', { params: projectId ? { project_id: projectId } : {} })
    setItems(data.items || [])
  }
  useEffect(() => { load(); const id = setInterval(load, 30000); return () => clearInterval(id) }, [projectId])
  return (
    <div style={{ position: 'relative' }}>
      <button type="button" className="topbar-icon" onClick={() => setOpen((v) => !v)} title="Notifications">
        <Bell size={18} />
        {items.length > 0 && <span className="topbar-badge">{items.length > 9 ? '9+' : items.length}</span>}
      </button>
      {open && (
        <div className="topbar-inbox">
          <div className="topbar-inbox-head">Inbox {projectId ? '(this project)' : '(all)'}</div>
          {items.length === 0 && <div className="empty-state" style={{ padding: 16 }}>No alerts right now</div>}
          {items.map((it) => (
            <a key={it.id} href={it.href || '/'} className="topbar-inbox-row" onClick={() => setOpen(false)}>
              <strong>{it.title}</strong>
              {it.detail && <div className="muted">{it.detail}</div>}
            </a>
          ))}
        </div>
      )}
    </div>
  )
}
