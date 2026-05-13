import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import toast from 'react-hot-toast'
import { RiBriefcaseLine, RiAddCircleLine, RiCloseLine, RiLeafLine } from 'react-icons/ri'
import { jobsApi } from '../services/api.js'

const SKILL_SUGGESTIONS = [
  'Python', 'JavaScript', 'React', 'Node.js', 'SQL', 'Docker',
  'Kubernetes', 'Machine Learning', 'PyTorch', 'TensorFlow',
  'AWS', 'Java', 'TypeScript', 'Go', 'Apache Spark', 'FastAPI',
]

export default function JobCreate() {
  const navigate = useNavigate()
  const [submitting, setSubmitting] = useState(false)
  const [requiredSkillInput, setRequiredSkillInput] = useState('')
  const [preferredSkillInput, setPreferredSkillInput] = useState('')

  const [form, setForm] = useState({
    title: '', company: '', location: '', job_type: 'full-time',
    description: '', requirements: '',
    required_skills: [], preferred_skills: [],
    experience_years_min: 0, experience_years_max: 10,
    education_level: '', salary_min: '', salary_max: '',
    diversity_goal: false,
  })

  const set = (field) => (e) => setForm(f => ({ ...f, [field]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))

  const addSkill = (type, value) => {
    const key = type === 'required' ? 'required_skills' : 'preferred_skills'
    const skill = value.trim()
    if (!skill || form[key].includes(skill)) return
    setForm(f => ({ ...f, [key]: [...f[key], skill] }))
    if (type === 'required') setRequiredSkillInput('')
    else setPreferredSkillInput('')
  }

  const removeSkill = (type, skill) => {
    const key = type === 'required' ? 'required_skills' : 'preferred_skills'
    setForm(f => ({ ...f, [key]: f[key].filter(s => s !== skill) }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.title || !form.company || !form.description || !form.requirements) {
      toast.error('Please fill in all required fields')
      return
    }
    if (form.required_skills.length === 0) {
      toast.error('Add at least one required skill')
      return
    }
    setSubmitting(true)
    try {
      const payload = {
        ...form,
        experience_years_min: Number(form.experience_years_min),
        experience_years_max: Number(form.experience_years_max),
        salary_min: form.salary_min ? Number(form.salary_min) : null,
        salary_max: form.salary_max ? Number(form.salary_max) : null,
      }
      await jobsApi.create(payload)
      toast.success('Job posted successfully!')
      navigate('/dashboard')
    } catch (err) {
      console.error(err)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="page-content" style={{ maxWidth: 820 }}>
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}>
        {/* Header */}
        <div style={{ marginBottom: 28 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
            <div style={{ width: 36, height: 36, background: 'var(--grad-brand)', borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <RiBriefcaseLine style={{ color: '#fff', fontSize: 18 }} />
            </div>
            <h1>Post a <span className="gradient-text">New Job</span></h1>
          </div>
          <p className="text-sm text-muted">Define the role requirements — HireSense AI will use these to score candidates.</p>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {/* Basic Info */}
          <div className="card">
            <h3 style={{ marginBottom: 20, fontSize: 15 }}>Basic Information</h3>
            <div className="grid-2" style={{ gap: 16 }}>
              <div className="form-group">
                <label className="form-label">Job Title *</label>
                <input className="form-input" value={form.title} onChange={set('title')} placeholder="e.g. Senior Data Engineer" required />
              </div>
              <div className="form-group">
                <label className="form-label">Company *</label>
                <input className="form-input" value={form.company} onChange={set('company')} placeholder="e.g. TechCorp Inc." required />
              </div>
              <div className="form-group">
                <label className="form-label">Location</label>
                <input className="form-input" value={form.location} onChange={set('location')} placeholder="Remote / Bangalore, India" />
              </div>
              <div className="form-group">
                <label className="form-label">Job Type</label>
                <select className="form-select" value={form.job_type} onChange={set('job_type')}>
                  {['full-time','part-time','contract','internship','freelance'].map(t =>
                    <option key={t} value={t}>{t.replace('-',' ').replace(/\b\w/g,c=>c.toUpperCase())}</option>
                  )}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Min Experience (years)</label>
                <input type="number" className="form-input" value={form.experience_years_min} onChange={set('experience_years_min')} min={0} max={30} />
              </div>
              <div className="form-group">
                <label className="form-label">Education Level</label>
                <select className="form-select" value={form.education_level} onChange={set('education_level')}>
                  <option value="">Any</option>
                  {["High School","Associate/Diploma","Bachelor's","Master's","PhD"].map(e =>
                    <option key={e} value={e}>{e}</option>
                  )}
                </select>
              </div>
            </div>
          </div>

          {/* Description */}
          <div className="card">
            <h3 style={{ marginBottom: 20, fontSize: 15 }}>Job Description & Requirements</h3>
            <div className="form-group" style={{ marginBottom: 16 }}>
              <label className="form-label">Job Description *</label>
              <textarea className="form-textarea" rows={5} value={form.description} onChange={set('description')}
                placeholder="Describe the role, team, and responsibilities..." required style={{ minHeight: 120 }} />
            </div>
            <div className="form-group">
              <label className="form-label">Requirements *</label>
              <textarea className="form-textarea" rows={4} value={form.requirements} onChange={set('requirements')}
                placeholder="List specific requirements, qualifications, certifications..." required style={{ minHeight: 100 }} />
            </div>
          </div>

          {/* Skills */}
          <div className="card">
            <h3 style={{ marginBottom: 20, fontSize: 15 }}>Skills Configuration</h3>

            {/* Required Skills */}
            <div className="form-group" style={{ marginBottom: 20 }}>
              <label className="form-label">Required Skills *</label>
              <div style={{ display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
                <input className="form-input" value={requiredSkillInput}
                  onChange={e => setRequiredSkillInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addSkill('required', requiredSkillInput))}
                  placeholder="Type a skill and press Enter"
                  style={{ flex: '1 1 240px', minWidth: 0 }} />
                <button type="button" className="btn btn-primary btn-sm" onClick={() => addSkill('required', requiredSkillInput)}>
                  <RiAddCircleLine />
                </button>
              </div>
              {/* Suggestions */}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
                {SKILL_SUGGESTIONS.filter(s => !form.required_skills.includes(s)).slice(0, 8).map(s => (
                  <button key={s} type="button" onClick={() => addSkill('required', s)}
                    style={{ padding: '2px 10px', borderRadius: '999px', fontSize: 12, background: 'var(--bg-surface2)', border: '1px solid var(--border)', color: 'var(--text-secondary)', cursor: 'pointer' }}>
                    + {s}
                  </button>
                ))}
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {form.required_skills.map(skill => (
                  <span key={skill} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 10px', borderRadius: '999px', fontSize: 12, fontWeight: 600, background: 'rgba(16,185,129,0.12)', color: '#6ee7b7', border: '1px solid rgba(16,185,129,0.3)' }}>
                    {skill}
                    <RiCloseLine style={{ cursor: 'pointer' }} onClick={() => removeSkill('required', skill)} />
                  </span>
                ))}
              </div>
            </div>

            {/* Preferred Skills */}
            <div className="form-group">
              <label className="form-label">Preferred Skills</label>
              <div style={{ display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
                <input className="form-input" value={preferredSkillInput}
                  onChange={e => setPreferredSkillInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addSkill('preferred', preferredSkillInput))}
                  placeholder="Nice-to-have skills"
                  style={{ flex: '1 1 240px', minWidth: 0 }} />
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => addSkill('preferred', preferredSkillInput)}>
                  <RiAddCircleLine />
                </button>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {form.preferred_skills.map(skill => (
                  <span key={skill} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 10px', borderRadius: '999px', fontSize: 12, fontWeight: 600, background: 'rgba(6,182,212,0.12)', color: '#67e8f9', border: '1px solid rgba(6,182,212,0.3)' }}>
                    {skill}
                    <RiCloseLine style={{ cursor: 'pointer' }} onClick={() => removeSkill('preferred', skill)} />
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* SDG 8 */}
          <div className="card" style={{ background: 'rgba(16,185,129,0.04)', border: '1px solid rgba(16,185,129,0.2)' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
              <RiLeafLine style={{ fontSize: 24, color: '#10b981', flexShrink: 0, marginTop: 2 }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 700, color: '#6ee7b7', marginBottom: 4 }}>SDG 8 — Diversity Goal</div>
                <p className="text-sm text-muted" style={{ marginBottom: 12 }}>
                  Enable this to flag the role as a diversity-priority hire. HireSense AI will add fairness annotations
                  and ensure bias-free candidate evaluation.
                </p>
                <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}>
                  <input type="checkbox" checked={form.diversity_goal} onChange={set('diversity_goal')}
                    style={{ width: 18, height: 18, accentColor: 'var(--brand-primary)', cursor: 'pointer' }} />
                  <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
                    This is a diversity-priority role
                  </span>
                </label>
              </div>
            </div>
          </div>

          {/* Submit */}
          <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
            <button type="button" className="btn btn-secondary" onClick={() => navigate('/dashboard')}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? <><div className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} /> Posting...</> : <><RiBriefcaseLine /> Post Job</>}
            </button>
          </div>
        </form>
      </motion.div>
    </div>
  )
}
