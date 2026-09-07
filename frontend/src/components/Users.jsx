import { useEffect, useMemo, useState } from 'react'
import {
  Ban,
  Check,
  Copy,
  KeyRound,
  Link2,
  MoreHorizontal,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  UserRoundCheck,
} from 'lucide-react'
import { api } from '../api'
import { bytes, copy, number, relativeDays } from '../utils'
import Modal from './Modal'

const emptyForm = {
  name: '', note: '', quota_gb: 50, validity_days: 30,
  max_ips: 1, speed_mbps: 0, node_ids: [],
}

function UserForm({ initial = emptyForm, nodes, onSubmit, submitLabel }) {
  const [form, setForm] = useState(() => (
    Object.hasOwn(initial, 'node_ids') && initial.node_ids.length === 0
      ? { ...initial, node_ids: nodes.filter((node) => node.enabled).map((node) => node.id) }
      : initial
  ))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const set = (name, value) => setForm((current) => ({ ...current, [name]: value }))

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try { await onSubmit(form) } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  return (
    <form className="form-grid" onSubmit={submit}>
      <label className="span-2"><span>نام کاربر</span><input value={form.name} onChange={(e) => set('name', e.target.value)} required /></label>
      <label><span>حجم (GB)</span><input type="number" min="0" step="1" value={form.quota_gb} onChange={(e) => set('quota_gb', Number(e.target.value))} /></label>
      <label><span>اعتبار (روز)</span><input type="number" min="0" value={form.validity_days} onChange={(e) => set('validity_days', Number(e.target.value))} /></label>
      <label><span>IP همزمان</span><input type="number" min="1" value={form.max_ips} onChange={(e) => set('max_ips', Number(e.target.value))} /></label>
      <label><span>سرعت (Mbps)</span><input type="number" min="0" step="1" value={form.speed_mbps} onChange={(e) => set('speed_mbps', Number(e.target.value))} /></label>
      {Object.hasOwn(form, 'node_ids') && (
        <fieldset className="span-2 node-selector">
          <legend>نودهای دسترسی</legend>
          {nodes.filter((node) => node.enabled).map((node) => (
            <label key={node.id} className="check-row">
              <input type="checkbox" checked={form.node_ids.includes(node.id)} onChange={(e) => set('node_ids', e.target.checked ? [...form.node_ids, node.id] : form.node_ids.filter((id) => id !== node.id))} />
              <span><strong>{node.name}</strong><small>{node.protocol.toUpperCase()}</small></span>
            </label>
          ))}
        </fieldset>
      )}
      <label className="span-2"><span>یادداشت</span><textarea rows="3" value={form.note} onChange={(e) => set('note', e.target.value)} /></label>
      {error && <div className="form-error span-2">{error}</div>}
      <div className="form-actions span-2"><button className="primary-button" disabled={busy}><Check size={17} />{busy ? 'در حال ثبت' : submitLabel}</button></div>
    </form>
  )
}

function Formats({ user, onClose, notify }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { api.formats(user.id).then(setData).catch((err) => setError(err.message)) }, [user.id])

  async function copyValue(value) {
    await copy(value)
    notify('در کلیپ‌بورد کپی شد')
  }

  return (
    <Modal title={`خروجی‌های ${user.name}`} onClose={onClose} wide>
      {!data && !error && <div className="page-loading"><RefreshCw className="spin" /> در حال ساخت خروجی‌ها</div>}
      {error && <div className="form-error">{error}</div>}
      {data && <div className="formats-list">
        <div className="format-row"><div><strong>Subscription</strong><span>VLESS / VMess + وضعیت حساب</span></div><code>{data.subscription_url}</code><button className="icon-button" onClick={() => copyValue(data.subscription_url)} title="کپی"><Copy size={18} /></button></div>
        <div className="format-row"><div><strong>Hiddify</strong><span>Deep link</span></div><code>{data.hiddify_url}</code><button className="icon-button" onClick={() => copyValue(data.hiddify_url)} title="کپی"><Copy size={18} /></button></div>
        {data.direct_links.map((link, index) => <div className="format-row" key={link}><div><strong>Direct {number(index + 1)}</strong><span>{link.split(':')[0].toUpperCase()}</span></div><code>{link}</code><button className="icon-button" onClick={() => copyValue(link)} title="کپی"><Copy size={18} /></button></div>)}
        {data.downloads.map((item) => <div className="format-row" key={item.node_id}><div><strong>{item.node_name}</strong><span>{item.protocol.toUpperCase()}</span></div><a className="secondary-button" href={item.url} target="_blank" rel="noreferrer">دریافت فایل</a></div>)}
      </div>}
    </Modal>
  )
}

export default function Users({ users, nodes, reload, notify }) {
  const [query, setQuery] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [editUser, setEditUser] = useState(null)
  const [formatsUser, setFormatsUser] = useState(null)
  const [busyId, setBusyId] = useState('')
  const filtered = useMemo(() => users.filter((user) => user.name.toLowerCase().includes(query.toLowerCase()) || user.id.includes(query)), [users, query])

  async function action(id, task, message) {
    setBusyId(id)
    try { await task(); await reload(); notify(message) } catch (err) { notify(err.message, 'error') } finally { setBusyId('') }
  }

  return (
    <div className="page-stack">
      <section className="toolbar">
        <div className="search-box"><Search size={18} /><input placeholder="جست‌وجوی نام یا شناسه" value={query} onChange={(event) => setQuery(event.target.value)} /></div>
        <button className="primary-button" onClick={() => setCreateOpen(true)}><Plus size={18} />کاربر جدید</button>
      </section>
      <section className="surface table-surface">
        <div className="table-heading"><div><span className="eyebrow">مدیریت دسترسی</span><h2>کاربران <b>{number(filtered.length)}</b></h2></div></div>
        <div className="data-table user-table">
          <div className="table-row table-head"><span>کاربر</span><span>مصرف</span><span>اعتبار</span><span>محدودیت</span><span>وضعیت</span><span /></div>
          {filtered.map((user) => {
            const percent = user.quota_bytes ? Math.min(100, user.used_bytes / user.quota_bytes * 100) : 0
            return <div className="table-row" key={user.id}>
              <div className="user-cell"><div className="avatar">{user.name.slice(0, 1).toUpperCase()}</div><div><strong>{user.name}</strong><small>{user.id.slice(0, 8)}</small></div></div>
              <div className="usage-cell"><div><strong>{bytes(user.used_bytes)}</strong><small>از {user.quota_bytes ? bytes(user.quota_bytes) : 'نامحدود'}</small></div><div className="progress"><i style={{ width: `${percent}%` }} /></div></div>
              <div className="validity-cell"><strong>{relativeDays(user.days_remaining)}</strong><small>{user.starts_at ? 'فعال شده' : 'شروع نشده'}</small></div>
              <div className="limit-cell"><strong>{number(user.max_ips)} IP</strong><small>{user.speed_limit_bps ? `${number(user.speed_limit_bps * 8 / 1_000_000)} Mbps` : 'سرعت نامحدود'}</small></div>
              <div className="status-cell"><span className={`status-pill ${user.allowed ? 'ok' : 'off'}`}>{user.allowed ? 'فعال' : 'متوقف'}</span><small>{number(user.active_ips)} آنلاین</small></div>
              <div className="row-actions">
                <button className="icon-button" onClick={() => setFormatsUser(user)} title="لینک‌ها"><Link2 size={17} /></button>
                <button className="icon-button" onClick={() => setEditUser(user)} title="ویرایش"><Pencil size={17} /></button>
                <button className="icon-button" disabled={busyId === user.id} onClick={() => action(user.id, () => api.updateUser(user.id, { active: !user.active }), user.active ? 'کاربر غیرفعال شد' : 'کاربر فعال شد')} title={user.active ? 'غیرفعال‌کردن' : 'فعال‌کردن'}>{user.active ? <Ban size={17} /> : <UserRoundCheck size={17} />}</button>
                <button className="icon-button danger" disabled={busyId === user.id} onClick={() => window.confirm(`کاربر «${user.name}» حذف شود؟`) && action(user.id, () => api.deleteUser(user.id), 'کاربر حذف شد')} title="حذف"><Trash2 size={17} /></button>
              </div>
            </div>
          })}
          {!filtered.length && <div className="empty-state">کاربری مطابق جست‌وجو وجود ندارد</div>}
        </div>
      </section>
      {createOpen && <Modal title="ساخت کاربر" onClose={() => setCreateOpen(false)}><UserForm nodes={nodes} submitLabel="ساخت و صدور دسترسی" onSubmit={async (form) => { await api.createUser(form); setCreateOpen(false); await reload(); notify('کاربر و دسترسی‌ها ساخته شدند') }} /></Modal>}
      {editUser && <Modal title={`ویرایش ${editUser.name}`} onClose={() => setEditUser(null)}><UserForm nodes={nodes} submitLabel="ذخیره تغییرات" initial={{ name: editUser.name, note: editUser.note, quota_gb: editUser.quota_bytes / 1024 ** 3, validity_days: editUser.validity_days, max_ips: editUser.max_ips, speed_mbps: editUser.speed_limit_bps * 8 / 1_000_000 }} onSubmit={async (form) => { await api.updateUser(editUser.id, form); setEditUser(null); await reload(); notify('تنظیمات کاربر ذخیره شد') }} /></Modal>}
      {formatsUser && <Formats user={formatsUser} onClose={() => setFormatsUser(null)} notify={notify} />}
    </div>
  )
}
