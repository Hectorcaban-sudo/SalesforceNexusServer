import { NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Building2, Radio, ListTree, ScrollText, Search, LogOut, Settings, SlidersHorizontal,
} from 'lucide-react'
import { logout } from '../lib/api'
import { useEffect, useState } from 'react'
import api from '../lib/api'

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/orgs', label: 'Salesforce Orgs', icon: Building2 },
  { to: '/events', label: 'Event Config', icon: Radio },
  { to: '/transactions', label: 'Transactions', icon: ListTree },
  { to: '/logs', label: 'System Logs', icon: ScrollText },
]

const ADMIN_NAV_ITEMS = [
  { to: '/admin-config', label: 'Admin Configuration', icon: SlidersHorizontal },
]

export default function Layout({ children }) {
  const navigate = useNavigate()
  const [me, setMe] = useState(null)

  useEffect(() => {
    api.get('/auth/me').then((r) => setMe(r.data)).catch(() => {})
  }, [])

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
            <div className="user-chip">
              <div className="avatar">{(me?.username || 'A').slice(0, 1).toUpperCase()}</div>
            </div>
          </div>
        </header>

        <main className="page-content">{children}</main>
      </div>
    </div>
  )
}
