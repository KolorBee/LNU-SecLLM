import { Activity, AlertTriangle, Wind, TrendingUp } from 'lucide-react';

export function MetricsBar() {
  const metrics = [
    {
      icon: Activity,
      label: 'Total Blocks',
      value: '2,847',
      change: '+12.3%',
      changeType: 'positive' as const,
      color: 'blue'
    },
    {
      icon: AlertTriangle,
      label: 'High Risk Zones',
      value: '17',
      change: '+3',
      changeType: 'negative' as const,
      color: 'orange'
    },
    {
      icon: Wind,
      label: 'Gas Levels',
      value: '24.7 ppm',
      change: '-2.1%',
      changeType: 'positive' as const,
      color: 'blue'
    },
    {
      icon: TrendingUp,
      label: 'Production Output',
      value: '1,247 T',
      change: '+8.4%',
      changeType: 'positive' as const,
      color: 'blue'
    }
  ];

  return (
    <div className="bg-[#0f1419] border-b border-[#1e2836] px-6 py-4">
      <div className="grid grid-cols-4 gap-6">
        {metrics.map((metric, index) => (
          <div 
            key={index}
            className="bg-[#0a0e1a] border border-[#1e2836] rounded-lg p-4 hover:border-[#2a3644] transition-colors"
          >
            <div className="flex items-start justify-between mb-2">
              <div className={`p-2 rounded ${
                metric.color === 'orange' 
                  ? 'bg-orange-500/10 text-orange-500' 
                  : 'bg-blue-500/10 text-blue-400'
              }`}>
                <metric.icon className="w-5 h-5" />
              </div>
              <span className={`text-xs px-2 py-1 rounded ${
                metric.changeType === 'positive' 
                  ? 'bg-green-500/10 text-green-400' 
                  : 'bg-red-500/10 text-red-400'
              }`}>
                {metric.change}
              </span>
            </div>
            <p className="text-2xl font-bold mb-1">{metric.value}</p>
            <p className="text-xs text-gray-400 uppercase tracking-wide">{metric.label}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
