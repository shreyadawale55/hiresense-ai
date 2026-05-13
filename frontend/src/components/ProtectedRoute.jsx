import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

export default function ProtectedRoute({ children }) {
  const { isAuthenticated, hydrated } = useAuth()
  if (!hydrated) {
    return (
      <div className="page-content" style={{ display: 'grid', placeItems: 'center', minHeight: '100vh' }}>
        <div className="spinner spinner-lg" />
      </div>
    )
  }
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  return children
}

