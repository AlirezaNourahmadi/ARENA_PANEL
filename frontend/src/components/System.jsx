import { CheckCircle2, CircleAlert, Database, ExternalLink, GitBranch, RadioTower, ServerCog } from 'lucide-react'

export default function System({ health }) {
  const ok = health?.status === 'ok'
  return <div className="page-stack system-page">
    <section className={`health-banner ${ok ? 'healthy' : 'degraded'}`}>
      {ok ? <CheckCircle2 size={28} /> : <CircleAlert size={28} />}
      <div><strong>{ok ? 'سرویس آماده است' : 'سرویس نیاز به بررسی دارد'}</strong><span>ARENA Control Plane / Phase 01</span></div>
      <code>v{health?.version || '0.1.0'}</code>
    </section>
    <section className="system-grid">
      <article className="system-item"><Database size={22} /><div><span>پایگاه داده</span><strong>{health?.database || 'unknown'}</strong></div><i className={health?.database === 'ok' ? 'ok' : 'error'} /></article>
      <article className="system-item"><RadioTower size={22} /><div><span>هسته Xray</span><strong>{health?.xray || 'unknown'}</strong></div><i className={health?.xray === 'running' || health?.xray === 'disabled' ? 'ok' : 'error'} /></article>
      <article className="system-item"><ServerCog size={22} /><div><span>Gateway</span><strong>policy enforced</strong></div><i className="ok" /></article>
      <article className="system-item"><GitBranch size={22} /><div><span>نسخه طرح</span><strong>Phase 01</strong></div><i className="ok" /></article>
    </section>
    <section className="surface runtime-table">
      <div className="section-heading"><div><span className="eyebrow">RUNTIME CONTRACT</span><h2>اجزای اجرایی</h2></div></div>
      <div className="runtime-row"><span>Control API</span><code>:8000</code><strong>FastAPI / PostgreSQL</strong></div>
      <div className="runtime-row"><span>WebSocket Gateway</span><code>:8081</code><strong>IP + Speed + Trace</strong></div>
      <div className="runtime-row"><span>VLESS data plane</span><code>:11000</code><strong>Xray Core</strong></div>
      <div className="runtime-row"><span>VMess data plane</span><code>:11001</code><strong>Xray Core</strong></div>
    </section>
  </div>
}
