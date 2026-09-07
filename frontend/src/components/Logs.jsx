import { useEffect, useMemo, useState } from 'react'
import { Activity, Filter, RefreshCw, Search, ShieldAlert } from 'lucide-react'
import { api } from '../api'
import { bytes, date, number } from '../utils'

export default function Logs({ users }) {
  const [data, setData] = useState({ sessions: [], audit: [] })
  const [tab, setTab] = useState('sessions')
  const [userId, setUserId] = useState('')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    try { setData(await api.logs(userId)) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [userId])
  const names = Object.fromEntries(users.map((user) => [user.id, user.name]))
  const rows = useMemo(() => (tab === 'sessions' ? data.sessions : data.audit).filter((item) => JSON.stringify(item).toLowerCase().includes(query.toLowerCase())), [data, tab, query])

  return <div className="page-stack">
    <section className="toolbar logs-toolbar">
      <div className="segmented"><button className={tab === 'sessions' ? 'active' : ''} onClick={() => setTab('sessions')}>نشست‌ها</button><button className={tab === 'audit' ? 'active' : ''} onClick={() => setTab('audit')}>رویدادهای مدیریتی</button></div>
      <div className="toolbar-cluster">
        <label className="select-box"><Filter size={17} /><select value={userId} onChange={(e) => setUserId(e.target.value)}><option value="">همه کاربران</option>{users.map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}</select></label>
        <div className="search-box compact-search"><Search size={17} /><input placeholder="فیلتر لاگ" value={query} onChange={(e) => setQuery(e.target.value)} /></div>
        <button className="icon-button" onClick={load} title="تازه‌سازی"><RefreshCw size={18} className={loading ? 'spin' : ''} /></button>
      </div>
    </section>
    <section className="surface table-surface">
      <div className="table-heading"><div><span className="eyebrow">TRACE</span><h2>{tab === 'sessions' ? 'اتصال‌های کاربران' : 'Audit log'} <b>{number(rows.length)}</b></h2></div></div>
      {tab === 'sessions' ? <div className="data-table log-table">
        <div className="table-row table-head"><span>کاربر</span><span>آدرس</span><span>وضعیت</span><span>ترافیک</span><span>شروع</span><span>پایان</span></div>
        {rows.map((item) => <div className="table-row" key={item.id}>
          <div><strong>{names[item.user_id] || item.user_id.slice(0, 8)}</strong><small>{item.node_id.slice(0, 8)}</small></div>
          <div dir="ltr"><strong>{item.source_ip}</strong><small title={item.user_agent}>{item.user_agent?.slice(0, 24) || 'بدون User-Agent'}</small></div>
          <div><span className={`status-pill ${item.status === 'active' ? 'ok' : item.status === 'blocked' ? 'error' : 'muted'}`}>{item.status}</span><small>{item.close_reason || 'در حال تبادل'}</small></div>
          <div><strong>{bytes(item.downlink_bytes + item.uplink_bytes)}</strong><small>↓ {bytes(item.downlink_bytes)} / ↑ {bytes(item.uplink_bytes)}</small></div>
          <div><strong>{date(item.started_at)}</strong></div><div><strong>{item.ended_at ? date(item.ended_at) : 'باز'}</strong></div>
        </div>)}
      </div> : <div className="data-table audit-table">
        <div className="table-row table-head"><span>رویداد</span><span>عامل</span><span>شناسه</span><span>جزئیات</span><span>زمان</span></div>
        {rows.map((item) => <div className="table-row" key={item.id}><div className="event-cell"><ShieldAlert size={17} /><strong>{item.action}</strong></div><div>{item.actor}</div><div dir="ltr">{item.entity_id?.slice(0, 12) || '-'}</div><code>{item.detail}</code><time>{date(item.created_at)}</time></div>)}
      </div>}
      {!rows.length && <div className="empty-state"><Activity size={24} />لاگی برای نمایش وجود ندارد</div>}
    </section>
  </div>
}
