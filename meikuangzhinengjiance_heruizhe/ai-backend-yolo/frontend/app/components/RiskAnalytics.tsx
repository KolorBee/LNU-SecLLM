import { AreaChart, Area, LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { TrendingUp, AlertCircle } from 'lucide-react';

const riskTrendData = [
  { time: '00:00', risk: 23, safe: 77 },
  { time: '04:00', risk: 28, safe: 72 },
  { time: '08:00', risk: 35, safe: 65 },
  { time: '12:00', risk: 42, safe: 58 },
  { time: '16:00', risk: 38, safe: 62 },
  { time: '20:00', risk: 31, safe: 69 },
  { time: '24:00', risk: 27, safe: 73 }
];

const zoneData = [
  { zone: 'A', level: 85 },
  { zone: 'B', level: 72 },
  { zone: 'C', level: 91 },
  { zone: 'D', level: 65 },
  { zone: 'E', level: 78 }
];

const riskDistribution = [
  { name: 'Low Risk', value: 45, color: '#22c55e' },
  { name: 'Medium Risk', value: 35, color: '#3b82f6' },
  { name: 'High Risk', value: 20, color: '#f97316' }
];

export function RiskAnalytics() {
  return (
    <div className="space-y-4">
      {/* Risk Trend Over Time */}
      <div className="bg-[#0f1419] border border-[#1e2836] rounded-lg p-4">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-sm font-semibold text-gray-100">Risk Trend Analysis</h3>
            <p className="text-xs text-gray-400">24-hour overview</p>
          </div>
          <TrendingUp className="w-4 h-4 text-orange-500" />
        </div>
        <ResponsiveContainer width="100%" height={180}>
          <AreaChart data={riskTrendData}>
            <defs>
              <linearGradient id="colorRisk" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#f97316" stopOpacity={0.3}/>
                <stop offset="95%" stopColor="#f97316" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e2836" />
            <XAxis 
              dataKey="time" 
              stroke="#6b7280" 
              style={{ fontSize: '11px' }}
            />
            <YAxis 
              stroke="#6b7280" 
              style={{ fontSize: '11px' }}
            />
            <Tooltip 
              contentStyle={{ 
                backgroundColor: '#0f1419', 
                border: '1px solid #1e2836',
                borderRadius: '6px',
                fontSize: '12px'
              }}
            />
            <Area 
              type="monotone" 
              dataKey="risk" 
              stroke="#f97316" 
              strokeWidth={2}
              fillOpacity={1} 
              fill="url(#colorRisk)" 
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Zone Safety Levels */}
      <div className="bg-[#0f1419] border border-[#1e2836] rounded-lg p-4">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-sm font-semibold text-gray-100">Zone Safety Levels</h3>
            <p className="text-xs text-gray-400">Current status</p>
          </div>
          <AlertCircle className="w-4 h-4 text-blue-400" />
        </div>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={zoneData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e2836" />
            <XAxis 
              dataKey="zone" 
              stroke="#6b7280" 
              style={{ fontSize: '11px' }}
            />
            <YAxis 
              stroke="#6b7280" 
              style={{ fontSize: '11px' }}
            />
            <Tooltip 
              contentStyle={{ 
                backgroundColor: '#0f1419', 
                border: '1px solid #1e2836',
                borderRadius: '6px',
                fontSize: '12px'
              }}
            />
            <Bar dataKey="level" fill="#3b82f6" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Risk Distribution */}
      <div className="bg-[#0f1419] border border-[#1e2836] rounded-lg p-4">
        <div className="mb-4">
          <h3 className="text-sm font-semibold text-gray-100">Risk Distribution</h3>
          <p className="text-xs text-gray-400">Zone classification</p>
        </div>
        <ResponsiveContainer width="100%" height={180}>
          <PieChart>
            <Pie
              data={riskDistribution}
              cx="50%"
              cy="50%"
              innerRadius={50}
              outerRadius={70}
              paddingAngle={2}
              dataKey="value"
            >
              {riskDistribution.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip 
              contentStyle={{ 
                backgroundColor: '#0f1419', 
                border: '1px solid #1e2836',
                borderRadius: '6px',
                fontSize: '12px'
              }}
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="space-y-2 mt-2">
          {riskDistribution.map((item, index) => (
            <div key={index} className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <div 
                  className="w-3 h-3 rounded-full" 
                  style={{ backgroundColor: item.color }}
                />
                <span className="text-gray-300">{item.name}</span>
              </div>
              <span className="text-gray-400">{item.value}%</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
