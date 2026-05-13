import { motion } from 'framer-motion'

/**
 * Animated SVG gauge that renders a score 0-100 as an arc.
 */
export default function ScoreGauge({ score = 0, size = 120, label = 'Match Score' }) {
  const radius = (size - 16) / 2
  const circumference = Math.PI * radius   // half-circle arc
  const progress = ((score / 100) * circumference)

  const color =
    score >= 80 ? '#10b981' :
    score >= 65 ? '#06b6d4' :
    score >= 45 ? '#f59e0b' : '#ef4444'

  const grade =
    score >= 80 ? 'Excellent' :
    score >= 65 ? 'Good' :
    score >= 45 ? 'Fair' : 'Low'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
      <div style={{ position: 'relative', width: size, height: size / 2 + 16, overflow: 'hidden' }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ position: 'absolute', top: 0, left: 0 }}>
          {/* Background arc */}
          <path
            d={`M 8 ${size / 2 + 8} A ${radius} ${radius} 0 0 1 ${size - 8} ${size / 2 + 8}`}
            fill="none"
            stroke="rgba(255,255,255,0.06)"
            strokeWidth="8"
            strokeLinecap="round"
          />
          {/* Animated fill arc */}
          <motion.path
            d={`M 8 ${size / 2 + 8} A ${radius} ${radius} 0 0 1 ${size - 8} ${size / 2 + 8}`}
            fill="none"
            stroke={color}
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={circumference}
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset: circumference - progress }}
            transition={{ duration: 1.2, ease: 'easeOut', delay: 0.2 }}
            style={{ filter: `drop-shadow(0 0 6px ${color})` }}
          />
        </svg>
        {/* Center score */}
        <div style={{
          position: 'absolute', bottom: 0, left: 0, right: 0,
          display: 'flex', flexDirection: 'column', alignItems: 'center',
        }}>
          <motion.span
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.8 }}
            style={{ fontSize: size / 4, fontWeight: 800, fontFamily: 'var(--font-display)', color, lineHeight: 1 }}
          >
            {Math.round(score)}
          </motion.span>
          <span style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 600 }}>{grade}</span>
        </div>
      </div>
      <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 600 }}>{label}</span>
    </div>
  )
}
