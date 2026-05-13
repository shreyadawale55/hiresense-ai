import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { RiLock2Line, RiMailLine, RiShieldStarLine, RiArrowRightLine } from 'react-icons/ri'
import { useAuth } from '../context/AuthContext.jsx'
import ThemeToggle from '../components/ThemeToggle.jsx'

export default function Login() {
  const navigate = useNavigate()
  const { login } = useAuth()
  const [email, setEmail] = useState('admin@hiresense.ai')
  const [password, setPassword] = useState('ChangeMe123!')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (event) => {
    event.preventDefault()
    setLoading(true)
    try {
      await login(email, password)
      navigate('/dashboard')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-layout">
      <div className="login-hero">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 48,
              height: 48,
              borderRadius: 14,
              background: 'var(--grad-brand)',
              display: 'grid',
              placeItems: 'center',
              boxShadow: 'var(--shadow-glow)',
            }}>
              <RiShieldStarLine style={{ color: '#fff', fontSize: 24 }} />
            </div>
            <div>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: 20 }}>HireSense AI</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', letterSpacing: '0.14em' }}>Hiring Intelligence Platform</div>
            </div>
          </div>
          <ThemeToggle />
        </div>

        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>
          <div style={{ maxWidth: 760 }}>
            <p style={{ textTransform: 'uppercase', letterSpacing: '0.16em', color: 'var(--text-muted)', fontSize: 12, fontWeight: 700 }}>
              Production-grade AI recruiting
            </p>
            <h1 style={{ fontSize: 'clamp(3rem, 8vw, 5.25rem)', lineHeight: 0.95, margin: '16px 0 20px' }}>
              Semantic hiring, explainability, and fairness in one workspace.
            </h1>
            <p style={{ fontSize: 18, maxWidth: 620, color: 'var(--text-secondary)' }}>
              Secure recruiter access, resume embeddings, live screening progress, and grounded AI explanations designed to look at home on a top-tier ML resume.
            </p>

            <div className="login-highlights-grid">
              {[
                ['JWT + RBAC', 'Recruiter/Admin protected access'],
                ['Semantic Search', 'FAISS-ready embedding pipeline'],
                ['Live Insights', 'Websocket task notifications'],
              ].map(([title, description]) => (
                <div key={title} className="card card-sm card-glass">
                  <div style={{ fontWeight: 700, marginBottom: 6 }}>{title}</div>
                  <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>{description}</div>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, marginTop: 32, color: 'var(--text-muted)', fontSize: 13 }}>
          <span>SDG 8 aligned · fair, skills-first screening</span>
          <span>FastAPI · React · PyTorch · Redis · PostgreSQL</span>
        </div>
      </div>

      <div className="login-panel">
        <motion.form
          onSubmit={handleSubmit}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="card"
          style={{ width: '100%', maxWidth: 460, padding: 32 }}
        >
          <div style={{ marginBottom: 26 }}>
            <p style={{ textTransform: 'uppercase', letterSpacing: '0.16em', color: 'var(--text-muted)', fontSize: 12, fontWeight: 700 }}>
              Secure Access
            </p>
            <h2 style={{ fontSize: 32, marginTop: 8 }}>Sign in to your recruiter console</h2>
            <p style={{ color: 'var(--text-secondary)', marginTop: 8 }}>
              Use your seeded admin credentials or a recruiter account created by an admin.
            </p>
          </div>

          <label className="form-group" style={{ marginBottom: 16, display: 'block' }}>
            <span className="form-label">Email</span>
            <div style={{ position: 'relative' }}>
              <RiMailLine style={{ position: 'absolute', left: 14, top: 14, color: 'var(--text-muted)' }} />
              <input
                className="form-input"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="recruiter@company.com"
                style={{ paddingLeft: 40 }}
              />
            </div>
          </label>

          <label className="form-group" style={{ marginBottom: 16, display: 'block' }}>
            <span className="form-label">Password</span>
            <div style={{ position: 'relative' }}>
              <RiLock2Line style={{ position: 'absolute', left: 14, top: 14, color: 'var(--text-muted)' }} />
              <input
                className="form-input"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="••••••••••"
                style={{ paddingLeft: 40 }}
              />
            </div>
          </label>

          <button type="submit" className="btn btn-primary btn-lg" style={{ width: '100%', justifyContent: 'center', marginTop: 12 }} disabled={loading}>
            {loading ? (
              <>
                <div className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} />
                Signing in...
              </>
            ) : (
              <>
                Enter Workspace <RiArrowRightLine />
              </>
            )}
          </button>

          <div style={{ marginTop: 20, fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.7 }}>
            Default bootstrap example:
            <div style={{ marginTop: 8, padding: 12, borderRadius: 12, background: 'var(--bg-surface1)', border: '1px solid var(--border)' }}>
              <div>Email: <strong>admin@hiresense.ai</strong></div>
              <div>Password: <strong>ChangeMe123!</strong></div>
            </div>
          </div>
        </motion.form>
      </div>
    </div>
  )
}
