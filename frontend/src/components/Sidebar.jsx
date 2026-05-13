import { NavLink, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  RiDashboardLine,
  RiBriefcaseLine,
  RiFileAddLine,
  RiBarChartBoxLine,
  RiLogoutCircleLine,
  RiFlashlightLine,
  RiShieldStarLine,
} from 'react-icons/ri'
import { useAuth } from '../context/AuthContext.jsx'
import ThemeToggle from './ThemeToggle.jsx'

const NAV_ITEMS = [
  { to: '/dashboard', icon: RiDashboardLine, label: 'Dashboard' },
  { to: '/analytics', icon: RiBarChartBoxLine, label: 'Analytics' },
  { to: '/jobs/new', icon: RiBriefcaseLine, label: 'Post a Job' },
  { to: '/resumes/upload', icon: RiFileAddLine, label: 'Upload Resumes' },
]

const navLinkStyle = ({ isActive }) => ({
  display: 'flex',
  alignItems: 'center',
  gap: '12px',
  padding: '12px 14px',
  borderRadius: '14px',
  fontSize: '14px',
  fontWeight: isActive ? 700 : 500,
  color: isActive ? 'var(--text-primary)' : 'var(--text-muted)',
  background: isActive ? 'rgba(124,58,237,0.14)' : 'transparent',
  border: isActive ? '1px solid rgba(124,58,237,0.24)' : '1px solid transparent',
  textDecoration: 'none',
  transition: 'all 0.2s ease',
})

export default function Sidebar({ open = false, onNavigate = () => {} }) {
  const navigate = useNavigate()
  const { user, logout } = useAuth()

  return (
    <aside className={`sidebar ${open ? 'open' : ''}`}>
      <div style={{ padding: '24px 20px 18px', borderBottom: '1px solid var(--border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{
            width: 42,
            height: 42,
            background: 'var(--grad-brand)',
            borderRadius: '14px',
            display: 'grid',
            placeItems: 'center',
            boxShadow: 'var(--shadow-glow)',
          }}>
            <RiFlashlightLine style={{ color: '#fff', fontSize: '18px' }} />
          </div>
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '16px', color: 'var(--text-primary)' }}>
              HireSense AI
            </div>
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', fontWeight: 700, letterSpacing: '0.12em' }}>
              RECRUITER INTELLIGENCE
            </div>
          </div>
        </div>
      </div>

      <nav style={{ flex: 1, padding: '16px 12px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
        <div style={{ fontSize: '10px', color: 'var(--text-muted)', fontWeight: 800, letterSpacing: '0.16em', padding: '0 8px', marginBottom: '8px' }}>
          WORKSPACE
        </div>
        {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
          <NavLink key={to} to={to} style={navLinkStyle} onClick={onNavigate}>
            {({ isActive }) => (
              <>
                <Icon style={{ fontSize: '18px', color: isActive ? 'var(--brand-primary)' : 'inherit', flexShrink: 0 }} />
                <span>{label}</span>
                {isActive && (
                  <motion.div
                    layoutId="activeIndicator"
                    style={{ marginLeft: 'auto', width: 8, height: 8, borderRadius: '50%', background: 'var(--brand-primary)' }}
                  />
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div style={{ padding: '16px 12px', borderTop: '1px solid var(--border)', display: 'grid', gap: 12 }}>
        <div style={{
          background: 'rgba(124,58,237,0.08)',
          border: '1px solid rgba(124,58,237,0.18)',
          borderRadius: '16px',
          padding: '14px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <RiShieldStarLine style={{ color: 'var(--brand-primary)', fontSize: 15 }} />
            <span style={{ fontSize: '11px', fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '0.08em' }}>
              {String(user?.role || 'recruiter').toUpperCase()}
            </span>
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>
            {user?.full_name || user?.email || 'Signed in user'}
          </div>
        </div>

        <ThemeToggle />

        <button
          className="btn btn-secondary"
          type="button"
          onClick={async () => {
            await logout()
            onNavigate()
            navigate('/login')
          }}
          style={{ justifyContent: 'center' }}
        >
          <RiLogoutCircleLine />
          Sign out
        </button>
      </div>
    </aside>
  )
}
