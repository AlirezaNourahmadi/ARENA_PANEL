import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { CheckCircle2, CircleAlert, LoaderCircle } from 'lucide-react'
import { api } from './api'
import Layout from './components/Layout'
import Login from './components/Login'

const Dashboard = lazy(() => import('./components/Dashboard'))
const Logs = lazy(() => import('./components/Logs'))
const Nodes = lazy(() => import('./components/Nodes'))
const System = lazy(() => import('./components/System'))
const Users = lazy(() => import('./components/Users'))

const validPages = new Set(['dashboard', 'users', 'nodes', 'logs', 'system'])

export default function App() {
  const [admin, setAdmin] = useState(null)
  const [booting, setBooting] = useState(true)
  const [authBusy, setAuthBusy] = useState(false)
  const [authError, setAuthError] = useState('')
  const [page, setPage] = useState(() => {
    const value = location.hash.replace('#/', '')
    return validPages.has(value) ? value : 'dashboard'
  })
  const [dashboard, setDashboard] = useState(null)
  const [users, setUsers] = useState([])
  const [nodes, setNodes] = useState([])
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [toast, setToast] = useState(null)

  const notify = useCallback((message, tone = 'ok') => {
    setToast({ message, tone })
    window.clearTimeout(window.__arenaToast)
    window.__arenaToast = window.setTimeout(() => setToast(null), 3500)
  }, [])

  const loadAll = useCallback(async () => {
    setLoading(true)
    try {
      const [dashboardData, usersData, nodesData, healthData] = await Promise.all([
        api.dashboard(), api.users(), api.nodes(), api.health(),
      ])
      setDashboard(dashboardData); setUsers(usersData); setNodes(nodesData); setHealth(healthData)
    } catch (err) {
      if (err.status === 401) setAdmin(null)
      else notify(err.message, 'error')
    } finally { setLoading(false) }
  }, [notify])

  useEffect(() => {
    api.session().then((data) => setAdmin(data.admin)).catch(() => setAdmin(null)).finally(() => setBooting(false))
  }, [])
  useEffect(() => { if (admin) loadAll() }, [admin, loadAll])
  useEffect(() => {
    if (!admin) return undefined
    const timer = window.setInterval(() => api.dashboard().then(setDashboard).catch(() => {}), 15000)
    return () => window.clearInterval(timer)
  }, [admin])

  function navigate(next) {
    setPage(next); location.hash = `/${next}`
  }

  async function login(payload) {
    setAuthBusy(true); setAuthError('')
    try { const result = await api.login(payload); setAdmin(result.admin) }
    catch (err) { setAuthError(err.message) }
    finally { setAuthBusy(false) }
  }

  async function logout() {
    try { await api.logout() } finally { setAdmin(null) }
  }

  if (booting) return <div className="boot-screen"><img src="/arena-mark.png" alt="" /><LoaderCircle className="spin" /></div>
  if (!admin) return <Login onLogin={login} busy={authBusy} error={authError} />

  return <Layout page={page} onNavigate={navigate} admin={admin} onLogout={logout}>
    <Suspense fallback={<div className="page-loading"><LoaderCircle className="spin" /> در حال بارگذاری</div>}>
      {page === 'dashboard' && <Dashboard data={dashboard} users={users} loading={loading} />}
      {page === 'users' && <Users users={users} nodes={nodes} reload={loadAll} notify={notify} />}
      {page === 'nodes' && <Nodes nodes={nodes} reload={loadAll} notify={notify} />}
      {page === 'logs' && <Logs users={users} />}
      {page === 'system' && <System health={health} />}
    </Suspense>
    {toast && <div className={`toast toast-${toast.tone}`}>{toast.tone === 'error' ? <CircleAlert size={18} /> : <CheckCircle2 size={18} />}<span>{toast.message}</span></div>}
  </Layout>
}
