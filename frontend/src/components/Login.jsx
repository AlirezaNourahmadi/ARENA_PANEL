import { useState } from 'react'
import { ArrowLeft, Eye, EyeOff, KeyRound, UserRound } from 'lucide-react'

export default function Login({ onLogin, busy, error }) {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [visible, setVisible] = useState(false)

  function submit(event) {
    event.preventDefault()
    onLogin({ username, password })
  }

  return (
    <main className="login-page">
      <section className="login-brand">
        <img src="/arena-mark.png" alt="" className="login-mark" />
        <div>
          <span className="brand-word">ARENA</span>
          <p>Network Control Plane</p>
        </div>
      </section>
      <section className="login-panel">
        <div className="login-heading">
          <span className="eyebrow">ورود مدیر</span>
          <h1>مرکز کنترل ARENA</h1>
        </div>
        <form onSubmit={submit}>
          <label>
            <span>نام کاربری</span>
            <div className="input-with-icon">
              <UserRound size={18} />
              <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required />
            </div>
          </label>
          <label>
            <span>رمز عبور</span>
            <div className="input-with-icon">
              <KeyRound size={18} />
              <input type={visible ? 'text' : 'password'} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required autoFocus />
              <button className="field-action" type="button" onClick={() => setVisible(!visible)} title={visible ? 'پنهان کردن' : 'نمایش رمز'}>
                {visible ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </label>
          {error && <div className="form-error" role="alert">{error}</div>}
          <button className="primary-button login-button" disabled={busy}>
            <span>{busy ? 'در حال بررسی' : 'ورود امن'}</span>
            <ArrowLeft size={18} />
          </button>
        </form>
      </section>
      <footer className="login-footer">ARENA / PHASE 01</footer>
    </main>
  )
}
