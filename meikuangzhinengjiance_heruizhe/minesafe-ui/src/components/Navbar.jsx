import { motion } from 'framer-motion'
import { useState } from 'react'

const NAV_ITEMS = [
  { label: '检测 (Detect)', href: '#detect' },
]

export default function Navbar() {
  return (
    <motion.nav
      initial={{ y: -60, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.6 }}
      style={navStyle}
    >
      <div style={logoStyle}>
        <motion.span
          animate={{ scale: [1, 1.5, 1], opacity: [1, 0.4, 1] }}
          transition={{ duration: 2, repeat: Infinity }}
          style={dotStyle}
        />
        煤矿智能<span style={{ color: '#f4a233' }}>监测</span>
      </div>

      <ul style={ulStyle}>
        {NAV_ITEMS.map((item) => (
          <NavLink key={item.label} label={item.label} href={item.href} />
        ))}
      </ul>

    </motion.nav>
  )
}

function NavLink({ label, href }) {
  const [hovered, setHovered] = useState(false)
  const color = hovered ? '#e8eaf0' : '#5a5f72'
  return (
    <li style={{ listStyle: 'none' }}>
      <a
        href={href}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        style={{
          fontFamily: 'DM Mono, monospace',
          fontSize: '11px',
          textTransform: 'uppercase',
          letterSpacing: '1.5px',
          textDecoration: 'none',
          color: color,
          transition: 'color 0.2s',
        }}
      >
        {label}
      </a>
    </li>
  )
}

const navStyle = {
  position: 'fixed',
  top: 0,
  left: 0,
  right: 0,
  zIndex: 100,
  padding: '20px 48px',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  background: 'rgba(5,6,8,0.8)',
  backdropFilter: 'blur(20px)',
  borderBottom: '1px solid rgba(255,255,255,0.07)',
}

const logoStyle = {
  fontFamily: 'Syne, sans-serif',
  fontWeight: 800,
  fontSize: '18px',
  color: '#e8eaf0',
  display: 'flex',
  alignItems: 'center',
  gap: '10px',
}

const dotStyle = {
  display: 'inline-block',
  width: '8px',
  height: '8px',
  background: '#3be8b0',
  borderRadius: '50%',
}

const ulStyle = {
  display: 'flex',
  gap: '32px',
  listStyle: 'none',
  padding: 0,
  margin: 0,
}
