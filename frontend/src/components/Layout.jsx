import { NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Building2, Radio, ListTree, ScrollText, Search, LogOut, Settings,
  SlidersHorizontal, Users as UsersIcon, Share2, BellRing, ShieldCheck, Cloud,
  FolderKanban, Code2, GitBranch,
} from 'lucide-react'
import { logout } from '../lib/api'
import { useAuth, hasRole } from '../lib/AuthContext'
import { useProject } from '../lib/ProjectContext'

const MONITOR_NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/transactions', label: 'Transactions', icon: ListTree },
  { to: '/logs', label: 'System Logs', icon: ScrollText },
]

const PROJECT_NAV = [
  { to: '/projects', label: 'Projects', icon: FolderKanban },
  { to: '/orgs', label: 'Salesforce Orgs', icon: Building2 },
  { to: '/events', label: 'Events & flows', icon: Radio },
  { to: '/integrations', label: 'Integrations', icon: Share2, admin: true },
  { to: '/sharepoint', label: 'SharePoint', icon: Cloud, admin: true },
  { to: '/processors', label: 'Processors', icon: Code2, admin: true },
  { to: '/rules', label: 'Rules', icon: GitBranch, admin: true },
]

const ADMIN_NAV = [
  { to: '/alerts', label: 'Alerts', icon: BellRing },
  { to: '/users', label: 'Users', icon: UsersIcon },
  { to: '/security', label: 'Security', icon: ShieldCheck },
  { to: '/admin-config', label: 'Admin Configuration', icon: Settings },
]

const ROLE_LABELS = { admin: 'Admin', operator: 'Operator', viewer: 'Viewer' }

export default function Layout({ children }) {
  const navigate = useNavigate()
  const { user } = useAuth()
  const isAdmin = hasRole(user, 'admin')
  const { projects, projectId, project, setProjectId } = useProject()

  function handleLogout() {
    logout()
    navigate('/login')
  }

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

        <div className="nav-group">
          <div className="nav-label">Monitor</div>
          {MONITOR_NAV.map((item) => (
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

        <div className="nav-group">
          <div className="nav-label">
            Project{project ? ` · ${project.name}` : ''}
          </div>
          {PROJECT_NAV.filter((i) => !i.admin || isAdmin).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => 'nav-item' + (isActive ? ' active' : '')}
            >
              <item.icon />
              {item.label}
            </NavLink>
          ))}
        </div>

        {isAdmin && (
          <div className="nav-group">
            <div className="nav-label">Administration</div>
            {ADMIN_NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => 'nav-item' + (isActive ? ' active' : '')}
              >
                <item.icon />
                {item.label}
              </NavLink>
            ))}
          </div>
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
            <div className="env-pill" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <FolderKanban size={13} />
              <select
                value={projectId || ''}
                onChange={(e) => setProjectId(e.target.value || null)}
                style={{
                  background: 'transparent', border: 'none', color: 'inherit',
                  fontSize: 12.5, maxWidth: 180, cursor: 'pointer',
                }}
                title="Active project"
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
            <div className="user-chip" title={user ? `${user.username} · ${ROLE_LABELS[user.role] || user.role}` : ''}>
              <div className="avatar">{(user?.username || 'A').slice(0, 1).toUpperCase()}</div>
              {user && (
                <span className={`badge badge-${user.role === 'admin' ? 'blue' : user.role === 'operator' ? 'orange' : 'gray'}`}>
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
'''
