import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import {
  RiBriefcaseLine,
  RiFileListLine,
  RiUserLine,
  RiFlashlightLine,
  RiAddLine,
  RiArrowRightLine,
  RiCheckboxCircleLine,
  RiTimeLine,
  RiSparklingLine,
  RiSignalTowerLine,
  RiRobot2Line,
} from 'react-icons/ri'
import { jobsApi, notificationsApi, screeningApi } from '../services/api.js'
import { useAuth } from '../context/AuthContext.jsx'
import { useWebSocket } from '../hooks/useWebSocket.js'

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  show: (i = 0) => ({ opacity: 1, y: 0, transition: { delay: i * 0.08, duration: 0.4 } }),
}

const RECOMMENDATION_CONFIG = {
  strong_yes: { label: 'Strong Yes', color: '#10b981', bg: 'rgba(16,185,129,0.15)' },
  yes: { label: 'Yes', color: '#06b6d4', bg: 'rgba(6,182,212,0.15)' },
  maybe: { label: 'Maybe', color: '#f59e0b', bg: 'rgba(245,158,11,0.15)' },
  no: { label: 'No', color: '#ef4444', bg: 'rgba(239,68,68,0.15)' },
}

function StatCard({ icon: Icon, label, value, change, iconBg, delay }) {
  return (
    <motion.div className="stat-card" variants={fadeUp} custom={delay} initial="hidden" animate="show">
      <div className="stat-icon" style={{ background: iconBg }}>
        <Icon style={{ color: '#fff', fontSize: 22 }} />
      </div>
      <div className="stat-info">
        <div className="stat-value gradient-text">{value}</div>
        <div className="stat-label">{label}</div>
        {change && <div className="stat-change text-success">{change}</div>}
      </div>
    </motion.div>
  )
}

function EmptyState({ title, description, action }) {
  return (
    <div style={{ padding: 48, textAlign: 'center' }}>
      <div style={{
        width: 72,
        height: 72,
        borderRadius: '24px',
        background: 'rgba(124,58,237,0.12)',
        display: 'grid',
        placeItems: 'center',
        margin: '0 auto 16px',
      }}>
        <RiSparklingLine style={{ color: 'var(--brand-primary)', fontSize: 28 }} />
      </div>
      <h3 style={{ marginBottom: 8 }}>{title}</h3>
      <p style={{ marginBottom: 20, color: 'var(--text-muted)' }}>{description}</p>
      {action}
    </div>
  )
}

function FeedItem({ event }) {
  const label = event?.type || event?.event_type || 'event'
  const message = event?.message || event?.title || event?.status || JSON.stringify(event)
  return (
    <div style={{
      padding: 12,
      borderRadius: 14,
      border: '1px solid var(--border)',
      background: 'rgba(255,255,255,0.02)',
      display: 'grid',
      gap: 4,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <RiSignalTowerLine style={{ color: 'var(--brand-accent)' }} />
        <span style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>{label}</span>
      </div>
      <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>{message}</div>
    </div>
  )
}

export default function Dashboard() {
  const queryClient = useQueryClient()
  const { accessToken } = useAuth()
  const [selectedJobId, setSelectedJobId] = useState(null)
  const [liveEvents, setLiveEvents] = useState([])

  const jobsQuery = useQuery({
    queryKey: ['jobs'],
    queryFn: async () => (await jobsApi.list({ page_size: 12 })).data,
  })

  useEffect(() => {
    const firstJobId = jobsQuery.data?.items?.[0]?.id
    if (!selectedJobId && firstJobId) {
      setSelectedJobId(firstJobId)
    }
  }, [jobsQuery.data, selectedJobId])

  const selectedJob = useMemo(
    () => jobsQuery.data?.items?.find((job) => job.id === selectedJobId) || jobsQuery.data?.items?.[0] || null,
    [jobsQuery.data, selectedJobId]
  )

  useEffect(() => {
    if (selectedJob?.id && selectedJob.id !== selectedJobId) {
      setSelectedJobId(selectedJob.id)
    }
  }, [selectedJob, selectedJobId])

  const resultsQuery = useQuery({
    queryKey: ['screening-results', selectedJob?.id],
    queryFn: async () => (await screeningApi.getResults(selectedJob.id)).data,
    enabled: Boolean(selectedJob?.id),
  })

  const statsQuery = useQuery({
    queryKey: ['screening-stats', selectedJob?.id],
    queryFn: async () => (await screeningApi.getStats(selectedJob.id)).data,
    enabled: Boolean(selectedJob?.id),
  })

  const topCandidates = resultsQuery.data?.items || []
  const topCandidate = topCandidates[0]

  const radarData = topCandidate ? [
    { subject: 'Skills', A: topCandidate.score?.skill_match_score || 0 },
    { subject: 'Semantic', A: topCandidate.score?.semantic_score || 0 },
    { subject: 'Experience', A: topCandidate.score?.experience_score || 0 },
    { subject: 'Education', A: topCandidate.score?.education_score || 0 },
    { subject: 'Confidence', A: (topCandidate.score?.confidence_score || 0) * 100 },
  ] : []

  const barData = topCandidates.slice(0, 8).map((candidate) => ({
    name: candidate.candidate_name || 'Unknown',
    score: candidate.score?.overall_score || 0,
  }))

  const liveUrl = selectedJob?.id && accessToken ? notificationsApi.screeningUrl(selectedJob.id, accessToken) : null
  const handleLiveMessage = useCallback((payload) => {
    setLiveEvents((prev) => [payload, ...prev].slice(0, 8))
    if (payload?.type?.startsWith('screening.')) {
      queryClient.invalidateQueries({ queryKey: ['screening-results', selectedJob?.id] })
      queryClient.invalidateQueries({ queryKey: ['screening-stats', selectedJob?.id] })
    }
  }, [queryClient, selectedJob?.id])

  const liveStream = useWebSocket(liveUrl, {
    enabled: Boolean(liveUrl),
    onMessage: handleLiveMessage,
  })

  const totalScreened = statsQuery.data?.total || topCandidates.length
  const avgScore = statsQuery.data?.avg_score || 0
  const semanticAvg = statsQuery.data?.avg_semantic_score || 0
  const confidenceAvg = statsQuery.data?.avg_confidence_score || 0
  const completed = statsQuery.data?.completed || topCandidates.filter((candidate) => candidate.status === 'explained').length

  if (jobsQuery.isLoading) {
    return (
      <div className="page-content" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
        <div style={{ textAlign: 'center' }}>
          <div className="spinner spinner-lg" style={{ margin: '0 auto 16px' }} />
          <p>Loading dashboard...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="page-content">
      <motion.div
        variants={fadeUp}
        initial="hidden"
        animate="show"
        style={{ marginBottom: 28, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 24, flexWrap: 'wrap' }}
      >
        <div>
          <h1 style={{ marginBottom: 8 }}>
            Recruiter <span className="gradient-text">Command Center</span>
          </h1>
          <p className="text-sm text-muted">
            Semantic screening, explainability, fairness, and live status updates for every hiring motion.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <Link to="/jobs/new" className="btn btn-secondary btn-sm">
            <RiAddLine /> New Job
          </Link>
          <Link to="/resumes/upload" className="btn btn-primary btn-sm">
            <RiFileListLine /> Upload Resumes
          </Link>
        </div>
      </motion.div>

      <div className="grid-4 mb-lg">
        <StatCard icon={RiBriefcaseLine} label="Active Jobs" value={jobsQuery.data?.items?.length || 0} iconBg="linear-gradient(135deg,#7c3aed,#4f46e5)" delay={0} />
        <StatCard icon={RiUserLine} label="Candidates Screened" value={totalScreened} iconBg="linear-gradient(135deg,#06b6d4,#0891b2)" delay={1} />
        <StatCard icon={RiFlashlightLine} label="Average Match" value={`${Math.round(avgScore)}%`} iconBg="linear-gradient(135deg,#f59e0b,#d97706)" delay={2} />
        <StatCard icon={RiCheckboxCircleLine} label="Completed Analyses" value={completed} iconBg="linear-gradient(135deg,#10b981,#059669)" delay={3} />
      </div>

      <div className="dashboard-panels">
        <div className="card" style={{ padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
            <h3 style={{ fontSize: 15 }}>Jobs</h3>
            <span className="badge badge-purple">{jobsQuery.data?.items?.length || 0}</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {jobsQuery.data?.items?.length === 0 ? (
              <EmptyState
                title="No jobs yet"
                description="Create a job to start ranking resumes and generating semantic insights."
                action={<Link to="/jobs/new" className="btn btn-primary btn-sm">Create Job</Link>}
              />
            ) : jobsQuery.data?.items?.map((job) => (
              <button
                key={job.id}
                onClick={() => setSelectedJobId(job.id)}
                style={{
                  textAlign: 'left',
                  border: selectedJob?.id === job.id ? '1px solid rgba(124,58,237,0.3)' : '1px solid transparent',
                  background: selectedJob?.id === job.id ? 'rgba(124,58,237,0.12)' : 'transparent',
                  borderRadius: 14,
                  padding: '12px 14px',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 14 }}>{job.title}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{job.company}</div>
                  </div>
                  <RiArrowRightLine style={{ color: 'var(--text-muted)' }} />
                </div>
              </button>
            ))}
          </div>
        </div>

        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '18px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
            <div>
              <h3 style={{ fontSize: 16, marginBottom: 4 }}>
                {selectedJob ? `Leaderboard • ${selectedJob.title}` : 'Leaderboard'}
              </h3>
              <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                Ranked by hybrid semantic, structured, and confidence scores.
              </p>
            </div>
            <span style={{
              padding: '6px 12px',
              borderRadius: 999,
              background: liveStream.connected ? 'rgba(16,185,129,0.15)' : 'rgba(245,158,11,0.15)',
              color: liveStream.connected ? '#10b981' : '#f59e0b',
              fontSize: 12,
              fontWeight: 700,
            }}>
              {liveStream.connected ? 'Live' : 'Connecting'}
            </span>
          </div>

          {resultsQuery.isLoading ? (
            <div style={{ padding: 40, textAlign: 'center' }}>
              <div className="spinner" style={{ margin: '0 auto 12px' }} />
              Loading screening results...
            </div>
          ) : topCandidates.length === 0 ? (
            <EmptyState
              title="No screening results"
              description="Upload resumes for this job and kick off a screening run to populate the leaderboard."
              action={<Link to="/resumes/upload" className="btn btn-primary btn-sm">Upload Resumes</Link>}
            />
          ) : (
            <div className="table-container" style={{ border: 'none', borderRadius: 0 }}>
              <table>
                <thead>
                  <tr>
                    <th>Rank</th>
                    <th>Candidate</th>
                    <th>Score</th>
                    <th>Semantic</th>
                    <th>Confidence</th>
                    <th>Recommendation</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {topCandidates.map((candidate, index) => {
                    const recommendation = RECOMMENDATION_CONFIG[candidate.ai?.recommendation] || RECOMMENDATION_CONFIG.maybe
                    return (
                      <motion.tr key={candidate.id} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: index * 0.04 }}>
                        <td>
                          <span style={{
                            width: 30,
                            height: 30,
                            borderRadius: '50%',
                            display: 'inline-grid',
                            placeItems: 'center',
                            background: index === 0 ? 'var(--grad-brand)' : 'var(--bg-surface2)',
                            color: index === 0 ? '#fff' : 'var(--text-muted)',
                            fontWeight: 800,
                          }}>
                            {index + 1}
                          </span>
                        </td>
                        <td>
                          <div style={{ fontWeight: 700 }}>{candidate.candidate_name || 'Unknown Candidate'}</div>
                          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{candidate.candidate_email || 'No email'}</div>
                        </td>
                        <td>
                          <span style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-primary)' }}>
                            {Math.round(candidate.score?.overall_score || 0)}
                          </span>
                          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>/100</span>
                        </td>
                        <td>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <div className="progress-bar" style={{ width: 86 }}>
                              <div className="progress-fill" style={{ width: `${candidate.score?.semantic_score || 0}%` }} />
                            </div>
                            <span style={{ fontSize: 12 }}>{Math.round(candidate.score?.semantic_score || 0)}%</span>
                          </div>
                        </td>
                        <td>
                          <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)' }}>
                            {Math.round((candidate.score?.confidence_score || 0) * 100)}%
                          </span>
                        </td>
                        <td>
                          <span style={{
                            padding: '4px 10px',
                            borderRadius: 999,
                            background: recommendation.bg,
                            color: recommendation.color,
                            fontSize: 12,
                            fontWeight: 700,
                          }}>
                            {recommendation.label}
                          </span>
                        </td>
                        <td>
                          <Link to={`/candidates/${candidate.id}`} className="btn btn-ghost btn-sm" style={{ padding: '5px 8px' }}>
                            <RiArrowRightLine />
                          </Link>
                        </td>
                      </motion.tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div style={{ display: 'grid', gap: 20 }}>
          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
              <RiRobot2Line style={{ color: 'var(--brand-primary)' }} />
              <h3 style={{ fontSize: 15 }}>Insights</h3>
            </div>
            <div style={{ display: 'grid', gap: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>Semantic Avg</span>
                <strong>{Math.round(semanticAvg)}%</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>Confidence Avg</span>
                <strong>{Math.round(confidenceAvg * 100)}%</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>Live Feed</span>
                <strong>{liveEvents.length} events</strong>
              </div>
            </div>
          </div>

          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
              <RiTimeLine style={{ color: 'var(--warning)' }} />
              <h3 style={{ fontSize: 15 }}>Live Events</h3>
            </div>
            <div style={{ display: 'grid', gap: 10, maxHeight: 280, overflow: 'auto' }}>
              {liveEvents.length > 0 ? liveEvents.map((event, idx) => <FeedItem key={idx} event={event} />) : (
                <div style={{ color: 'var(--text-muted)', fontSize: 13, lineHeight: 1.6 }}>
                  Screening updates and notification events will appear here in real time once a job is being processed.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

        <div className="dashboard-secondary-grid">
        <div className="card">
          <h3 style={{ marginBottom: 20, fontSize: 15 }}>Top Candidate Score Breakdown</h3>
          {topCandidate ? (
            <div style={{ display: 'flex', justifyContent: 'space-around', flexWrap: 'wrap', gap: 24 }}>
              <div style={{ width: '100%', minWidth: 280, height: 300 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart data={radarData}>
                    <PolarGrid stroke="rgba(255,255,255,0.08)" />
                    <PolarAngleAxis dataKey="subject" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                    <Radar dataKey="A" stroke="#7c3aed" fill="rgba(124,58,237,0.28)" fillOpacity={0.7} />
                    <Tooltip />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            </div>
          ) : (
            <EmptyState
              title="No candidate selected"
              description="Once a leaderboard exists, the strongest candidate appears here with semantic and structured score detail."
              action={null}
            />
          )}
        </div>

        <div className="card">
          <h3 style={{ marginBottom: 20, fontSize: 15 }}>Top 8 Ranking</h3>
          {barData.length > 0 ? (
            <div style={{ width: '100%', height: 320 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={barData} layout="vertical" margin={{ left: 24, right: 12 }}>
                  <XAxis type="number" tick={{ fill: 'var(--text-muted)' }} />
                  <YAxis dataKey="name" type="category" width={120} tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                  <Tooltip />
                  <Bar dataKey="score" radius={[0, 12, 12, 0]}>
                    {barData.map((entry, index) => (
                      <Cell key={entry.name} fill={index === 0 ? '#10b981' : '#7c3aed'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyState
              title="No rank data"
              description="Run a screening cycle to populate the ranking view."
              action={<Link to="/resumes/upload" className="btn btn-primary btn-sm">Run Screening</Link>}
            />
          )}
        </div>
      </div>
    </div>
  )
}
