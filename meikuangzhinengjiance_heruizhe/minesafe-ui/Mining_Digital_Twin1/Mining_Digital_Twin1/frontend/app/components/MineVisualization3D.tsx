import { useEffect, useRef, useState } from 'react';
import { Maximize2, ZoomIn, ZoomOut, RotateCw } from 'lucide-react';

export function MineVisualization3D() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [rotation, setRotation] = useState(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Draw grid background
      ctx.strokeStyle = '#1e2836';
      ctx.lineWidth = 1;
      
      // Horizontal lines
      for (let i = 0; i <= 20; i++) {
        ctx.beginPath();
        ctx.moveTo(0, (canvas.height / 20) * i);
        ctx.lineTo(canvas.width, (canvas.height / 20) * i);
        ctx.stroke();
      }
      
      // Vertical lines
      for (let i = 0; i <= 20; i++) {
        ctx.beginPath();
        ctx.moveTo((canvas.width / 20) * i, 0);
        ctx.lineTo((canvas.width / 20) * i, canvas.height);
        ctx.stroke();
      }

      // Draw 3D-like mine structure with perspective
      const centerX = canvas.width / 2;
      const centerY = canvas.height / 2;
      const time = Date.now() * 0.001 + rotation;

      // Draw main mine shaft (central structure)
      ctx.save();
      ctx.translate(centerX, centerY);
      
      // Level 1 - Top
      drawMineLevel(ctx, 0, -120, 200, 40, '#1e3a8a', time);
      
      // Level 2
      drawMineLevel(ctx, 0, -70, 180, 40, '#1e40af', time + 0.5);
      
      // Level 3
      drawMineLevel(ctx, 0, -20, 160, 40, '#2563eb', time + 1);
      
      // Level 4 - High Risk Zone
      drawMineLevel(ctx, 0, 30, 140, 40, '#ea580c', time + 1.5);
      
      // Level 5 - Bottom
      drawMineLevel(ctx, 0, 80, 120, 40, '#1e40af', time + 2);

      // Draw connecting shafts
      ctx.strokeStyle = '#334155';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(-80, -100);
      ctx.lineTo(-60, 60);
      ctx.stroke();
      
      ctx.beginPath();
      ctx.moveTo(80, -100);
      ctx.lineTo(60, 60);
      ctx.stroke();

      // Draw sensor points
      drawSensorPoint(ctx, -90, -90, '#22c55e', true);
      drawSensorPoint(ctx, 95, -85, '#22c55e', true);
      drawSensorPoint(ctx, -70, 0, '#f59e0b', false);
      drawSensorPoint(ctx, 75, 10, '#ef4444', false);
      drawSensorPoint(ctx, 0, 90, '#22c55e', true);

      ctx.restore();
    };

    const drawMineLevel = (
      ctx: CanvasRenderingContext2D, 
      x: number, 
      y: number, 
      width: number, 
      height: number, 
      color: string,
      time: number
    ) => {
      const offset = Math.sin(time) * 5;
      
      // Top face
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.moveTo(x - width/2, y);
      ctx.lineTo(x + width/2, y);
      ctx.lineTo(x + width/2 - 10, y - 10);
      ctx.lineTo(x - width/2 + 10, y - 10);
      ctx.closePath();
      ctx.fill();
      
      // Front face
      ctx.fillStyle = adjustBrightness(color, -20);
      ctx.fillRect(x - width/2, y, width, height);
      
      // Side face (right)
      ctx.fillStyle = adjustBrightness(color, -40);
      ctx.beginPath();
      ctx.moveTo(x + width/2, y);
      ctx.lineTo(x + width/2 - 10, y - 10);
      ctx.lineTo(x + width/2 - 10, y + height - 10);
      ctx.lineTo(x + width/2, y + height);
      ctx.closePath();
      ctx.fill();

      // Draw grid pattern on face
      ctx.strokeStyle = adjustBrightness(color, 30);
      ctx.lineWidth = 1;
      for (let i = 1; i < 3; i++) {
        ctx.beginPath();
        ctx.moveTo(x - width/2, y + (height / 3) * i);
        ctx.lineTo(x + width/2, y + (height / 3) * i);
        ctx.stroke();
      }

      // Highlight if high risk
      if (color === '#ea580c') {
        ctx.strokeStyle = '#f97316';
        ctx.lineWidth = 2;
        ctx.strokeRect(x - width/2 - 2, y - 2, width + 4, height + 4);
      }
    };

    const drawSensorPoint = (
      ctx: CanvasRenderingContext2D,
      x: number,
      y: number,
      color: string,
      active: boolean
    ) => {
      // Outer glow
      if (active) {
        const gradient = ctx.createRadialGradient(x, y, 0, x, y, 12);
        gradient.addColorStop(0, color + '40');
        gradient.addColorStop(1, color + '00');
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(x, y, 12, 0, Math.PI * 2);
        ctx.fill();
      }

      // Sensor point
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(x, y, 4, 0, Math.PI * 2);
      ctx.fill();

      // Pulse animation
      if (active) {
        const pulse = Math.sin(Date.now() * 0.005) * 0.5 + 0.5;
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.globalAlpha = pulse;
        ctx.beginPath();
        ctx.arc(x, y, 6 + pulse * 3, 0, Math.PI * 2);
        ctx.stroke();
        ctx.globalAlpha = 1;
      }
    };

    const adjustBrightness = (color: string, percent: number) => {
      const num = parseInt(color.replace('#', ''), 16);
      const amt = Math.round(2.55 * percent);
      const R = (num >> 16) + amt;
      const G = (num >> 8 & 0x00FF) + amt;
      const B = (num & 0x0000FF) + amt;
      return '#' + (0x1000000 + (R < 255 ? R < 1 ? 0 : R : 255) * 0x10000 +
        (G < 255 ? G < 1 ? 0 : G : 255) * 0x100 +
        (B < 255 ? B < 1 ? 0 : B : 255))
        .toString(16).slice(1);
    };

    // Animation loop
    let animationId: number;
    const animate = () => {
      draw();
      animationId = requestAnimationFrame(animate);
    };
    animate();

    return () => {
      cancelAnimationFrame(animationId);
    };
  }, [rotation]);

  return (
    <div className="bg-[#0f1419] border border-[#1e2836] rounded-lg h-full flex flex-col">
      {/* Controls Bar */}
      <div className="flex items-center justify-between border-b border-[#1e2836] px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-100">3D Mine Structure</h3>
          <p className="text-xs text-gray-400">Real-time visualization</p>
        </div>
        <div className="flex items-center gap-2">
          <button className="p-2 hover:bg-[#1e2836] rounded transition-colors">
            <ZoomIn className="w-4 h-4 text-gray-400" />
          </button>
          <button className="p-2 hover:bg-[#1e2836] rounded transition-colors">
            <ZoomOut className="w-4 h-4 text-gray-400" />
          </button>
          <button 
            onClick={() => setRotation(r => r + Math.PI / 4)}
            className="p-2 hover:bg-[#1e2836] rounded transition-colors"
          >
            <RotateCw className="w-4 h-4 text-gray-400" />
          </button>
          <button className="p-2 hover:bg-[#1e2836] rounded transition-colors">
            <Maximize2 className="w-4 h-4 text-gray-400" />
          </button>
        </div>
      </div>

      {/* Canvas */}
      <div className="flex-1 relative p-4">
        <canvas
          ref={canvasRef}
          width={800}
          height={600}
          className="w-full h-full rounded"
          style={{ background: '#0a0e1a' }}
        />
        
        {/* Overlay Info */}
        <div className="absolute bottom-8 left-8 space-y-2">
          <div className="flex items-center gap-2 text-xs">
            <div className="w-3 h-3 bg-blue-500 rounded"></div>
            <span className="text-gray-300">Normal Operation</span>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <div className="w-3 h-3 bg-orange-500 rounded"></div>
            <span className="text-gray-300">High Risk Zone</span>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <div className="w-3 h-3 bg-green-500 rounded-full"></div>
            <span className="text-gray-300">Active Sensor</span>
          </div>
        </div>

        {/* Depth Indicator */}
        <div className="absolute top-8 right-8 bg-[#0f1419] border border-[#1e2836] rounded p-3">
          <p className="text-xs text-gray-400 mb-2">Depth (m)</p>
          <div className="space-y-1">
            {['0', '-50', '-100', '-150', '-200'].map((depth, i) => (
              <div key={i} className="flex items-center gap-2">
                <div className="w-8 h-0.5 bg-gray-600"></div>
                <span className="text-xs text-gray-300">{depth}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
