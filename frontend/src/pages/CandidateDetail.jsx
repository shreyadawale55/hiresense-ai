import { useEffect, useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  RiArrowLeftLine,
  RiUserLine,
  RiCheckboxCircleLine,
  RiCloseCircleLine,
  RiStarLine,
  RiAlertLine,
  RiLeafLine,
  RiLightbulbLine,
  RiQuestionLine,
  RiBriefcaseLine,
  RiGitBranchLine,
  RiShieldStarLine,
  RiBrainLine,
  RiSparklingLine,
} from 'react-icons/ri'
import {
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
} from 'recharts'
import ScoreGauge from '../components/ScoreGauge.jsx'
import SkillBadge from '../components/SkillBadge.jsx'
import { notificationsApi, screeningApi } from '../services/api.js'
import { useAuth } from '../context/AuthContext.jsx'
import { useWebSocket } from '../hooks/useWebSocket.js'

const RECOMMENDATION_CONFIG = {
  strong_yes: { label: '⭐ Strong Yes', color: '#10b981', bg: 'rgba(16,185,129,0.15)', border: 'rgba(16,185,129,0.3)' },
  yes: { label: '✓ Yes', color: '#06b6d4', bg: 'rgba(6,182,212,0.15)', border: 'rgba(6,182,212,0.3)' },
  maybe: { label: '◑ Maybe', color: '#f59e0b', bg: 'rgba(245,158,11,0.15)', border: 'rgba(245,158,11,0.3)' },
  no: { label: '✗ No', color: '#ef4444', bg: 'rgba(239,68,68,0.15)', border: 'rgba(239,68,68,0.3)' },
}

const PIE_COLORS = ['#10b981', '#06b6d4', '#f59e0b', '#ef4444']

function Section({ icon: Icon, title, color, children }) {
  return (
    <motion.div className="card" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
        <div style={{ width: 32, height: 32, borderRadius: 8, background: `${color}20`, display: 'grid', placeItems: 'center' }}>
          <Icon style={{ color, fontSize: 16 }} />
        </div>
        <h3 style={{ fontSize: 15 }}>{title}</h3>
      </div>
      {children}
    </motion.div>
  )
}

function ScoreMeter({ label, value }) {
  const color = value >= 80 ? '#10b981' : value >= 65 ? '#06b6d4' : value >= 45 ? '#f59e0b' : '#ef4444'
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{label}</span>
        <span style={{ fontSize: 13, fontWeight: 700, color }}>{Math.round(value || 0)}%</span>
      </div>
      <div className="progress-bar">
        <motion.div
          className="progress-fill"
          initial={{ width: 0 }}
          animate={{ width: `${value || 0}%` }}
          transition={{ duration: 0.9, ease: 'easeOut', delay: 0.3 }}
          style={{ background: `linear-gradient(90deg, ${color}88, ${color})` }}
        />
      </div>
    </div>
  )
}

export default function CandidateDetail() {
  const { screeningId } = useParams()
  const queryClient = useQueryClient()
  const { accessToken } = useAuth()

  const screeningQuery = useQuery({
    queryKey: ['screening', screeningId],
    queryFn: async () => (await screeningApi.getSingle(screeningId)).data,
  })

  const similarityQuery = useQuery({
    queryKey: ['candidate-similarity', screeningQuery.data?.resume_id],
    queryFn: async () => (await screeningApi.similarity(screeningQuery.data.resume_id, 6)).data,
    enabled: Boolean(screeningQuery.data?.resume_id),
  })

  const liveUrl = screeningQuery.data?.job_id && accessToken
    ? notificationsApi.screeningUrl(screeningQuery.data.job_id, accessToken)
    : null

  const liveStream = useWebSocket(liveUrl, {
    enabled: Boolean(liveUrl),
    onMessage: (payload) => {
      if (payload?.type?.startsWith('screening.')) {
        queryClient.invalidateQueries({ queryKey: ['screening', screeningId] })
      }
    },
  })

  useEffect(() => {
    if (screeningQuery.data?.status && screeningQuery.data.status !== 'explained' && screeningQuery.data.status !== 'failed') {
      const timer = setInterval(() => queryClient.invalidateQueries({ queryKey: ['screening', screeningId] }), 4000)
      return () => clearInterval(timer)
    }
    return undefined
  }, [screeningQuery.data, queryClient, screeningId])

  const data = screeningQuery.data
  const score = data?.score || {}
  const ai = data?.ai || {}
  const stillProcessing = data?.status && data.status !== 'explained' && data.status !== 'failed'

  const radarData = useMemo(() => ([
    { subject: 'Overall', A: score.overall_score || 0 },
    { subject: 'Semantic', A: score.semantic_score || 0 },
    { subject: 'Skills', A: score.skill_match_score || 0 },
    { subject: 'Experience', A: score.experience_score || 0 },
    { subject: 'Education', A: score.education_score || 0 },
  ]), [score])

  const recommendation = RECOMMENDATION_CONFIG[ai.recommendation] || RECOMMENDATION_CONFIG.maybe
  const retrievedContext = data?.explanation_context?.retrieved_context || data?.retrieved_context || []
  const pieData = [
    { name: 'Matched', value: score.matched_skills?.length || 0 },
    { name: 'Missing', value: score.missing_skills?.length || 0 },
    { name: 'Bonus', value: score.bonus_skills?.length || 0 },
  ]

  if (screeningQuery.isLoading) {
    return (
      <div className="page-content" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
        <div style={{ textAlign: 'center' }}>
          <div className="spinner spinner-lg" style={{ margin: '0 auto 16px' }} />
          <p>Loading candidate analysis...</p>
        </div>
      </div>
    )
  }

  if (!data) return <div className="page-content"><p>Screening not found.</p></div>

  return (
    <div className="page-content" style={{ maxWidth: 1180 }}>
      <Link to="/dashboard" className="btn btn-ghost btn-sm" style={{ marginBottom: 24, display: 'inline-flex' }}>
        <RiArrowLeftLine /> Back to Dashboard
      </Link>

      <motion.div className="card glow-border" style={{ marginBottom: 24 }} initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 20, flexWrap: 'wrap' }}>
          <div style={{
            width: 68,
            height: 68,
            borderRadius: '50%',
            background: 'var(--grad-brand)',
            display: 'grid',
            placeItems: 'center',
            fontSize: 26,
            fontWeight: 800,
            color: '#fff',
            boxShadow: 'var(--shadow-glow)',
          }}>
            {(data.candidate_name || 'U').charAt(0).toUpperCase()}
          </div>

          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <h2 style={{ marginBottom: 0 }}>{data.candidate_name || 'Unknown Candidate'}</h2>
              <span style={{
                padding: '6px 12px',
                borderRadius: 999,
                background: recommendation.bg,
                border: `1px solid ${recommendation.border}`,
                color: recommendation.color,
                fontSize: 12,
                fontWeight: 700,
              }}>
                {recommendation.label}
              </span>
            </div>
            <p className="text-sm text-muted">{data.candidate_email || 'No email on file'}</p>
            <p className="text-sm text-muted">{data.candidate_location || 'Location unavailable'}</p>
            {stillProcessing && (
              <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--warning)' }}>
                <div className="spinner" style={{ width: 14, height: 14, borderWidth: 2, borderTopColor: 'var(--warning)' }} />
                AI analysis in progress - auto refreshing...
              </div>
            )}
          </div>

          <div style={{ display: 'grid', gap: 10, minWidth: 220 }}>
            <div className="card card-sm" style={{ padding: 16 }}>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Job ID</div>
              <div style={{ fontWeight: 700 }}>{data.job_id}</div>
            </div>
            <div className="card card-sm" style={{ padding: 16 }}>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Live stream</div>
              <div style={{ fontWeight: 700, color: liveStream.connected ? '#10b981' : '#f59e0b' }}>
                {liveStream.connected ? 'Connected' : 'Connecting'}
              </div>
            </div>
          </div>
        </div>
      </motion.div>

      <div className="card" style={{ marginBottom: 24 }}>
        <h3 style={{ marginBottom: 24, fontSize: 15 }}>Score Breakdown</h3>
        <div className="candidate-score-grid">
          <ScoreGauge score={score.overall_score || 0} size={130} label="Overall Match" />
          <ScoreGauge score={score.semantic_score || 0} size={110} label="Semantic" />
          <ScoreGauge score={score.skill_match_score || 0} size={110} label="Skills" />
          <ScoreGauge score={score.experience_score || 0} size={110} label="Experience" />
          <ScoreGauge score={score.education_score || 0} size={110} label="Education" />
        </div>
        <div className="candidate-info-grid">
          <div>
            <ScoreMeter label="Skill Match" value={score.skill_match_score} />
            <ScoreMeter label="Semantic Match" value={score.semantic_score} />
            <ScoreMeter label="Experience" value={score.experience_score} />
            <ScoreMeter label="Education" value={score.education_score} />
          </div>
          <div style={{ width: '100%', height: 280 }}>
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
      </div>

      <div className="candidate-aux-grid" style={{ marginBottom: 20 }}>
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '18px 20px', borderBottom: '1px solid var(--border)' }}>
            <h3 style={{ fontSize: 15 }}>Skills Analysis</h3>
          </div>
          <div style={{ padding: 20 }}>
            {score.matched_skills?.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: '#10b981', letterSpacing: '0.08em', marginBottom: 8 }}>
                  ✓ MATCHED SKILLS ({score.matched_skills.length})
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {score.matched_skills.map((skill) => <SkillBadge key={skill} skill={skill} variant="matched" />)}
                </div>
              </div>
            )}
            {score.missing_skills?.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: '#ef4444', letterSpacing: '0.08em', marginBottom: 8 }}>
                  ✗ MISSING SKILLS ({score.missing_skills.length})
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {score.missing_skills.map((skill) => <SkillBadge key={skill} skill={skill} variant="missing" />)}
                </div>
              </div>
            )}
            {score.bonus_skills?.length > 0 && (
              <div>
                <div style={{ fontSize: 12, fontWeight: 700, color: '#06b6d4', letterSpacing: '0.08em', marginBottom: 8 }}>
                  ⭐ BONUS SKILLS ({score.bonus_skills.length})
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {score.bonus_skills.map((skill) => <SkillBadge key={skill} skill={skill} variant="bonus" />)}
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
            <RiGitBranchLine style={{ color: 'var(--brand-primary)' }} />
            <h3 style={{ fontSize: 15 }}>Evidence Mix</h3>
          </div>
          <div style={{ width: '100%', height: 240 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={60} outerRadius={92} paddingAngle={5}>
                  {pieData.map((entry, index) => (
                    <Cell key={entry.name} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="candidate-context-grid" style={{ marginTop: 10 }}>
            {pieData.map((item) => (
              <div key={item.name} className="card card-sm" style={{ padding: 12, textAlign: 'center' }}>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{item.name}</div>
                <div style={{ fontSize: 20, fontWeight: 800 }}>{item.value}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {ai.explanation && (
        <Section icon={RiLightbulbLine} title="AI Analysis" color="#a78bfa">
          <div style={{
            background: 'rgba(124,58,237,0.06)',
            borderRadius: 14,
            padding: 18,
            fontSize: 14,
            lineHeight: 1.8,
            color: 'var(--text-secondary)',
            whiteSpace: 'pre-line',
            border: '1px solid rgba(124,58,237,0.15)',
          }}>
            {ai.explanation}
          </div>
        </Section>
      )}

      <div className="grid-2" style={{ marginTop: 20 }}>
        {ai.strengths?.length > 0 && (
          <Section icon={RiStarLine} title="Strengths" color="#10b981">
            <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8 }}>
              {ai.strengths.map((strength, index) => (
                <li key={index} style={{ display: 'flex', gap: 8, fontSize: 13, color: 'var(--text-secondary)' }}>
                  <RiCheckboxCircleLine style={{ color: '#10b981', flexShrink: 0, marginTop: 2 }} />
                  {strength}
                </li>
              ))}
            </ul>
          </Section>
        )}
        {ai.concerns?.length > 0 && (
          <Section icon={RiAlertLine} title="Areas of Concern" color="#f59e0b">
            <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8 }}>
              {ai.concerns.map((concern, index) => (
                <li key={index} style={{ display: 'flex', gap: 8, fontSize: 13, color: 'var(--text-secondary)' }}>
                  <RiAlertLine style={{ color: '#f59e0b', flexShrink: 0, marginTop: 2 }} />
                  {concern}
                </li>
              ))}
            </ul>
          </Section>
        )}
      </div>

      <div className="grid-2" style={{ marginTop: 20 }}>
        <Section icon={RiQuestionLine} title="Interview Questions" color="#06b6d4">
          <ul style={{ listStyle: 'none', display: 'grid', gap: 10 }}>
            {(ai.interview_questions?.length > 0 ? ai.interview_questions : [
              'Tell me about a project where you used these skills.',
              'How do you approach learning unfamiliar tools?',
              'What tradeoffs did you make in a technical implementation?',
            ]).map((question, index) => (
              <li key={index} style={{ display: 'flex', gap: 8, fontSize: 13, color: 'var(--text-secondary)' }}>
                <RiQuestionLine style={{ color: '#06b6d4', flexShrink: 0, marginTop: 2 }} />
                {question}
              </li>
            ))}
          </ul>
        </Section>
        <Section icon={RiShieldStarLine} title="Fairness Report" color="#10b981">
          <div style={{ display: 'grid', gap: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {ai.bias_detected
                ? <><RiAlertLine style={{ color: '#f59e0b' }} /><span style={{ color: '#f59e0b', fontWeight: 600, fontSize: 13 }}>Bias indicators detected and sanitized</span></>
                : <><RiCheckboxCircleLine style={{ color: '#10b981' }} /><span style={{ color: '#10b981', fontWeight: 600, fontSize: 13 }}>No bias detected</span></>
              }
            </div>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
              Evaluated on skills, experience, education, and achievements only.
            </p>
            {score.fairness_score != null && (
              <div style={{ fontSize: 13, fontWeight: 700 }}>Fairness score: {Math.round(score.fairness_score)}%</div>
            )}
            {(ai.bias_keywords?.length > 0 || ai.fairness_flags?.length > 0) && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {[...(ai.bias_keywords || []), ...(ai.fairness_flags || [])].map((flag) => (
                  <SkillBadge key={flag} skill={flag} variant="bonus" />
                ))}
              </div>
            )}
            {ai.sdg8_note && (
              <div style={{ padding: 14, borderRadius: 14, background: 'rgba(16,185,129,0.05)', border: '1px solid rgba(16,185,129,0.16)' }}>
                {ai.sdg8_note}
              </div>
            )}
          </div>
        </Section>
      </div>

      <div className="grid-2" style={{ marginTop: 20 }}>
        <Section icon={RiBrainLine} title="Retrieved Context" color="#7c3aed">
          <div style={{ display: 'grid', gap: 10 }}>
            {retrievedContext.length > 0 ? retrievedContext.map((item, index) => (
              <div key={index} className="card card-sm" style={{ background: 'rgba(255,255,255,0.02)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 6 }}>
                  <strong style={{ fontSize: 13 }}>{item.candidate_name || item.resume_id}</strong>
                  <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>{item.similarity}%</span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.7 }}>
                  {item.skills?.length ? item.skills.join(', ') : 'No skills captured'}
                </div>
              </div>
            )) : (
              <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>No retrieved context available yet.</div>
            )}
          </div>
        </Section>
        <Section icon={RiSparklingLine} title="Similar Candidates" color="#f59e0b">
          <div style={{ display: 'grid', gap: 10 }}>
            {similarityQuery.data?.length > 0 ? similarityQuery.data.map((candidate) => (
              <div key={candidate.resume_id} className="card card-sm" style={{ background: 'rgba(255,255,255,0.02)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                  <strong style={{ fontSize: 13 }}>{candidate.candidate_name || candidate.resume_id}</strong>
                  <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{candidate.similarity}%</span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>{candidate.reason}</div>
              </div>
            )) : (
              <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>Similar candidate search populates after the resume is indexed.</div>
            )}
          </div>
        </Section>
      </div>
    </div>
  )
}
