import { useState, useCallback, useEffect } from 'react'
import { useDropzone } from 'react-dropzone'
import { motion, AnimatePresence } from 'framer-motion'
import toast from 'react-hot-toast'
import {
  RiUploadCloud2Line, RiFilePdf2Line, RiFileWord2Line,
  RiCheckboxCircleLine, RiCloseCircleLine, RiTimeLine,
  RiFlashlightLine, RiBriefcaseLine
} from 'react-icons/ri'
import { resumesApi, jobsApi, screeningApi } from '../services/api.js'

const STATUS_ICON = {
  queued:    <RiTimeLine style={{ color: 'var(--warning)' }} />,
  uploading: <div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />,
  done:      <RiCheckboxCircleLine style={{ color: 'var(--success)' }} />,
  error:     <RiCloseCircleLine style={{ color: 'var(--danger)' }} />,
}

export default function ResumeUpload() {
  const [files, setFiles] = useState([])         // { file, status, resumeId, name }
  const [jobs, setJobs] = useState([])
  const [selectedJobId, setSelectedJobId] = useState('')
  const [uploading, setUploading] = useState(false)
  const [screening, setScreening] = useState(false)

  useEffect(() => {
    jobsApi.list({ page_size: 50 }).then(r => setJobs(r.data.items || []))
  }, [])

  const onDrop = useCallback((accepted, rejected) => {
    rejected.forEach(r => toast.error(`${r.file.name}: ${r.errors[0]?.message}`))
    const newFiles = accepted.map(f => ({ file: f, status: 'queued', resumeId: null, name: f.name }))
    setFiles(prev => [...prev, ...newFiles])
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'], 'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'] },
    maxSize: 10 * 1024 * 1024,
    maxFiles: 50,
  })

  const removeFile = (idx) => setFiles(prev => prev.filter((_, i) => i !== idx))

  const uploadAll = async () => {
    const queued = files.filter(f => f.status === 'queued')
    if (!queued.length) { toast.error('No files to upload'); return }
    setUploading(true)

    for (let i = 0; i < files.length; i++) {
      if (files[i].status !== 'queued') continue
      setFiles(prev => prev.map((f, idx) => idx === i ? { ...f, status: 'uploading' } : f))
      try {
        const res = await resumesApi.upload(files[i].file, selectedJobId || null)
        setFiles(prev => prev.map((f, idx) => idx === i ? { ...f, status: 'done', resumeId: res.data.id } : f))
      } catch {
        setFiles(prev => prev.map((f, idx) => idx === i ? { ...f, status: 'error' } : f))
      }
    }
    setUploading(false)
    toast.success('Upload complete!')
  }

  const startScreening = async () => {
    if (!selectedJobId) { toast.error('Select a job first'); return }
    const resumeIds = files.filter(f => f.status === 'done' && f.resumeId).map(f => f.resumeId)
    if (!resumeIds.length) { toast.error('Upload resumes first'); return }
    setScreening(true)
    try {
      await screeningApi.start(selectedJobId, resumeIds)
      toast.success(`AI screening started for ${resumeIds.length} resumes! Check Dashboard for results.`)
    } catch (err) {
      console.error(err)
    } finally {
      setScreening(false)
    }
  }

  const doneCount = files.filter(f => f.status === 'done').length
  const allDone = files.length > 0 && files.every(f => f.status === 'done' || f.status === 'error')

  return (
    <div className="page-content" style={{ maxWidth: 860 }}>
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}>
        {/* Header */}
        <div style={{ marginBottom: 28 }}>
          <h1>Upload <span className="gradient-text">Resumes</span></h1>
          <p className="text-sm text-muted mt-sm">Upload PDF or DOCX resumes — AI processing starts automatically.</p>
        </div>

        {/* Job Selector */}
        <div className="card mb-lg">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
            <RiBriefcaseLine style={{ color: 'var(--brand-primary)', fontSize: 20 }} />
            <h3 style={{ fontSize: 15 }}>Select Job Position</h3>
          </div>
          <select className="form-select" value={selectedJobId} onChange={e => setSelectedJobId(e.target.value)}>
            <option value="">— Select a job to screen against —</option>
            {jobs.map(j => <option key={j.id} value={j.id}>{j.title} · {j.company}</option>)}
          </select>
          {!selectedJobId && (
            <p className="text-xs text-muted" style={{ marginTop: 8 }}>
              You can upload without selecting a job, but AI scoring requires a job.
            </p>
          )}
        </div>

        {/* Dropzone */}
        <div {...getRootProps()} className={`dropzone ${isDragActive ? 'active' : ''}`} style={{ marginBottom: 20 }}>
          <input {...getInputProps()} />
          <motion.div
            animate={{ scale: isDragActive ? 1.05 : 1 }}
            style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 64, height: 64,
              background: isDragActive ? 'var(--grad-brand)' : 'rgba(124,58,237,0.12)',
              borderRadius: '50%',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'all 0.3s',
              boxShadow: isDragActive ? 'var(--shadow-glow)' : 'none',
            }}>
              <RiUploadCloud2Line style={{ fontSize: 28, color: isDragActive ? '#fff' : 'var(--brand-primary)' }} />
            </div>
            <div>
              <p style={{ fontWeight: 700, fontSize: 16, color: 'var(--text-primary)', marginBottom: 4 }}>
                {isDragActive ? 'Drop files here!' : 'Drag & drop resumes here'}
              </p>
              <p className="text-sm text-muted">or click to browse · PDF & DOCX · Max 10MB · Up to 50 files</p>
            </div>
          </motion.div>
        </div>

        {/* File List */}
        <AnimatePresence>
          {files.length > 0 && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
              <div className="card" style={{ padding: 0, overflow: 'hidden', marginBottom: 20 }}>
                <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: 14, fontWeight: 600 }}>{files.length} file{files.length > 1 ? 's' : ''} selected</span>
                  <span className="badge badge-green">{doneCount} uploaded</span>
                </div>
                <div style={{ maxHeight: 280, overflowY: 'auto' }}>
                  {files.map((f, i) => (
                    <motion.div key={i} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.03 }}
                      style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                      {f.name.endsWith('.pdf')
                        ? <RiFilePdf2Line style={{ fontSize: 20, color: '#f43f5e', flexShrink: 0 }} />
                        : <RiFileWord2Line style={{ fontSize: 20, color: '#3b82f6', flexShrink: 0 }} />
                      }
                      <span style={{ flex: 1, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {f.name}
                      </span>
                      <span style={{ fontSize: 11, color: 'var(--text-muted)', flexShrink: 0 }}>
                        {(f.file.size / 1024).toFixed(0)} KB
                      </span>
                      <span style={{ flexShrink: 0 }}>{STATUS_ICON[f.status]}</span>
                      {f.status === 'queued' && (
                        <button onClick={() => removeFile(i)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 2 }}>
                          <RiCloseCircleLine style={{ fontSize: 16 }} />
                        </button>
                      )}
                    </motion.div>
                  ))}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Action Buttons */}
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <button className="btn btn-primary" onClick={uploadAll} disabled={uploading || files.filter(f => f.status === 'queued').length === 0}>
            {uploading
              ? <><div className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} /> Uploading...</>
              : <><RiUploadCloud2Line /> Upload {files.filter(f => f.status === 'queued').length || ''} Files</>
            }
          </button>

          {allDone && doneCount > 0 && selectedJobId && (
            <motion.button initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}
              className="btn btn-secondary" onClick={startScreening} disabled={screening}>
              {screening
                ? <><div className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} /> Starting...</>
                : <><RiFlashlightLine style={{ color: 'var(--brand-primary)' }} /> Start AI Screening</>
              }
            </motion.button>
          )}
        </div>

        {allDone && doneCount > 0 && !selectedJobId && (
          <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-sm text-warning" style={{ marginTop: 12 }}>
            ⚠ Select a job above and click "Start AI Screening" to score these candidates.
          </motion.p>
        )}
      </motion.div>
    </div>
  )
}
