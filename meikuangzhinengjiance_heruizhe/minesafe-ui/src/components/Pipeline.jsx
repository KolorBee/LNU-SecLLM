import { motion } from 'framer-motion'

const STEPS = [
  { icon: '📡', name: 'Sensor Fusion',      sub: 'LiDAR + Thermal + Radar' },
  { icon: '🔍', name: 'YOLO Detection',     sub: 'Low-light adaptive' },
  { icon: '🧠', name: 'AI Reasoning',       sub: 'Hazard prediction' },
  { icon: '🗺️', name: 'Path Memory',        sub: 'SLAM navigation' },
  { icon: '🚛', name: 'Autonomous Vehicle', sub: 'ROS-controlled' },
  { icon: '📻', name: 'LoRa Uplink',        sub: 'Long-range telemetry' },
]

export default function Pipeline() {
  return (
    <div style={styles.wrapper}>
      {/* Section label */}
      <motion.div
        initial={{ opacity: 0, x: -20 }}
        whileInView={{ opacity: 1, x: 0 }}
        viewport={{ once: true }}
        style={styles.label}
      >
        <span style={styles.labelLine} /> System Pipeline
      </motion.div>

      {/* Steps row */}
      <div style={styles.pipeline}>
        {STEPS.map((step, i) => (
          <>
            {/* Each step card animates in with a delay based on index */}
            <motion.div
              key={step.name}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1 }}
              whileHover={{ borderColor: '#f4a233', y: -4 }}
              style={styles.step}
            >
              <div style={styles.stepIcon}>{step.icon}</div>
              <div style={styles.stepName}>{step.name}</div>
              <div style={styles.stepSub}>{step.sub}</div>
            </motion.div>

            {/* Arrow between steps, don't show after last */}
            {i < STEPS.length - 1 && (
              <div key={`arrow-${i}`} style={styles.arrow}>→</div>
            )}
          </>
        ))}
      </div>
    </div>
  )
}

const styles = {
  wrapper: {
    maxWidth: '1200px',
    margin: '0 auto',
    padding: '0 48px 80px',
  },
  label: {
    fontFamily: 'DM Mono, monospace',
    fontSize: '10px',
    letterSpacing: '3px',
    textTransform: 'uppercase',
    color: '#f4a233',
    marginBottom: '32px',
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  labelLine: {
    display: 'inline-block',
    width: '24px', height: '1px',
    background: '#f4a233',
  },
  pipeline: {
    display: 'flex',
    alignItems: 'center',
    gap: '0',
    overflowX: 'auto',
    paddingBottom: '8px',
  },
  step: {
    flexShrink: 0,
    background: '#0d0f14',
    border: '1px solid rgba(255,255,255,0.07)',
    borderRadius: '12px',
    padding: '20px',
    minWidth: '155px',
    textAlign: 'center',
    cursor: 'pointer',
    transition: 'border-color 0.3s, transform 0.3s',
  },
  stepIcon: { fontSize: '24px', marginBottom: '10px' },
  stepName: {
    fontFamily: 'Syne, sans-serif',
    fontWeight: 700,
    fontSize: '12px',
    color: '#e8eaf0',
    marginBottom: '4px',
  },
  stepSub: {
    fontFamily: 'DM Mono, monospace',
    fontSize: '10px',
    color: '#5a5f72',
  },
  arrow: {
    flexShrink: 0,
    color: '#5a5f72',
    fontSize: '18px',
    padding: '0 6px',
  },
}