/**
 * Skill badge with color variants: matched, missing, bonus.
 */
export default function SkillBadge({ skill, variant = 'default', icon }) {
  const styles = {
    matched: { bg: 'rgba(16,185,129,0.12)', color: '#6ee7b7', border: 'rgba(16,185,129,0.3)' },
    missing: { bg: 'rgba(239,68,68,0.12)',  color: '#fca5a5', border: 'rgba(239,68,68,0.3)'  },
    bonus:   { bg: 'rgba(6,182,212,0.12)',  color: '#67e8f9', border: 'rgba(6,182,212,0.3)'  },
    default: { bg: 'rgba(124,58,237,0.12)', color: '#a78bfa', border: 'rgba(124,58,237,0.3)' },
  }
  const s = styles[variant] || styles.default
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '3px 10px', borderRadius: '999px',
      fontSize: 12, fontWeight: 600,
      background: s.bg, color: s.color,
      border: `1px solid ${s.border}`,
      whiteSpace: 'nowrap',
    }}>
      {icon && <span style={{ fontSize: 10 }}>{icon}</span>}
      {skill}
    </span>
  )
}
