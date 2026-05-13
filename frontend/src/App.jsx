import { Navigate, Route, Routes } from 'react-router-dom'
import AppLayout from './components/AppLayout.jsx'
import ProtectedRoute from './components/ProtectedRoute.jsx'
import Dashboard from './pages/Dashboard.jsx'
import JobCreate from './pages/JobCreate.jsx'
import ResumeUpload from './pages/ResumeUpload.jsx'
import CandidateDetail from './pages/CandidateDetail.jsx'
import Login from './pages/Login.jsx'
import Analytics from './pages/Analytics.jsx'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/jobs/new" element={<JobCreate />} />
        <Route path="/resumes/upload" element={<ResumeUpload />} />
        <Route path="/candidates/:screeningId" element={<CandidateDetail />} />
      </Route>
    </Routes>
  )
}

