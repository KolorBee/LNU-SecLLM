import { useState, useRef, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

const API_URL = 'http://127.0.0.1:8000/api/detect'

export default function HazardDetector() {
  const [imageUrl, setImageUrl]   = useState(null)
  const [imageFile, setImageFile] = useState(null)
  const [loading, setLoading]     = useState(false)
  const [results, setResults]     = useState([])
  const [done, setDone]           = useState(false)
  const [avgConf, setAvgConf]     = useState(0)

  const imgRef    = useRef(null)
  const canvasRef = useRef(null)

  function handleUpload(e) {
    const file = e.target.files[0]
    if (!file) return
    setImageFile(file)
    setImageUrl(URL.createObjectURL(file))
    setResults([])
    setDone(false)
    clearCanvas()
  }

  function clearCanvas() {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    ctx.clearRect(0, 0, canvas.width, canvas.height)
  }

  const drawBoxes = useCallback((detections) => {
    const img    = imgRef.current
    const canvas = canvasRef.current
    if (!img || !canvas || !detections.length) return

    // Match canvas pixel size to the rendered image size
    canvas.width  = img.offsetWidth
    canvas.height = img.offsetHeight

    const ctx = canvas.getContext('2d')
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    // YOLO returns coords in original image pixel space; scale to rendered size
    const scaleX = img.offsetWidth  / img.naturalWidth
    const scaleY = img.offsetHeight / img.naturalHeight

    detections.forEach((det) => {
      if (!det.box || det.box.length < 4) return
      const [x1, y1, x2, y2] = det.box
      const rx = x1 * scaleX
      const ry = y1 * scaleY
      const rw = (x2 - x1) * scaleX
      const rh = (y2 - y1) * scaleY

      ctx.strokeStyle = det.color || '#ff4d4d'
      ctx.lineWidth   = 2
      ctx.strokeRect(rx, ry, rw, rh)

      // Label background
      const label   = `${det.icon || ''} ${det.name}  ${det.confidence}%`
      ctx.font      = 'bold 11px DM Mono, monospace'
      const textW   = ctx.measureText(label).width
      ctx.fillStyle = det.color || '#ff4d4d'
      ctx.fillRect(rx, ry - 20, textW + 10, 20)

      // Label text
      ctx.fillStyle = '#000'
      ctx.fillText(label, rx + 5, ry - 6)
    })
  }, [])

  async function runDetection() {
    if (!imageFile) return
    setLoading(true)
    setResults([])
    setDone(false)
    clearCanvas()

    try {
      const form = new FormData()
      form.append('file', imageFile)

      const res  = await fetch(API_URL, { method: 'POST', body: form })
      const data = await res.json()

      const detections = data.detections || []
      setResults(detections)
      setAvgConf(data.confidence ?? 0)
      setDone(true)

      // Draw after state update — wait one frame for img to be in DOM
      requestAnimationFrame(() => drawBoxes(detections))
    } catch (err) {
      setResults([{ icon: '⚠️', name: `Error: ${err.message}`, confidence: 0, risk: 'ERROR', color: '#ff4d4d' }])
      setDone(true)
    } finally {
      setLoading(false)
    }
  }

  return (
    <section id="detect" style={sectionStyle}>

      {/* Section Header */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
      >
        <div style={labelStyle}>
          <span style={labelLineStyle} />
          Module 01
        </div>
        <h2 style={titleStyle}>智能矿山高精度<br />危险源监测系统</h2>
        <p style={subStyle}>
          基于深度学习 YOLO 算法与多源传感器融合的智能监测平台。
          本系统可针对露天及井下矿山环境，实现对落石、结构裂缝等高危隐患的实时高精度识别，为矿山安全生产保驾护航。
        </p>
      </motion.div>

      {/* Main Grid */}
      <div style={gridStyle}>

        {/* LEFT — Upload + Canvas overlay */}
        <div>
          <div
            style={{
              ...uploadZoneStyle,
              borderColor: imageUrl ? '#3be8b0' : 'rgba(255,255,255,0.07)',
            }}
            onClick={() => document.getElementById('fileInput').click()}
          >
            <input
              id="fileInput"
              type="file"
              accept="image/*"
              style={{ display: 'none' }}
              onChange={handleUpload}
            />
            {imageUrl ? (
              <div style={{ position: 'relative', lineHeight: 0 }}>
                <img
                  ref={imgRef}
                  src={imageUrl}
                  alt="uploaded"
                  style={{ width: '100%', height: '300px', objectFit: 'cover', borderRadius: '12px', display: 'block' }}
                />
                <canvas
                  ref={canvasRef}
                  style={{
                    position: 'absolute',
                    top: 0, left: 0,
                    width: '100%', height: '100%',
                    borderRadius: '12px',
                    pointerEvents: 'none',
                  }}
                />
              </div>
            ) : (
              <div style={{ textAlign: 'center', padding: '48px 24px' }}>
                <div style={uploadIconStyle}>📸</div>
                <div style={uploadTextStyle}>请上传矿山现场图像</div>
                <div style={uploadHintStyle}>支持 PNG、JPG 格式 · 可见光或热成像</div>
              </div>
            )}
          </div>

          <button
            onClick={runDetection}
            disabled={!imageUrl || loading}
            style={{
              ...detectBtnStyle,
              opacity: !imageUrl || loading ? 0.5 : 1,
              cursor: !imageUrl || loading ? 'not-allowed' : 'pointer',
            }}
          >
            {loading ? '⏳ YOLO 推理中...' : done ? '✅ 重新检测' : '⚡ 上传图片并检测'}
          </button>
        </div>

        {/* RIGHT — Results */}
        <div style={resultsPanelStyle}>
          <div style={resultsHeaderStyle}>
            <span style={resultsTitleStyle}>智能分析结果</span>
            <span style={liveBadgeStyle}>
              <span style={liveDotStyle} />
              YOLOv8
            </span>
          </div>

          <div style={{ padding: '24px' }}>
            {/* Empty state */}
            {!loading && results.length === 0 && (
              <div style={emptyStateStyle}>
                <div style={{ fontSize: '32px', marginBottom: '12px' }}>🔭</div>
                <p style={{ fontFamily: 'DM Mono, monospace', fontSize: '12px', color: '#5a5f72' }}>
                  请上传矿山现场图像以启动智能分析
                </p>
              </div>
            )}

            {/* Loading state */}
            {loading && (
              <div style={emptyStateStyle}>
                <motion.div
                  animate={{ rotate: 360 }}
                  transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                  style={{ fontSize: '32px', marginBottom: '12px' }}
                >
                  ⚙️
                </motion.div>
                <p style={{ fontFamily: 'DM Mono, monospace', fontSize: '12px', color: '#5a5f72' }}>
                  图像分析中...
                </p>
              </div>
            )}

            {/* Results list */}
            <AnimatePresence>
              {results.map((item, i) => (
                <motion.div
                  key={item.name + i}
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.15 }}
                  style={hazardItemStyle}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <div style={{
                      width: '36px', height: '36px',
                      borderRadius: '8px',
                      background: item.color + '20',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: '16px',
                    }}>
                      {item.icon}
                    </div>
                    <div>
                      <div style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '13px' }}>
                        {item.name}
                      </div>
                      <div style={{ fontFamily: 'DM Mono, monospace', fontSize: '10px', color: '#5a5f72' }}>
                        置信度: {item.confidence}%
                      </div>
                    </div>
                  </div>
                  <span style={{
                    fontFamily: 'DM Mono, monospace',
                    fontSize: '10px',
                    padding: '4px 10px',
                    borderRadius: '100px',
                    background: item.color + '20',
                    color: item.color,
                    border: `1px solid ${item.color}40`,
                  }}>
                    {item.risk}
                  </span>
                </motion.div>
              ))}
            </AnimatePresence>

            {/* Confidence bar */}
            {done && results.length > 0 && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                style={{ marginTop: '20px', paddingTop: '20px', borderTop: '1px solid rgba(255,255,255,0.07)' }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'DM Mono, monospace', fontSize: '10px', color: '#5a5f72', marginBottom: '8px' }}>
                  <span>系统综合置信度</span>
                  <span>{avgConf}%</span>
                </div>
                <div style={{ height: '4px', background: '#13161e', borderRadius: '100px', overflow: 'hidden' }}>
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${avgConf}%` }}
                    transition={{ duration: 1, delay: 0.5 }}
                    style={{ height: '100%', background: 'linear-gradient(90deg, #3be8b0, #f4a233)', borderRadius: '100px' }}
                  />
                </div>
              </motion.div>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}

const sectionStyle = {
  maxWidth: '1200px',
  margin: '0 auto',
  padding: '100px 48px',
}
const labelStyle = {
  fontFamily: 'DM Mono, monospace',
  fontSize: '10px',
  letterSpacing: '3px',
  textTransform: 'uppercase',
  color: '#f4a233',
  marginBottom: '16px',
  display: 'flex',
  alignItems: 'center',
  gap: '12px',
}
const labelLineStyle = {
  display: 'inline-block',
  width: '24px', height: '1px',
  background: '#f4a233',
}
const titleStyle = {
  fontFamily: 'Syne, sans-serif',
  fontWeight: 800,
  fontSize: 'clamp(28px, 4vw, 48px)',
  letterSpacing: '-1.5px',
  color: '#fff',
  lineHeight: 1.1,
  marginBottom: '16px',
}
const subStyle = {
  color: '#5a5f72',
  maxWidth: '480px',
  fontSize: '15px',
  lineHeight: 1.7,
  marginBottom: '48px',
}
const gridStyle = {
  display: 'grid',
  gridTemplateColumns: '1fr 1fr',
  gap: '24px',
  alignItems: 'start',
}
const uploadZoneStyle = {
  border: '1.5px dashed',
  borderRadius: '16px',
  background: '#0d0f14',
  cursor: 'pointer',
  overflow: 'hidden',
  transition: 'border-color 0.3s',
}
const uploadIconStyle = {
  width: '56px', height: '56px',
  background: 'rgba(244,162,51,0.1)',
  border: '1px solid rgba(244,162,51,0.2)',
  borderRadius: '16px',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  margin: '0 auto 16px',
  fontSize: '22px',
}
const uploadTextStyle = {
  fontFamily: 'Syne, sans-serif',
  fontWeight: 600,
  fontSize: '15px',
  color: '#e8eaf0',
  marginBottom: '8px',
}
const uploadHintStyle = {
  fontFamily: 'DM Mono, monospace',
  fontSize: '11px',
  color: '#5a5f72',
}
const detectBtnStyle = {
  width: '100%',
  marginTop: '16px',
  background: '#f4a233',
  color: '#000',
  fontFamily: 'Syne, sans-serif',
  fontWeight: 700,
  fontSize: '14px',
  padding: '16px',
  borderRadius: '10px',
  border: 'none',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: '8px',
  transition: 'all 0.2s',
}
const resultsPanelStyle = {
  background: '#0d0f14',
  border: '1px solid rgba(255,255,255,0.07)',
  borderRadius: '16px',
  overflow: 'hidden',
}
const resultsHeaderStyle = {
  padding: '20px 24px',
  borderBottom: '1px solid rgba(255,255,255,0.07)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
}
const resultsTitleStyle = {
  fontFamily: 'Syne, sans-serif',
  fontWeight: 700,
  fontSize: '14px',
}
const liveBadgeStyle = {
  fontFamily: 'DM Mono, monospace',
  fontSize: '10px',
  letterSpacing: '1px',
  background: 'rgba(59,232,176,0.1)',
  border: '1px solid rgba(59,232,176,0.25)',
  color: '#3be8b0',
  padding: '4px 10px',
  borderRadius: '100px',
  display: 'flex',
  alignItems: 'center',
  gap: '6px',
}
const liveDotStyle = {
  width: '6px', height: '6px',
  background: '#3be8b0',
  borderRadius: '50%',
}
const emptyStateStyle = {
  textAlign: 'center',
  padding: '48px 24px',
}
const hazardItemStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '14px 16px',
  borderRadius: '10px',
  background: '#13161e',
  marginBottom: '10px',
  border: '1px solid rgba(255,255,255,0.07)',
}
