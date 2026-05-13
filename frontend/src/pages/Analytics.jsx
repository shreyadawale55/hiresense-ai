import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  PieChart,
  Pie,
  Cell,
  Legend,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
} from 'recharts'
import { RiArrowLeftLine, RiBarChart2Line, RiShieldStarLine, RiRobot2Line, RiSignalTowerLine } from 'react-icons/ri'
import { jobsApi, screeningApi } from '../services/api.js'

const COLORS = ['#10b981', '#06b6d4', '#f59e0b', '#ef4444']

export default function Analytics() {
  const [selectedJobId, setSelectedJobId] = useState(null)

  const jobsQuery = useQuery({
    queryKey: ['analytics-jobs'],
    queryFn: async () => (await jobsApi.list({ page_size: 50 })).data,
  })

  useEffect(() => {
    const firstJobId = jobsQuery.data?.items?.[0]?.id
    if (!selectedJobId && firstJobId) setSelectedJobId(firstJobId)
  }, [jobsQuery.data, selectedJobId])

  const selectedJob = useMemo(
    () => jobsQuery.data?.items?.find((job) => job.id === selectedJobId) || jobsQuery.data?.items?.[0] || null,
    [jobsQuery.data, selectedJobId]
  )

  const resultsQuery = useQuery({
    queryKey: ['analytics-results', selectedJob?.id],
    queryFn: async () => (await screeningApi.getResults(selectedJob.id)).data,
    enabled: Boolean(selectedJob?.id),
  })

  const statsQuery = useQuery({
    queryKey: ['analytics-stats', selectedJob?.id],
    queryFn: async () => (await screeningApi.getStats(selectedJob.id)).data,
    enabled: Boolean(selectedJob?.id),
  })

  const recommendations = useMemo(() => {
    const counts = { strong_yes: 0, yes: 0, maybe: 0, no: 0 }
    for (const item of resultsQuery.data?.items || []) {
      const key = item.ai?.recommendation || 'maybe'
      counts[key] = (counts[key] || 0) + 1
    }
    return [
      { name: 'Strong Yes', value: counts.strong_yes },
      { name: 'Yes', value: counts.yes },
      { name: 'Maybe', value: counts.maybe },
      { name: 'No', value: counts.no },
    ]
  }, [resultsQuery.data])

  const scoreTrend = useMemo(() => (
    resultsQuery.data?.items?.map((item, index) => ({
      name: item.candidate_name || `Candidate ${index + 1}`,
      score: item.score?.overall_score || 0,
      semantic: item.score?.semantic_score || 0,
    })) || []
  ), [resultsQuery.data])

  const fairnessSnapshot = useMemo(() => {
    const items = resultsQuery.data?.items || []
    const biasCount = items.filter((item) => item.ai?.bias_detected).length
    const avgConfidence = items.length ? items.reduce((sum, item) => sum + ((item.score?.confidence_score || 0) * 100), 0) / items.length : 0
    return [
      { label: 'Bias flags', value: biasCount },
      { label: 'Avg confidence', value: `${Math.round(avgConfidence)}%` },
      { label: 'Completed', value: statsQuery.data?.completed || 0 },
      { label: 'Mean semantic', value: `${Math.round(statsQuery.data?.avg_semantic_score || 0)}%` },
    ]
  }, [resultsQuery.data, statsQuery.data])

  return (
    <div className="page-content">
      <Link to="/dashboard" className="btn btn-ghost btn-sm" style={{ marginBottom: 24, display: 'inline-flex' }}>
        <RiArrowLeftLine /> Back to Dashboard
      </Link>

      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} style={{ marginBottom: 24 }}>
        <h1 style={{ marginBottom: 8 }}>
          Analytics <span className="gradient-text">Overview</span>
        </h1>
        <p className="text-sm text-muted">
          Track recommendation distribution, confidence, semantic fit, and fairness signals at a glance.
        </p>
      </motion.div>

      <div className="grid-4 mb-lg">
        <div className="card">
          <div className="stat-icon" style={{ background: 'linear-gradient(135deg,#7c3aed,#4f46e5)' }}>
            <RiBarChart2Line style={{ color: '#fff', fontSize: 22 }} />
          </div>
          <div className="stat-info" style={{ marginTop: 12 }}>
            <div className="stat-value gradient-text">{jobsQuery.data?.items?.length || 0}</div>
            <div className="stat-label">Jobs tracked</div>
          </div>
        </div>
        <div className="card">
          <div className="stat-icon" style={{ background: 'linear-gradient(135deg,#06b6d4,#0891b2)' }}>
            <RiSignalTowerLine style={{ color: '#fff', fontSize: 22 }} />
          </div>
          <div className="stat-info" style={{ marginTop: 12 }}>
            <div className="stat-value gradient-text">{Math.round(statsQuery.data?.avg_score || 0)}%</div>
            <div className="stat-label">Mean overall score</div>
          </div>
        </div>
        <div className="card">
          <div className="stat-icon" style={{ background: 'linear-gradient(135deg,#10b981,#059669)' }}>
            <RiRobot2Line style={{ color: '#fff', fontSize: 22 }} />
          </div>
          <div className="stat-info" style={{ marginTop: 12 }}>
            <div className="stat-value gradient-text">{Math.round(statsQuery.data?.avg_semantic_score || 0)}%</div>
            <div className="stat-label">Mean semantic score</div>
          </div>
        </div>
        <div className="card">
          <div className="stat-icon" style={{ background: 'linear-gradient(135deg,#f59e0b,#d97706)' }}>
            <RiShieldStarLine style={{ color: '#fff', fontSize: 22 }} />
          </div>
          <div className="stat-info" style={{ marginTop: 12 }}>
            <div className="stat-value gradient-text">{Math.round((statsQuery.data?.avg_confidence_score || 0) * 100)}%</div>
            <div className="stat-label">Average confidence</div>
          </div>
        </div>
      </div>

      <div className="dashboard-secondary-grid" style={{ marginBottom: 20 }}>
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
            <h3 style={{ fontSize: 15 }}>Recommendation Distribution</h3>
            <select className="form-select" style={{ width: 'min(240px, 100%)' }} value={selectedJobId || ''} onChange={(event) => setSelectedJobId(event.target.value)}>
              {jobsQuery.data?.items?.map((job) => (
                <option key={job.id} value={job.id}>{job.title} · {job.company}</option>
              ))}
            </select>
          </div>
          <div style={{ width: '100%', height: 320 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={recommendations} dataKey="value" nameKey="name" innerRadius={70} outerRadius={110} paddingAngle={4}>
                  {recommendations.map((entry, index) => (
                    <Cell key={entry.name} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card">
          <h3 style={{ fontSize: 15, marginBottom: 14 }}>Fairness Snapshot</h3>
          <div className="grid-2" style={{ gap: 14 }}>
            {fairnessSnapshot.map((item) => (
              <div key={item.label} className="card card-sm" style={{ background: 'rgba(255,255,255,0.02)' }}>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 6 }}>{item.label}</div>
                <div style={{ fontSize: 24, fontWeight: 800 }}>{item.value}</div>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 18, padding: 16, borderRadius: 16, border: '1px solid rgba(16,185,129,0.18)', background: 'rgba(16,185,129,0.05)' }}>
            <strong style={{ display: 'block', marginBottom: 6 }}>SDG 8 aligned screening</strong>
            <p style={{ margin: 0, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
              The fairness panel tracks bias flags, confidence, and semantic consistency so recruiter decisions stay transparent and skills-first.
            </p>
          </div>
        </div>
      </div>

      <div className="card">
        <h3 style={{ fontSize: 15, marginBottom: 18 }}>Score Trend</h3>
        <div style={{ width: '100%', height: 360 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={scoreTrend}>
              <defs>
                <linearGradient id="scoreFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#7c3aed" stopOpacity={0.6} />
                  <stop offset="95%" stopColor="#7c3aed" stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
              <XAxis dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
              <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
              <Tooltip />
              <Area type="monotone" dataKey="score" stroke="#7c3aed" fill="url(#scoreFill)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}
