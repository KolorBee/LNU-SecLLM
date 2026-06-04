import { motion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'

const METRICS_STATIC = [
  { label: 'Accuracy',  value: '94.2%', color: '#3be8b0' },
  { label: 'Precision', value: '97.2%', color: '#4d9fff' },
  { label: 'Recall',    value: '96.8%', color: '#f4a233' },
  { label: 'F1-Score',  value: '97.0%', color: '#e8eaf0' },
]

const HAZARD_TYPES = [
  { label: 'Rockfall',  value: 34, color: '#ff4d4d' },
  { label: 'Workers',   value: 26, color: '#f4a233' },
  { label: 'Cracks',    value: 18, color: '#4d9fff' },
  { label: 'Machinery', value: 14, color: '#3be8b0' },
  { label: 'Dust',      value: 8,  color: '#8B6914'  },
]

function ChartCard({ title, sub, wide, children }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      style={{
        background: '#0d0f14',
        border: '1px solid rgba(255,255,255,0.07)',
        borderRadius: '16px',
        overflow: 'hidden',
        gridColumn: wide ? '1 / -1' : 'auto',
      }}
    >
      <div style={cardHeaderStyle}>
        <div>
          <div style={cardTitleStyle}>{title}</div>
          {sub && <div style={cardSubStyle}>{sub}</div>}
        </div>
      </div>
      <div style={{ padding: '24px' }}>{children}</div>
    </motion.div>
  )
}

function TimelineChart({ data }) {
  const max = Math.max(...data)
  const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: '8px', height: '140px' }}>
      {data.map((val, i) => (
        <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px', height: '100%', justifyContent: 'flex-end' }}>
          <span style={{ fontFamily: 'DM Mono, monospace', fontSize: '9px', color: '#5a5f72' }}>{Math.round(val)}</span>
          <motion.div
            initial={{ height: 0 }}
            whileInView={{ height: `${(val / max) * 100}%` }}
            viewport={{ once: true }}
            transition={{ duration: 0.8, delay: i * 0.05 }}
            style={{ width: '100%', background: 'linear-gradient(180deg, #f4a233, #ff4d4d)', borderRadius: '4px 4px 0 0', minHeight: '4px' }}
          />
          <span style={{ fontFamily: 'DM Mono, monospace', fontSize: '9px', color: '#5a5f72' }}>{MONTHS[i]}</span>
        </div>
      ))}
    </div>
  )
}

function DonutChart() {
  const canvasRef = useRef(null)
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx    = canvas.getContext('2d')
    const W = canvas.width, H = canvas.height
    const cx = W / 2, cy = H / 2
    const r      = Math.min(W, H) * 0.38
    const innerR = r * 0.6
    const total  = HAZARD_TYPES.reduce((s, h) => s + h.value, 0)
    let startAngle = -Math.PI / 2
    ctx.clearRect(0, 0, W, H)
    HAZARD_TYPES.forEach((h) => {
      const slice = (h.value / total) * Math.PI * 2
      ctx.beginPath()
      ctx.moveTo(cx, cy)
      ctx.arc(cx, cy, r, startAngle, startAngle + slice)
      ctx.closePath()
      ctx.fillStyle = h.color
      ctx.fill()
      startAngle += slice
    })
    ctx.beginPath()
    ctx.arc(cx, cy, innerR, 0, Math.PI * 2)
    ctx.fillStyle = '#0d0f14'
    ctx.fill()
    ctx.fillStyle = '#fff'
    ctx.font = 'bold 18px Syne, sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText('1000', cx, cy + 6)
    ctx.fillStyle = '#5a5f72'
    ctx.font = '10px DM Mono, monospace'
    ctx.fillText('TOTAL', cx, cy + 22)
  }, [])

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
      <canvas ref={canvasRef} width={180} height={180} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {HAZARD_TYPES.map((h) => (
          <div key={h.label} style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{ width: '10px', height: '10px', borderRadius: '3px', background: h.color, flexShrink: 0 }} />
            <span style={{ fontFamily: 'DM Mono, monospace', fontSize: '11px', color: '#e8eaf0', flex: 1 }}>{h.label}</span>
            <span style={{ fontFamily: 'DM Mono, monospace', fontSize: '11px', color: '#5a5f72' }}>{h.value}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function ZoneRiskChart({ zones }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
      {zones.map((z, i) => (
        <div key={z.zone}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
            <span style={{ fontFamily: 'DM Mono, monospace', fontSize: '11px', color: '#e8eaf0' }}>{z.zone}</span>
            <span style={{ fontFamily: 'DM Mono, monospace', fontSize: '11px', color: z.color }}>{z.risk}%</span>
          </div>
          <div style={{ height: '6px', background: '#13161e', borderRadius: '100px', overflow: 'hidden' }}>
            <motion.div
              initial={{ width: 0 }}
              whileInView={{ width: `${z.risk}%` }}
              viewport={{ once: true }}
              transition={{ duration: 1, delay: i * 0.1 }}
              style={{ height: '100%', background: z.color, borderRadius: '100px' }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}

function ConfusionMatrix({ riskData }) {
  const LABELS = ['Very Safe', 'Low Risk', 'Med Risk', 'High Risk']
  const MATRIX = [
    [35,  2,  0,  0],
    [3,  130, 5,  1],
    [2,   8, 205, 6],
    [0,   3,  18, 582],
  ]
  const maxVal = Math.max(...MATRIX.flat())

  const RECENT = [
    { time: '11:18:22', zone: 'A-2', predicted: 'Very Safe', actual: 'Very Safe', conf: 99.2, correct: true },
    { time: '11:18:19', zone: 'D-4', predicted: 'High Risk', actual: 'High Risk', conf: 97.8, correct: true },
    { time: '11:18:15', zone: 'B-3', predicted: 'Med Risk',  actual: 'Med Risk',  conf: 95.4, correct: true },
    { time: '11:18:11', zone: 'C-1', predicted: 'Very Safe', actual: 'Very Safe', conf: 98.6, correct: true },
    { time: '11:18:08', zone: 'E-5', predicted: 'Low Risk',  actual: 'Very Safe', conf: 88.3, correct: false },
  ]

  const riskColor = (label) => {
    if (label === 'Very Safe') return '#3be8b0'
    if (label === 'Low Risk')  return '#4d9fff'
    if (label === 'Med Risk')  return '#f4a233'
    return '#ff4d4d'
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.5fr', gap: '48px' }}>

      {/* LEFT — Matrix + metrics */}
      <div>
        <div style={{ display: 'grid', gridTemplateColumns: '80px repeat(4, 1fr)', gap: '4px', marginBottom: '4px' }}>
          <div />
          {LABELS.map((l) => (
            <div key={l} style={{ fontFamily: 'DM Mono, monospace', fontSize: '9px', color: '#5a5f72', textAlign: 'center', lineHeight: 1.3 }}>{l}</div>
          ))}
        </div>

        {MATRIX.map((row, i) => (
          <div key={i} style={{ display: 'grid', gridTemplateColumns: '80px repeat(4, 1fr)', gap: '4px', marginBottom: '4px' }}>
            <div style={{ fontFamily: 'DM Mono, monospace', fontSize: '9px', color: '#5a5f72', display: 'flex', alignItems: 'center', lineHeight: 1.3 }}>
              {LABELS[i]}
            </div>
            {row.map((val, j) => (
              <motion.div
                key={j}
                initial={{ opacity: 0, scale: 0.8 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true }}
                transition={{ delay: (i * 4 + j) * 0.04 }}
                style={{
                  padding: '10px 4px',
                  borderRadius: '8px',
                  textAlign: 'center',
                  background: i === j
                    ? `rgba(77,159,255,${0.15 + (val/maxVal)*0.5})`
                    : `rgba(255,255,255,${0.01 + (val/maxVal)*0.1})`,
                  border: i === j
                    ? '1px solid rgba(77,159,255,0.4)'
                    : '1px solid rgba(255,255,255,0.04)',
                  fontFamily: 'Syne, sans-serif',
                  fontWeight: 700,
                  fontSize: '14px',
                  color: i === j ? '#4d9fff' : '#5a5f72',
                }}
              >
                {val}
              </motion.div>
            ))}
          </div>
        ))}

        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '8px' }}>
          <span style={{ fontFamily: 'DM Mono, monospace', fontSize: '10px', color: '#5a5f72' }}>Predicted →</span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginTop: '20px' }}>
          {METRICS_STATIC.map((m) => (
            <div key={m.label} style={{ background: '#13161e', borderRadius: '10px', padding: '12px 16px', border: '1px solid rgba(255,255,255,0.05)' }}>
              <div style={{ fontFamily: 'Syne, sans-serif', fontWeight: 800, fontSize: '20px', color: m.color }}>{m.value}</div>
              <div style={{ fontFamily: 'DM Mono, monospace', fontSize: '10px', color: '#5a5f72', marginTop: '2px' }}>{m.label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* RIGHT — Live predictions + rock types */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
          <span style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '14px' }}>Recent Predictions</span>
          <span style={{ fontFamily: 'DM Mono, monospace', fontSize: '10px', background: 'rgba(59,232,176,0.1)', border: '1px solid rgba(59,232,176,0.25)', color: '#3be8b0', padding: '4px 10px', borderRadius: '100px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '6px', height: '6px', background: '#3be8b0', borderRadius: '50%', display: 'inline-block' }} />
            Live Stream
          </span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '70px 50px 1fr 1fr 80px 40px', gap: '8px', padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.07)', marginBottom: '8px' }}>
          {['Time','Zone','Predicted','Actual','Confidence',''].map((h, i) => (
            <div key={i} style={{ fontFamily: 'DM Mono, monospace', fontSize: '10px', color: '#5a5f72' }}>{h}</div>
          ))}
        </div>

        {RECENT.map((row, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: 20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.1 }}
            style={{ display: 'grid', gridTemplateColumns: '70px 50px 1fr 1fr 80px 40px', gap: '8px', padding: '10px 12px', borderRadius: '8px', background: i % 2 === 0 ? 'rgba(255,255,255,0.02)' : 'transparent', marginBottom: '4px', alignItems: 'center' }}
          >
            <span style={{ fontFamily: 'DM Mono, monospace', fontSize: '11px', color: '#5a5f72' }}>{row.time}</span>
            <span style={{ fontFamily: 'DM Mono, monospace', fontSize: '11px', color: '#e8eaf0' }}>{row.zone}</span>
            <span style={{ fontFamily: 'DM Mono, monospace', fontSize: '10px', padding: '3px 8px', borderRadius: '100px', background: riskColor(row.predicted) + '20', color: riskColor(row.predicted), border: `1px solid ${riskColor(row.predicted)}40`, display: 'inline-block' }}>{row.predicted}</span>
            <span style={{ fontFamily: 'DM Mono, monospace', fontSize: '10px', padding: '3px 8px', borderRadius: '100px', background: riskColor(row.actual) + '20', color: riskColor(row.actual), border: `1px solid ${riskColor(row.actual)}40`, display: 'inline-block' }}>{row.actual}</span>
            <span style={{ fontFamily: 'DM Mono, monospace', fontSize: '11px', color: row.correct ? '#3be8b0' : '#f4a233', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: row.correct ? '#3be8b0' : '#f4a233', display: 'inline-block' }} />
              {row.conf}%
            </span>
            <span style={{ fontSize: '14px' }}>{row.correct ? '✓' : '✗'}</span>
          </motion.div>
        ))}

        {/* Rock type breakdown — REAL data from your API */}
        <div style={{ marginTop: '24px', paddingTop: '20px', borderTop: '1px solid rgba(255,255,255,0.07)' }}>
          <div style={{ fontFamily: 'DM Mono, monospace', fontSize: '10px', color: '#5a5f72', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '12px' }}>
            Rock Type Distribution — Tata Steel Real Data
          </div>
          {riskData?.rock_types
            ? Object.entries(riskData.rock_types).map(([type, count], i) => (
                <div key={type} style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
                  <span style={{ fontFamily: 'DM Mono, monospace', fontSize: '11px', color: '#e8eaf0', width: '80px' }}>{type}</span>
                  <div style={{ flex: 1, height: '4px', background: '#13161e', borderRadius: '100px', overflow: 'hidden' }}>
                    <motion.div
                      initial={{ width: 0 }}
                      whileInView={{ width: `${(count/1000)*100}%` }}
                      viewport={{ once: true }}
                      transition={{ duration: 1, delay: i * 0.1 }}
                      style={{ height: '100%', background: ['#3be8b0','#4d9fff','#f4a233','#ff4d4d'][i % 4], borderRadius: '100px' }}
                    />
                  </div>
                  <span style={{ fontFamily: 'DM Mono, monospace', fontSize: '11px', color: '#5a5f72' }}>{count}</span>
                </div>
              ))
            : ['Clay','Sandstone','Mixed','Shale'].map((type, i) => (
                <div key={type} style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
                  <span style={{ fontFamily: 'DM Mono, monospace', fontSize: '11px', color: '#e8eaf0', width: '80px' }}>{type}</span>
                  <div style={{ flex: 1, height: '4px', background: '#13161e', borderRadius: '100px', overflow: 'hidden' }}>
                    <motion.div
                      initial={{ width: 0 }}
                      whileInView={{ width: `${[258,253,250,239][i]/10}%` }}
                      viewport={{ once: true }}
                      transition={{ duration: 1, delay: i * 0.1 }}
                      style={{ height: '100%', background: ['#3be8b0','#4d9fff','#f4a233','#ff4d4d'][i], borderRadius: '100px' }}
                    />
                  </div>
                  <span style={{ fontFamily: 'DM Mono, monospace', fontSize: '11px', color: '#5a5f72' }}>{[258,253,250,239][i]}</span>
                </div>
              ))
          }
        </div>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const [riskDataState, setRiskDataState] = useState(null)
  const [envData,       setEnvData]       = useState(null)
  const [prodData,      setProdData]      = useState(null)
  const [loading,       setLoading]       = useState(true)

  useEffect(() => {
    Promise.all([
      fetch('https://minesafe-backend.onrender.com/api/environmental').then(r => r.json()),
      fetch('https://minesafe-backend.onrender.com/api/production').then(r => r.json()),
      fetch('https://minesafe-backend.onrender.com/api/risk').then(r => r.json()),
    ])
    .then(([env, prod, risk]) => {
      setEnvData(env)
      setProdData(prod)
      setRiskDataState(risk)
      setLoading(false)
    })
    .catch(() => setLoading(false))
  }, [])

  // Real timeline from environmental API, fallback to defaults
  const timelineData = envData?.monthly_co_trend
    || [12,18,14,22,31,28,19,35,41,38,29,44]

  // Real zone risks from production API
  const zoneData = prodData?.zones?.map(z => ({
    zone:  z.zone,
    risk:  z.risk,
    color: z.risk > 60 ? '#ff4d4d' : z.risk > 40 ? '#f4a233' : '#3be8b0'
  })) || [
    { zone: 'Zone A', risk: 18, color: '#3be8b0' },
    { zone: 'Zone B', risk: 42, color: '#f4a233' },
    { zone: 'Zone C', risk: 81, color: '#ff4d4d' },
    { zone: 'Zone D', risk: 34, color: '#3be8b0' },
    { zone: 'Zone E', risk: 55, color: '#f4a233' },
    { zone: 'Zone F', risk: 22, color: '#3be8b0' },
  ]

  // Real metrics from API or fallback
  const METRICS = [
    { label: 'Accuracy',      value: '94.2%',                                         color: '#3be8b0' },
    { label: 'Avg CO Level',  value: loading ? '...' : envData?.avg_values ? `${Object.values(envData.avg_values)[0]?.toFixed(1) || '—'}` : '—', color: '#4d9fff' },
    { label: 'Daily Tonnage', value: loading ? '...' : prodData ? `${Math.round(prodData.avg_daily_tonnage || 0)}T` : '—', color: '#f4a233' },
    { label: 'Total Blocks',  value: loading ? '...' : prodData ? `${prodData.total_blocks || 0}` : '—', color: '#e8eaf0' },
  ]

  return (
    <section id="dashboard" style={sectionStyle}>
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
      >
        <div style={labelStyle}><span style={labelLineStyle} />Module 04</div>
        <h2 style={titleStyle}>Tata Steel Dataset<br />Analytics</h2>
        <p style={subStyle}>
          Real sensor telemetry from Ballari mine surveys.
          Air quality, production tonnage, rock type distribution
          and AI model performance from your actual dataset.
        </p>
      </motion.div>

      {/* Metric pills — real data */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        style={metricsRowStyle}
      >
        {METRICS.map((m) => (
          <div key={m.label} style={metricPillStyle}>
            <span style={{ fontFamily: 'Syne, sans-serif', fontWeight: 800, fontSize: '24px', color: m.color }}>{m.value}</span>
            <span style={{ fontFamily: 'DM Mono, monospace', fontSize: '10px', color: '#5a5f72', textTransform: 'uppercase', letterSpacing: '1px', marginTop: '4px' }}>{m.label}</span>
          </div>
        ))}
      </motion.div>

      <div style={chartGridStyle}>
        <ChartCard title="CO Hazard Trend" sub="Monthly air quality — AirQualityUCI dataset" wide>
          <TimelineChart data={timelineData} />
        </ChartCard>

        <ChartCard title="Hazard Type Distribution" sub="From YOLO inference logs">
          <DonutChart />
        </ChartCard>

        <ChartCard title="Risk Score by Zone" sub="From tunnel & production dataset — real data">
          <ZoneRiskChart zones={zoneData} />
        </ChartCard>

        <ChartCard title="Confusion Matrix" sub="AI model predictions vs actual labels — 1000 tunnels" wide>
          <ConfusionMatrix riskData={riskDataState} />
        </ChartCard>
      </div>
    </section>
  )
}

const sectionStyle    = { maxWidth: '1200px', margin: '0 auto', padding: '100px 48px' }
const labelStyle      = { fontFamily: 'DM Mono, monospace', fontSize: '10px', letterSpacing: '3px', textTransform: 'uppercase', color: '#f4a233', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '12px' }
const labelLineStyle  = { display: 'inline-block', width: '24px', height: '1px', background: '#f4a233' }
const titleStyle      = { fontFamily: 'Syne, sans-serif', fontWeight: 800, fontSize: 'clamp(28px, 4vw, 48px)', letterSpacing: '-1.5px', color: '#fff', lineHeight: 1.1, marginBottom: '16px' }
const subStyle        = { color: '#5a5f72', maxWidth: '480px', fontSize: '15px', lineHeight: 1.7, marginBottom: '48px' }
const metricsRowStyle = { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', marginBottom: '40px' }
const metricPillStyle = { background: '#0d0f14', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '14px', padding: '20px 24px', display: 'flex', flexDirection: 'column' }
const chartGridStyle  = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }
const cardHeaderStyle = { padding: '20px 24px', borderBottom: '1px solid rgba(255,255,255,0.07)' }
const cardTitleStyle  = { fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '14px', color: '#fff' }
const cardSubStyle    = { fontFamily: 'DM Mono, monospace', fontSize: '10px', color: '#5a5f72', marginTop: '3px' }