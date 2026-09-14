import { useState } from 'react'
import { Check, CircleOff, Fingerprint, Globe2, Pencil, Plus, Radio, Route, Server } from 'lucide-react'
import { api } from '../api'
import { number } from '../utils'
import Modal from './Modal'

const defaults = {
  name: '', slug: '', kind: 'xray', protocol: 'vless', transport: 'websocket',
  host: 'auto', port: 443, security: 'tls', sni: '', websocket_host: 'auto', path: '/edge',
  fingerprint: 'chrome', alpn: ['http/1.1'], enabled: true, metadata: { adaptive_endpoint: true },
}

function NodeForm({ initial = defaults, editing = false, onSubmit }) {
  const [form, setForm] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const set = (name, value) => setForm((current) => ({ ...current, [name]: value }))

  function protocol(value) {
    if (value === 'wireguard') setForm((f) => ({ ...f, protocol: value, kind: 'wireguard', transport: 'external', security: 'none', port: 51820 }))
    else if (value === 'cisco') setForm((f) => ({ ...f, protocol: value, kind: 'cisco', transport: 'external', security: 'tls', port: 443 }))
    else setForm((f) => ({ ...f, protocol: value, kind: 'xray', transport: 'websocket', host: 'auto', port: 443, security: 'tls', sni: '', websocket_host: 'auto', metadata: { ...f.metadata, adaptive_endpoint: true } }))
  }

  function adaptiveEndpoint(enabled) {
    setForm((f) => ({
      ...f,
      host: enabled ? 'auto' : (f.host === 'auto' ? '' : f.host),
      port: enabled ? (f.transport === 'tcp' ? 2053 : 443) : f.port,
      security: enabled ? (f.transport === 'tcp' ? 'reality' : 'tls') : f.security,
      sni: enabled && f.transport !== 'tcp' ? '' : f.sni,
      websocket_host: enabled ? 'auto' : (f.websocket_host === 'auto' ? '' : f.websocket_host),
      metadata: { ...f.metadata, adaptive_endpoint: enabled },
    }))
  }

  async function submit(event) {
    event.preventDefault(); setBusy(true); setError('')
    try { await onSubmit(form) } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const xray = form.kind === 'xray'
  const reality = xray && form.transport === 'tcp' && form.security === 'reality'
  const adaptive = xray && Boolean(form.metadata?.adaptive_endpoint)
  return <form className="form-grid" onSubmit={submit}>
    <label><span>نام نمایشی</span><input value={form.name} onChange={(e) => set('name', e.target.value)} required /></label>
    {!editing && <label><span>شناسه</span><input dir="ltr" value={form.slug} onChange={(e) => set('slug', e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))} required /></label>}
    {!editing && <label><span>پروتکل</span><select value={form.protocol} onChange={(e) => protocol(e.target.value)}><option value="vless">VLESS</option><option value="vmess">VMess</option><option value="wireguard">WireGuard</option><option value="cisco">Cisco / OpenConnect</option></select></label>}
    {xray && <>
      <label className="check-row span-2"><input type="checkbox" checked={adaptive} onChange={(e) => adaptiveEndpoint(e.target.checked)} /><span>آدرس از دامنه پنل</span></label>
    </>}
    <label><span>آدرس عمومی</span><input dir="ltr" value={form.host} onChange={(e) => set('host', e.target.value)} required disabled={adaptive} /></label>
    <label><span>پورت</span><input type="number" min="1" max="65535" value={form.port} onChange={(e) => set('port', Number(e.target.value))} disabled={adaptive} /></label>
    {xray && <>
      <label><span>امنیت</span><select value={form.security} onChange={(e) => set('security', e.target.value)} disabled={adaptive}><option value="tls">TLS</option><option value="reality">REALITY</option><option value="none">None</option></select></label>
      <label><span>SNI</span><input dir="ltr" value={form.sni} onChange={(e) => set('sni', e.target.value)} disabled={adaptive} /></label>
      {!reality && <label><span>WebSocket Host</span><input dir="ltr" value={form.websocket_host} onChange={(e) => set('websocket_host', e.target.value)} disabled={adaptive} /></label>}
      {!reality && <label><span>Path پایه</span><input dir="ltr" value={form.path} onChange={(e) => set('path', e.target.value)} /></label>}
      <label><span>Fingerprint</span><select value={form.fingerprint} onChange={(e) => set('fingerprint', e.target.value)}>{['chrome', 'firefox', 'safari', 'ios', 'android', 'edge', 'random', 'randomized'].map((item) => <option key={item}>{item}</option>)}</select></label>
      <fieldset className="alpn-field"><legend>ALPN</legend>{['http/1.1', 'h2', 'h3'].map((item) => <label className="check-row compact" key={item}><input type="checkbox" checked={form.alpn.includes(item)} onChange={(e) => set('alpn', e.target.checked ? [...form.alpn, item] : form.alpn.filter((value) => value !== item))} /><span>{item}</span></label>)}</fieldset>
    </>}
    {form.protocol === 'wireguard' && <>
      <label className="span-2"><span>کلید عمومی سرور</span><input dir="ltr" value={form.metadata.server_public_key || ''} onChange={(e) => set('metadata', { ...form.metadata, server_public_key: e.target.value })} required /></label>
      <label><span>شبکه کاربران</span><input dir="ltr" value={form.metadata.client_cidr || '10.66.0.0/24'} onChange={(e) => set('metadata', { ...form.metadata, client_cidr: e.target.value })} /></label>
      <label><span>DNS</span><input dir="ltr" value={form.metadata.dns || '1.1.1.1'} onChange={(e) => set('metadata', { ...form.metadata, dns: e.target.value })} /></label>
    </>}
    {form.protocol === 'cisco' && <label><span>Group</span><input dir="ltr" value={form.metadata.group || 'ARENA'} onChange={(e) => set('metadata', { ...form.metadata, group: e.target.value })} /></label>}
    {error && <div className="form-error span-2">{error}</div>}
    <div className="form-actions span-2"><button className="primary-button" disabled={busy}><Check size={17} />{busy ? 'در حال ذخیره' : editing ? 'ذخیره نود' : 'ساخت نود'}</button></div>
  </form>
}

export default function Nodes({ nodes, reload, notify }) {
  const [createOpen, setCreateOpen] = useState(false)
  const [editNode, setEditNode] = useState(null)

  async function toggle(node) {
    try { await api.updateNode(node.id, { enabled: !node.enabled }); await reload(); notify(node.enabled ? 'نود متوقف شد' : 'نود فعال شد') } catch (err) { notify(err.message, 'error') }
  }

  return <div className="page-stack">
    <section className="toolbar toolbar-end"><button className="primary-button" onClick={() => setCreateOpen(true)}><Plus size={18} />نود جدید</button></section>
    <section className="node-grid">
      {nodes.map((node) => <article className={`node-card ${node.enabled ? '' : 'disabled'}`} key={node.id}>
        <header><div className={`protocol-mark protocol-${node.protocol}`}><Server size={21} /></div><div><strong>{node.name}</strong><span>{node.slug}</span></div><span className={`status-pill ${node.enabled ? 'ok' : 'off'}`}>{node.enabled ? 'فعال' : 'خاموش'}</span></header>
        <div className="node-address"><Globe2 size={17} /><strong dir={node.metadata?.adaptive_endpoint ? 'rtl' : 'ltr'}>{node.metadata?.adaptive_endpoint ? 'دامنه پنل (خودکار)' : `${node.host}:${node.port}`}</strong></div>
        <dl className="node-specs">
          <div><dt><Route size={15} />پروتکل</dt><dd>{node.protocol.toUpperCase()} / {node.transport === 'websocket' ? 'WS' : node.transport === 'tcp' ? 'TCP / REALITY' : 'External'}</dd></div>
          <div><dt><Fingerprint size={15} />Fingerprint</dt><dd>{node.fingerprint}</dd></div>
          <div><dt><Radio size={15} />ALPN</dt><dd>{node.alpn.join(', ') || 'none'}</dd></div>
        </dl>
        <footer><button className="secondary-button" onClick={() => setEditNode(node)}><Pencil size={16} />ویرایش</button><button className={`icon-button ${node.enabled ? 'danger' : ''}`} onClick={() => toggle(node)} title={node.enabled ? 'توقف نود' : 'فعال‌سازی'}><CircleOff size={18} /></button></footer>
      </article>)}
      {!nodes.length && <div className="empty-state">نودی تعریف نشده است</div>}
    </section>
    {createOpen && <Modal title="تعریف نود" onClose={() => setCreateOpen(false)} wide><NodeForm onSubmit={async (form) => { await api.createNode(form); setCreateOpen(false); await reload(); notify('نود ساخته شد') }} /></Modal>}
    {editNode && <Modal title={`ویرایش ${editNode.name}`} onClose={() => setEditNode(null)} wide><NodeForm editing initial={editNode} onSubmit={async (form) => { const { name, enabled, host, port, security, sni, websocket_host, path, fingerprint, alpn, metadata } = form; await api.updateNode(editNode.id, { name, enabled, host, port, security, sni, websocket_host, path, fingerprint, alpn, metadata }); setEditNode(null); await reload(); notify('نود ذخیره شد') }} /></Modal>}
  </div>
}
