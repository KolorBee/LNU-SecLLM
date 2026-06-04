import { motion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'

const LAYERS = [
  { color: '#e8c84a', label: 'Top Soil & Overburden', depth: '0–12m',  risk: 18,  desc: 'Loose alluvial deposits. High permeability, prone to water ingress.', riskColor: '#3be8b0' },
  { color: '#8B6914', label: 'Clay Layer',            depth: '12–28m', risk: 28,  desc: 'Dense clay with moderate compression strength. Stable under dry conditions.', riskColor: '#3be8b0' },
  { color: '#5C3D2E', label: 'Iron Ore Deposit',      depth: '28–45m', risk: 42,  desc: 'High-grade hematite (Ballari region). Primary extraction zone.', riskColor: '#f4a233' },
  { color: '#cc3333', label: '⚠ Unstable Shale',      depth: '45–58m', risk: 81,  desc: 'Fractured shale zone. Rockfall risk elevated. Restricted access.', riskColor: '#ff4d4d' },
  { color: '#2d4a8a', label: 'Coal Seam',             depth: '58–80m', risk: 55,  desc: 'Sub-bituminous coal. Moderate methane emission risk.', riskColor: '#f4a233' },
  { color: '#333333',    label: 'Bedrock',               depth: '80m+',   risk: 12,  desc: 'Granite bedrock. High structural integrity. Foundation layer.', riskColor: '#3be8b0' },
]

export default function DigitalTwin() {
  const canvasRef = useRef(null)
  const [activeLayer, setActiveLayer] = useState(0)

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

      // Draw each geological layer
      const layerHeights = [0.12, 0.14, 0.20, 0.10, 0.20, 0.24]
      let y = 0
      LAYERS.forEach((layer, i) => {
        const lh = H * layerHeights[i]

        // Gradient fill
        const grad = ctx.createLinearGradient(0, y, W, y + lh)
        grad.addColorStop(0, layer.color + 'cc')
        grad.addColorStop(0.5, layer.color + 'ff')
        grad.addColorStop(1, layer.color + '88')
        ctx.fillStyle = grad
        ctx.fillRect(0, y, W, lh)

        // Active layer highlight
        if (i === activeLayer) {
          ctx.strokeStyle = 'rgba(255,255,255,0.8)'
          ctx.lineWidth = 2
          ctx.strokeRect(1, y + 1, W - 2, lh - 2)
        }

        // High risk flash
        if (layer.risk > 60) {
          const t = Date.now() / 1000
          ctx.fillStyle = `rgba(255,77,77,${0.04 + 0.04 * Math.sin(t * 2)})`
          ctx.fillRect(0, y, W, lh)
        }

        // Layer label
        ctx.fillStyle = 'rgba(255,255,255,0.9)'
        ctx.font = `bold 11px DM Mono, monospace`
        ctx.fillText(layer.label, 12, y + lh / 2 + 4)

        // Depth label right side
        ctx.fillStyle = 'rgba(255,255,255,0.4)'
        ctx.font = `10px DM Mono, monospace`
        ctx.fillText(layer.depth, W - 52, y + 14)

        y += lh
      })

      // Rocks scattered
      ctx.fillStyle = 'rgba(200,180,150,0.5)'
      ;[[60,90,14],[180,160,10],[300,120,18],[420,200,12],[150,260,16],[380,310,11]].forEach(([rx, ry, rr]) => {
        ctx.beginPath()
        ctx.arc(rx, ry, rr, 0, Math.PI * 2)
        ctx.fill()
      })

      // Animated scan line
      const scanY = (Date.now() / 20) % H
      const scanGrad = ctx.createLinearGradient(0, scanY - 6, 0, scanY + 6)
      scanGrad.addColorStop(0, 'transparent')
      scanGrad.addColorStop(0.5, 'rgba(59,232,176,0.5)')
      scanGrad.addColorStop(1, 'transparent')
      ctx.fillStyle = scanGrad
      ctx.fillRect(0, scanY - 6, W, 12)

      animFrame = requestAnimationFrame(draw)
    }

    draw()
    return () => {
      cancelAnimationFrame(animFrame)
      window.removeEventListener('resize', resize)
    }
  }, [activeLayer])

  return (
    <section id="digital-twin" style={sectionStyle}>
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
      >
        <div style={labelStyle}><span style={labelLineStyle} />Module 02</div>
        <h2 style={titleStyle}>Cognitive<br />Digital Twin</h2>
        <p style={subStyle}>
          Underground soil and rock stratification reconstructed from
          Tata Steel geological datasets — without physical excavation.
          AI predicts rockfall and landslide risk from temporal patterns.
        </p>
      </motion.div>

      <div style={gridStyle}>
        {/* Canvas */}
        <motion.div
          initial={{ opacity: 0, x: -30 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true }}
          style={canvasWrapStyle}
        >
          <canvas
            ref={canvasRef}
            style={{ width: '100%', height: '420px', display: 'block' }}
          />
          {/* Legend overlay */}
          <div style={legendStyle}>
            <div style={legendTitleStyle}>Layer Legend</div>
            {LAYERS.map((l) => (
              <div key={l.label} style={legendItemStyle}>
                <div style={{ width: '10px', height: '10px', borderRadius: '3px', background: l.color, flexShrink: 0 }} />
                <span style={{ fontFamily: 'DM Mono, monospace', fontSize: '11px', color: '#e8eaf0' }}>
                  {l.label.replace('⚠ ', '')}
                </span>
              </div>
            ))}
          </div>
        </motion.div>

        {/* Layer cards */}
        <motion.div
          initial={{ opacity: 0, x: 30 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true }}
        >
          {LAYERS.map((layer, i) => (
            <div
              key={layer.label}
              onClick={() => setActiveLayer(i)}
              style={{
                ...layerCardStyle,
                borderColor: activeLayer === i ? '#f4a233' : 'rgba(255,255,255,0.07)',
                background: activeLayer === i ? 'rgba(244,162,51,0.05)' : '#0d0f14',
                cursor: 'pointer',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <div style={{ width: '10px', height: '10px', borderRadius: '3px', background: layer.color }} />
                  <span style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '13px' }}>
                    {layer.label}
                  </span>
                </div>
                <span style={{ fontFamily: 'DM Mono, monospace', fontSize: '11px', color: '#5a5f72' }}>
                  {layer.depth}
                </span>
              </div>
              <p style={{ fontSize: '12px', color: '#5a5f72', lineHeight: 1.6, marginBottom: '10px' }}>
                {layer.desc}
              </p>
              {/* Risk bar */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontFamily: 'DM Mono, monospace', fontSize: '10px', color: '#5a5f72', whiteSpace: 'nowrap' }}>
                  Risk
                </span>
                <div style={{ flex: 1, height: '3px', background: '#13161e', borderRadius: '100px', overflow: 'hidden' }}>
                  <motion.div
                    initial={{ width: 0 }}
                    whileInView={{ width: `${layer.risk}%` }}
                    viewport={{ once: true }}
                    transition={{ duration: 1, delay: i * 0.1 }}
                    style={{ height: '100%', background: layer.riskColor, borderRadius: '100px' }}
                  />
                </div>
                <span style={{ fontFamily: 'DM Mono, monospace', fontSize: '10px', color: layer.riskColor }}>
                  {layer.risk}%
                </span>
              </div>
            </div>
          ))}
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
const gridStyle = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '32px', alignItems: 'start' }
const canvasWrapStyle = { borderRadius: '16px', overflow: 'hidden', border: '1px solid rgba(255,255,255,0.07)', position: 'relative' }
const legendStyle = { position: 'absolute', top: '16px', left: '16px', background: 'rgba(5,6,8,0.85)', backdropFilter: 'blur(12px)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '10px', padding: '12px 16px' }
const legendTitleStyle = { fontFamily: 'DM Mono, monospace', fontSize: '10px', color: '#5a5f72', letterSpacing: '1px', textTransform: 'uppercase', marginBottom: '8px' }
const legendItemStyle = { display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }
const layerCardStyle = { border: '1px solid', borderRadius: '12px', padding: '16px', marginBottom: '12px', transition: 'all 0.2s' }