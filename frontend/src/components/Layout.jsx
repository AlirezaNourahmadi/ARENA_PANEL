import {
  Activity,
  Gauge,
  LogOut,
  Menu,
  Network,
  ServerCog,
  UsersRound,
  X,
} from 'lucide-react'
import { useState } from 'react'

const items = [
  { id: 'dashboard', label: 'نمای کلی', icon: Gauge },
  { id: 'users', label: 'کاربران', icon: UsersRound },
  { id: 'nodes', label: 'نودها', icon: Network },
  { id: 'logs', label: 'ردیابی', icon: Activity },
  { id: 'system', label: 'سیستم', icon: ServerCog },
]

const titles = Object.fromEntries(items.map((item) => [item.id, item.label]))

export default function Layout({ page, onNavigate, admin, onLogout, children }) {
  const [mobileOpen, setMobileOpen] = useState(false)

  function navigate(id) {
    onNavigate(id)
    setMobileOpen(false)
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileOpen ? 'sidebar-open' : ''}`}>
        <div className="sidebar-brand">
          <img src="/arena-mark.png" alt="" />
          <div><strong>ARENA</strong><span>CONTROL PLANE</span></div>
          <button className="sidebar-close" onClick={() => setMobileOpen(false)} title="بستن منو"><X size={20} /></button>
        </div>
        <nav aria-label="منوی اصلی">
          {items.map(({ id, label, icon: Icon }) => (
            <button key={id} className={page === id ? 'active' : ''} onClick={() => navigate(id)}>
              <Icon size={19} strokeWidth={1.8} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-status">
          <span className="live-dot" />
          <div><strong>هسته آنلاین</strong><small>Xray / Gateway</small></div>
        </div>
        <button className="logout-button" onClick={onLogout}>
          <LogOut size={18} />
          <span>خروج</span>
        </button>
      </aside>
      {mobileOpen && <button className="sidebar-scrim" onClick={() => setMobileOpen(false)} aria-label="بستن منو" />}
      <main className="workspace">
        <header className="topbar">
          <div className="topbar-title">
            <button className="menu-button" onClick={() => setMobileOpen(true)} aria-label="باز کردن منو"><Menu size={22} /></button>
            <div><span>ARENA</span><h1>{titles[page]}</h1></div>
          </div>
          <div className="admin-chip">
            <span>{admin.username.slice(0, 2).toUpperCase()}</span>
            <div><strong>{admin.username}</strong><small>مدیر سیستم</small></div>
          </div>
        </header>
        <div className="workspace-content">{children}</div>
      </main>
      <nav className="mobile-nav" aria-label="منوی موبایل">
        {items.slice(0, 4).map(({ id, label, icon: Icon }) => (
          <button key={id} className={page === id ? 'active' : ''} onClick={() => navigate(id)}>
            <Icon size={20} /><span>{label}</span>
          </button>
        ))}
      </nav>
    </div>
  )
}
