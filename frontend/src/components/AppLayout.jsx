import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { RiMenuLine } from 'react-icons/ri'
import Sidebar from './Sidebar.jsx'

export default function AppLayout() {
  const location = useLocation()
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  useEffect(() => {
    setMobileNavOpen(false)
  }, [location.pathname])

  return (
    <div className="app-shell">
      <button
        type="button"
        className="mobile-sidebar-toggle btn btn-secondary btn-sm"
        onClick={() => setMobileNavOpen((value) => !value)}
        aria-label="Toggle navigation"
      >
        <RiMenuLine />
      </button>
      <div
        className={`sidebar-backdrop ${mobileNavOpen ? 'open' : ''}`}
        onClick={() => setMobileNavOpen(false)}
        aria-hidden="true"
      />
      <Sidebar open={mobileNavOpen} onNavigate={() => setMobileNavOpen(false)} />
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  )
}
