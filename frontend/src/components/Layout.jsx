import { NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Building2, Radio, ListTree, ScrollText, Search, LogOut, Settings,
  SlidersHorizontal, Users as UsersIcon, Share2, BellRing,
} from 'lucide-react'
import { logout } from '../lib/api'
import { useAuth, hasRole } from '../lib/AuthContext'

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/orgs', label: 'Salesforce Orgs', icon: Building2 },
  { to: '/events', label: 'Event Config', icon: Radio },
  { to: '/transactions', label: 'Transactions', icon: ListTree },
  { to: '/logs', label: 'System Logs', icon: ScrollText },
]

// Admin-only section - hidden entirely for viewer/operator roles
const ADMIN_NAV_ITEMS = [
  { to: '/integrations', label: 'Integrations', icon: Share2 },
  { to: '/alerts', label: 'Alerts', icon: BellRing },
  { to: '/users', label: 'Users', icon: UsersIcon },
  { to: '/admin-config', label: 'Admin Configuration', icon: SlidersHorizontal },
]

const ROLE_LABELS = { admin: 'Admin', operator: 'Operator', viewer: 'Viewer' }

export default function Layout({ children }) {
  const navigate = useNavigate()
  const { user } = useAuth()
  const isAdmin = hasRole(user, 'admin')

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
          {NAV_ITEMS.map((item) => (
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

        {isAdmin && (
          <div className="nav-group">
            <div className="nav-label">Administration</div>
            {ADMIN_NAV_ITEMS.map((item) => (
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
            <div className="env-pill">
              <Settings size={13} />
              Multi-org
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
