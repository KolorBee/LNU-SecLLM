import { motion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'

const ROUTES = [
  {
    name: 'Route A — Main Corridor',
    risk: 'SAFE', color: '#3be8b0',
    points: [[40,180],[120,160],[220,140],[320,130],[420,140],[520,130],[580,120]],
    distance: '840m', time: '4.2 min', note: 'Stable',
    desc: 'Primary extraction path. All sensors green. Recommended for heavy vehicles.',
  },
  {
    name: 'Route B — East Tunnel',
    risk: 'CAUTION', color: '#f4a233',
    points: [[40,180],[100,220],[200,240],[300,230],[380,210],[460,220]],
    distance: '590m', time: '3.1 min', note: '⚠ Cracks',
    desc: 'Minor crack at 320m mark. Light vehicles only. Monitor actively.',
  },
  {
    name: 'Route C — Shaft 7',
    risk: 'DANGER', color: '#ff4d4d',
    points: [[40,180],[90,260],[160,300],[220,310],[270,300]],
    distance: '420m', time: '—', note: '🚫 Blocked',
    desc: 'Rockfall detected. Structural instability confirmed. Access BLOCKED.',
  },
]

const RISK_COLORS = {
  SAFE:    { bg: 'rgba(59,232,176,0.1)',  border: 'rgba(59,232,176,0.2)',  text: '#3be8b0' },
  CAUTION: { bg: 'rgba(244,162,51,0.1)', border: 'rgba(244,162,51,0.2)', text: '#f4a233' },
  DANGER:  { bg: 'rgba(255,77,77,0.1)',  border: 'rgba(255,77,77,0.2)',  text: '#ff4d4d' },
}

export default function PathNavigator() {
  const canvasRef  = useRef(null)
  const [active, setActive] = useState(0)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    let animFrame

    function resize() {
      canvas.width  = canvas.offsetWidth
      canvas.height = canvas.offsetHeight
    }
    resize()
    window.addEventListener('resize', resize)

    function draw() {
      const W = canvas.width
      const H = canvas.height
      ctx.clearRect(0, 0, W, H)

      // Background
      ctx.fillStyle = '#0d0f14'
      ctx.fillRect(0, 0, W, H)

      // Grid
      ctx.strokeStyle = 'rgba(255,255,255,0.04)'
      ctx.lineWidth = 1
      for (let x = 0; x < W; x += 40) {
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke()
      }
      for (let y = 0; y < H; y += 40) {
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke()
      }

      // Danger zone blobs
      ctx.fillStyle = 'rgba(255,77,77,0.07)'
      ctx.beginPath(); ctx.ellipse(220, 300, 70, 35, 0, 0, Math.PI * 2); ctx.fill()
      ctx.fillStyle = 'rgba(244,162,51,0.06)'
      ctx.beginPath(); ctx.ellipse(370, 215, 55, 28, 0, 0, Math.PI * 2); ctx.fill()

      // Draw all routes
      ROUTES.forEach((route, i) => {
        ctx.beginPath()
        ctx.moveTo(route.points[0][0], route.points[0][1])
        route.points.slice(1).forEach(([px, py]) => ctx.lineTo(px, py))
        ctx.strokeStyle = route.color
        ctx.lineWidth = i === active ? 3 : 1.5
        if (i !== active) ctx.setLineDash([8, 4])
        else ctx.setLineDash([])
        ctx.stroke()
        ctx.setLineDash([])

        // Route label at end
        const last = route.points[route.points.length - 1]
        ctx.fillStyle = route.color
        ctx.font = 'bold 10px DM Mono, monospace'
        ctx.fillText(`Route ${['A','B','C'][i]}`, last[0] + 6, last[1] + 4)
      })

      // Start & end dots
      ctx.beginPath(); ctx.arc(40, 180, 7, 0, Math.PI * 2)
      ctx.fillStyle = '#fff'; ctx.fill()
      ctx.strokeStyle = '#3be8b0'; ctx.lineWidth = 2; ctx.stroke()

      ctx.beginPath(); ctx.arc(580, 120, 7, 0, Math.PI * 2)
      ctx.fillStyle = '#fff'; ctx.fill()
      ctx.strokeStyle = '#3be8b0'; ctx.lineWidth = 2; ctx.stroke()

      // Animated vehicle on active route
      const pts = ROUTES[active].points
      const t   = (Date.now() / 3000) % 1
      const seg = Math.min(Math.floor(t * (pts.length - 1)), pts.length - 2)
      const segT = (t * (pts.length - 1)) - seg
      const vx = pts[seg][0] + (pts[seg + 1][0] - pts[seg][0]) * segT
      const vy = pts[seg][1] + (pts[seg + 1][1] - pts[seg][1]) * segT

      // Glow
      const gGrad = ctx.createRadialGradient(vx, vy, 0, vx, vy, 20)
      gGrad.addColorStop(0, 'rgba(59,232,176,0.35)')
      gGrad.addColorStop(1, 'transparent')
      ctx.fillStyle = gGrad
      ctx.fillRect(vx - 20, vy - 20, 40, 40)

      ctx.beginPath(); ctx.arc(vx, vy, 6, 0, Math.PI * 2)
      ctx.fillStyle = '#3be8b0'; ctx.fill()
      ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.stroke()

      // Hazard icons
      ctx.font = '16px serif'
      ctx.fillText('🚫', 213, 308)
      ctx.fillText('⚠️', 360, 222)

      animFrame = requestAnimationFrame(draw)
    }

    draw()
    return () => {
      cancelAnimationFrame(animFrame)
      window.removeEventListener('resize', resize)
    }
  }, [active])

  return (
    <section id="navigation" style={sectionStyle}>
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
      >
        <div style={labelStyle}><span style={labelLineStyle} />Module 03</div>
        <h2 style={titleStyle}>Path Memory &<br />Risk Navigation</h2>
        <p style={subStyle}>
          SLAM-generated underground route maps. Paths classified into
          safe, caution, and danger zones using real-time hazard data.
        </p>
      </motion.div>

      <div style={gridStyle}>
        {/* Map canvas */}
        <motion.div
          initial={{ opacity: 0, x: -30 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true }}
          style={mapWrapStyle}
        >
          <div style={mapHeaderStyle}>
            <span style={{ fontFamily: 'DM Mono, monospace', fontSize: '11px', color: '#5a5f72', textTransform: 'uppercase', letterSpacing: '1px' }}>
              Underground Map — Level B3
            </span>
            <span style={liveBadgeStyle}>
              <span style={liveDotStyle} /> SLAM Live
            </span>
          </div>
          <canvas ref={canvasRef} style={{ width: '100%', height: '340px', display: 'block' }} />
          <div style={mapFooterStyle}>
            {[['#3be8b0','Safe'],['#f4a233','Caution'],['#ff4d4d','Danger']].map(([c, l]) => (
              <div key={l} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <div style={{ width: '20px', height: '3px', background: c, borderRadius: '100px' }} />
                <span style={{ fontFamily: 'DM Mono, monospace', fontSize: '10px', color: '#5a5f72' }}>{l}</span>
              </div>
            ))}
          </div>
        </motion.div>

        {/* Route cards */}
        <motion.div
          initial={{ opacity: 0, x: 30 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true }}
          style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}
        >
          {ROUTES.map((route, i) => {
            const rc = RISK_COLORS[route.risk]
            return (
              <div
                key={route.name}
                onClick={() => setActive(i)}
                style={{
                  background: '#0d0f14',
                  border: `1px solid ${active === i ? route.color : 'rgba(255,255,255,0.07)'}`,
                  borderRadius: '14px',
                  padding: '18px 20px',
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '13px' }}>
                    <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: route.color }} />
                    {route.name}
                  </div>
                  <span style={{ fontFamily: 'DM Mono, monospace', fontSize: '10px', padding: '4px 10px', borderRadius: '100px', background: rc.bg, color: rc.text, border: `1px solid ${rc.border}` }}>
                    {route.risk}
                  </span>
                </div>
                <p style={{ fontSize: '12px', color: '#5a5f72', lineHeight: 1.6, marginBottom: '10px' }}>
                  {route.desc}
                </p>
                <div style={{ display: 'flex', gap: '16px' }}>
                  {[['📏', route.distance], ['⏱', route.time], ['🔩', route.note]].map(([icon, val]) => (
                    <span key={val} style={{ fontFamily: 'DM Mono, monospace', fontSize: '11px', color: '#5a5f72' }}>
                      {icon} {val}
                    </span>
                  ))}
                </div>
              </div>
            )
          })}

          {/* AI advice box */}
          <div style={{ background: '#0d0f14', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '14px', padding: '18px 20px' }}>
            <div style={{ fontFamily: 'DM Mono, monospace', fontSize: '10px', color: '#5a5f72', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '10px' }}>
              AI Navigation Advice
            </div>
            <p style={{ fontSize: '13px', color: '#e8eaf0', lineHeight: 1.7 }}>
              🧠 <strong>Recommended:</strong> Route A is optimal. 3 workers detected near Route B junction — maintain 50m clearance. Predicted stability window: <span style={{ color: '#f4a233' }}>4.8 hours</span>.
            </p>
          </div>
        </motion.div>
      </div>
    </section>
  )
}

const sectionStyle = { maxWidth: '1200px', margin: '0 auto', padding: '100px 48px' }
const labelStyle = { fontFamily: 'DM Mono, monospace', fontSize: '10px', letterSpacing: '3px', textTransform: 'uppercase', color: '#f4a233', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '12px' }
const labelLineStyle = { display: 'inline-block', width: '24px', height: '1px', background: '#f4a233' }
const titleStyle = { fontFamily: 'Syne, sans-serif', fontWeight: 800, fontSize: 'clamp(28px, 4vw, 48px)', letterSpacing: '-1.5px', color: '#fff', lineHeight: 1.1, marginBottom: '16px' }
const subStyle = { color: '#5a5f72', maxWidth: '480px', fontSize: '15px', lineHeight: 1.7, marginBottom: '48px' }
const gridStyle = { display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '32px', alignItems: 'start' }
const mapWrapStyle = { background: '#0d0f14', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '16px', overflow: 'hidden' }
const mapHeaderStyle = { padding: '16px 20px', borderBottom: '1px solid rgba(255,255,255,0.07)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }
const mapFooterStyle = { padding: '14px 20px', borderTop: '1px solid rgba(255,255,255,0.07)', display: 'flex', gap: '20px' }
const liveBadgeStyle = { fontFamily: 'DM Mono, monospace', fontSize: '10px', background: 'rgba(59,232,176,0.1)', border: '1px solid rgba(59,232,176,0.25)', color: '#3be8b0', padding: '4px 10px', borderRadius: '100px', display: 'flex', alignItems: 'center', gap: '6px' }
const liveDotStyle = { width: '6px', height: '6px', background: '#3be8b0', borderRadius: '50%', display: 'inline-block' }