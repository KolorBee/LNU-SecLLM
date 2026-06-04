import { motion } from 'framer-motion'

const TECH = ['ROS', 'YOLOv8', 'SLAM', 'LoRa', 'LiDAR', 'FastAPI', 'React', 'Three.js']

export default function Footer() {
  return (
    <motion.footer
      initial={{ opacity: 0 }}
      whileInView={{ opacity: 1 }}
      viewport={{ once: true }}
      style={footerStyle}
    >
      {/* Top row */}
      <div style={topRowStyle}>
        {/* Left */}
        <div>
          <div style={logoStyle}>
            煤矿智能<span style={{ color: '#f4a233' }}>监测</span>
          </div>
          <p style={taglineStyle}>
            基于多模态深度学习的矿山危险源智能监测与预警平台
          </p>
        </div>

        {/* Right — tech tags */}
        <div style={tagsWrapStyle}>
          <div style={tagsLabelStyle}>技术栈</div>
          <div style={tagsStyle}>
            {TECH.map((t) => (
              <span key={t} style={tagStyle}>{t}</span>
            ))}
          </div>
        </div>
      </div>

      {/* Divider */}
      <div style={dividerStyle} />

      {/* Bottom row */}
      <div style={bottomRowStyle}>
        <span style={bottomTextStyle}>
          核心技术支持：YOLOv8 高精度视觉模型 · Project 3 最终演示版 · 2026 保留所有权利
        </span>
      </div>
    </motion.footer>
  )
}

const footerStyle = {
  borderTop: '1px solid rgba(255,255,255,0.07)',
  padding: '60px 48px 40px',
  maxWidth: '1200px',
  margin: '0 auto',
}
const topRowStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'flex-start',
  marginBottom: '48px',
  flexWrap: 'wrap',
  gap: '32px',
}
const logoStyle = {
  fontFamily: 'Syne, sans-serif',
  fontWeight: 800,
  fontSize: '22px',
  color: '#e8eaf0',
  letterSpacing: '-0.5px',
  marginBottom: '12px',
}
const taglineStyle = {
  fontFamily: 'DM Mono, monospace',
  fontSize: '11px',
  color: '#5a5f72',
  lineHeight: 1.7,
  letterSpacing: '0.3px',
}
const tagsWrapStyle = {
  textAlign: 'right',
}
const tagsLabelStyle = {
  fontFamily: 'DM Mono, monospace',
  fontSize: '10px',
  color: '#5a5f72',
  textTransform: 'uppercase',
  letterSpacing: '2px',
  marginBottom: '12px',
}
const tagsStyle = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: '8px',
  justifyContent: 'flex-end',
  maxWidth: '360px',
}
const tagStyle = {
  fontFamily: 'DM Mono, monospace',
  fontSize: '10px',
  background: 'rgba(255,255,255,0.04)',
  border: '1px solid rgba(255,255,255,0.07)',
  color: '#5a5f72',
  padding: '5px 12px',
  borderRadius: '100px',
  letterSpacing: '0.5px',
}
const dividerStyle = {
  height: '1px',
  background: 'rgba(255,255,255,0.07)',
  marginBottom: '32px',
}
const bottomRowStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  flexWrap: 'wrap',
  gap: '12px',
}
const bottomTextStyle = {
  fontFamily: 'DM Mono, monospace',
  fontSize: '10px',
  color: '#5a5f72',
  letterSpacing: '0.5px',
}