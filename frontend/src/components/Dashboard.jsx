import { Activity, ArrowDown, ArrowUp, Network, Radio, UsersRound } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { bytes, date, number } from '../utils'

function Stat({ label, value, meta, icon: Icon, tone }) {
  return (
    <article className={`stat-card tone-${tone}`}>
      <div className="stat-icon"><Icon size={21} /></div>
      <div><span>{label}</span><strong>{value}</strong><small>{meta}</small></div>
    </article>
  )
}

export default function Dashboard({ data, users, loading }) {
  if (loading || !data) return <div className="page-loading"><Activity className="spin" /> در حال دریافت وضعیت</div>
  const names = Object.fromEntries(users.map((user) => [user.id, user.name]))
  const chart = [...data.recent_sessions].reverse().map((item, index) => ({
    name: number(index + 1),
    up: Math.round(item.uplink_bytes / 1024),
    down: Math.round(item.downlink_bytes / 1024),
  }))
  return (
    <div className="page-stack">
      <section className="stats-grid" aria-label="شاخص‌های سرویس">
        <Stat label="کاربران فعال" value={number(data.users_enabled)} meta={`از ${number(data.users_total)} کاربر`} icon={UsersRound} tone="green" />
        <Stat label="نشست زنده" value={number(data.active_sessions)} meta={`${number(data.active_ips)} آی‌پی یکتا`} icon={Radio} tone="cyan" />
        <Stat label="ترافیک ثبت‌شده" value={bytes(data.traffic_total)} meta="مجموع چرخه جاری" icon={Activity} tone="amber" />
        <Stat label="نودهای در دسترس" value={number(data.nodes_enabled)} meta="مسیر فعال" icon={Network} tone="coral" />
      </section>

      <section className="dashboard-grid">
        <div className="surface chart-surface">
          <div className="section-heading">
            <div><span className="eyebrow">جریان نشست‌ها</span><h2>ترافیک اخیر</h2></div>
            <div className="legend"><span><i className="down" />دانلود</span><span><i className="up" />آپلود</span></div>
          </div>
          <div className="chart-wrap">
            {chart.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chart} barGap={3}>
                  <CartesianGrid stroke="#e9ecef" vertical={false} />
                  <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: '#7a8085', fontSize: 11 }} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fill: '#7a8085', fontSize: 11 }} width={44} />
                  <Tooltip contentStyle={{ borderRadius: 6, border: '1px solid #dfe3e6', direction: 'rtl' }} formatter={(value) => `${number(value)} KB`} />
                  <Bar dataKey="down" fill="#00a870" radius={[3, 3, 0, 0]} maxBarSize={18} />
                  <Bar dataKey="up" fill="#14a8c4" radius={[3, 3, 0, 0]} maxBarSize={18} />
                </BarChart>
              </ResponsiveContainer>
            ) : <div className="empty-state">هنوز نشست ثبت‌شده‌ای وجود ندارد</div>}
          </div>
        </div>

        <div className="surface live-surface">
          <div className="section-heading"><div><span className="eyebrow">آخرین رویدادها</span><h2>نشست‌ها</h2></div><span className="live-label"><i />زنده</span></div>
          <div className="session-list">
            {data.recent_sessions.slice(0, 6).map((item) => (
              <div className="session-row" key={item.id}>
                <div className="session-avatar">{(names[item.user_id] || 'U').slice(0, 1).toUpperCase()}</div>
                <div className="session-main"><strong>{names[item.user_id] || item.user_id.slice(0, 8)}</strong><span>{item.source_ip}</span></div>
                <div className="session-traffic"><span><ArrowDown size={13} />{bytes(item.downlink_bytes)}</span><span><ArrowUp size={13} />{bytes(item.uplink_bytes)}</span></div>
                <time>{date(item.last_seen_at)}</time>
              </div>
            ))}
            {!data.recent_sessions.length && <div className="empty-state">نشستی ثبت نشده است</div>}
          </div>
        </div>
      </section>
    </div>
  )
}
