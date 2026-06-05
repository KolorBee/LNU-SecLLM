import { motion } from 'framer-motion'

export default function Hero() {
  return (
    <section style={styles.section}>
      <div style={styles.grid} />
      <div style={styles.glow} />

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        style={styles.eyebrow}
      >
        深度学习 · YOLO 视觉感知 · 动态规则引擎 · 实时预警
      </motion.div>

      <motion.h1
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        style={styles.title}
      >
        洞悉矿区环境的<br />
        智能视觉<br />
        <span style={styles.highlight}>监测大脑</span>
      </motion.h1>

      <motion.p
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.6 }}
        style={styles.sub}
      >
        融合前沿 YOLO 视觉大模型与动态综合风险评估引擎。
        实现对露天及井下矿山落石、结构损伤等高危隐患的毫秒级精准识别，
        全天候保障矿区作业人员与设备安全，赋能矿山智能化转型。
      </motion.p>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.8 }}
        style={styles.ctas}
      >
        <a href="#detect" style={styles.btnPrimary}>⚡ 开始实时检测</a>
      </motion.div>
    </section>
  )
}

const styles = {
  section: {
    minHeight: '100vh',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
    padding: '120px 48px 80px',
    textAlign: 'center',
    overflow: 'hidden',
  },
  grid: {
    position: 'absolute',
    inset: 0,
    backgroundImage: `
      linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px)
    `,
    backgroundSize: '60px 60px',
    WebkitMaskImage: 'radial-gradient(ellipse 80% 60% at 50% 50%, black, transparent)',
    maskImage: 'radial-gradient(ellipse 80% 60% at 50% 50%, black, transparent)',
  },
  glow: {
    position: 'absolute',
    width: '600px', height: '600px',
    background: 'radial-gradient(circle, rgba(244,162,51,0.08) 0%, transparent 70%)',
    top: '50%', left: '50%',
    transform: 'translate(-50%, -50%)',
    pointerEvents: 'none',
  },
  eyebrow: {
    fontFamily: 'DM Mono, monospace',
    fontSize: '11px',
    letterSpacing: '3px',
    textTransform: 'uppercase',
    color: '#f4a233',
    marginBottom: '24px',
    position: 'relative',
  },
  title: {
    fontFamily: 'Syne, sans-serif',
    fontWeight: 800,
    fontSize: 'clamp(40px, 7vw, 88px)',
    lineHeight: 1.0,
    letterSpacing: '-3px',
    color: '#fff',
    maxWidth: '900px',
    marginBottom: '28px',
    position: 'relative',
  },
  highlight: {
    background: 'linear-gradient(135deg, #f4a233, #3be8b0)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    backgroundClip: 'text',
  },
  sub: {
    fontSize: '16px',
    color: '#5a5f72',
    maxWidth: '560px',
    lineHeight: 1.7,
    marginBottom: '48px',
    position: 'relative',
  },
  ctas: {
    display: 'flex',
    gap: '16px',
    justifyContent: 'center',
    marginBottom: '64px',
    position: 'relative',
  },
  btnPrimary: {
    background: '#f4a233',
    color: '#000',
    fontFamily: 'Syne, sans-serif',
    fontWeight: 700,
    fontSize: '13px',
    padding: '14px 28px',
    borderRadius: '8px',
    textDecoration: 'none',
    display: 'inline-flex',
    alignItems: 'center',
    gap: '8px',
  },
}