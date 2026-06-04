import { AlertTriangle, Activity, ThermometerSun, Wind, Zap, Droplets } from 'lucide-react';
import { useEffect, useState } from 'react';

interface Alert {
  id: number;
  type: 'critical' | 'warning' | 'info';
  message: string;
  zone: string;
  time: string;
}

interface SensorReading {
  id: string;
  name: string;
  value: string;
  status: 'normal' | 'warning' | 'critical';
  icon: any;
  trend: number;
}

export function AlertsPanel() {
  const [alerts, setAlerts] = useState<Alert[]>([
    { id: 1, type: 'critical', message: 'Gas concentration exceeding threshold', zone: 'Zone D-4', time: '2 min ago' },
    { id: 2, type: 'warning', message: 'Temperature spike detected', zone: 'Zone B-2', time: '5 min ago' },
    { id: 3, type: 'warning', message: 'Structural stress increasing', zone: 'Zone A-1', time: '8 min ago' },
    { id: 4, type: 'info', message: 'Maintenance scheduled', zone: 'Zone C-3', time: '15 min ago' },
    { id: 5, type: 'info', message: 'Sensor calibration complete', zone: 'Zone E-5', time: '23 min ago' }
  ]);

  const [sensors, setSensors] = useState<SensorReading[]>([
    { id: 'temp', name: 'Temperature', value: '28.4°C', status: 'normal', icon: ThermometerSun, trend: -1.2 },
    { id: 'gas', name: 'Gas Level', value: '24.7 ppm', status: 'warning', icon: Wind, trend: 2.3 },
    { id: 'humidity', name: 'Humidity', value: '67%', status: 'normal', icon: Droplets, trend: 0.5 },
    { id: 'vibration', name: 'Vibration', value: '0.23 mm/s', status: 'normal', icon: Activity, trend: -0.1 },
    { id: 'power', name: 'Power Draw', value: '847 kW', status: 'normal', icon: Zap, trend: 12.4 }
  ]);

  // Simulate real-time updates
  useEffect(() => {
    const interval = setInterval(() => {
      setSensors(prev => prev.map(sensor => ({
        ...sensor,
        value: updateSensorValue(sensor.id, sensor.value)
      })));
    }, 3000);

    return () => clearInterval(interval);
  }, []);

  const updateSensorValue = (id: string, currentValue: string) => {
    const randomChange = (Math.random() - 0.5) * 0.2;
    switch (id) {
      case 'temp':
        const temp = parseFloat(currentValue) + randomChange;
        return `${temp.toFixed(1)}°C`;
      case 'gas':
        const gas = parseFloat(currentValue) + randomChange * 2;
        return `${gas.toFixed(1)} ppm`;
      case 'humidity':
        const hum = parseFloat(currentValue) + randomChange;
        return `${Math.round(hum)}%`;
      case 'vibration':
        const vib = parseFloat(currentValue) + randomChange * 0.1;
        return `${vib.toFixed(2)} mm/s`;
      case 'power':
        const pow = parseFloat(currentValue) + randomChange * 10;
        return `${Math.round(pow)} kW`;
      default:
        return currentValue;
    }
  };

  const getAlertColor = (type: Alert['type']) => {
    switch (type) {
      case 'critical':
        return 'border-red-500 bg-red-500/10';
      case 'warning':
        return 'border-orange-500 bg-orange-500/10';
      case 'info':
        return 'border-blue-500 bg-blue-500/10';
    }
  };

  const getAlertIcon = (type: Alert['type']) => {
    switch (type) {
      case 'critical':
        return <AlertTriangle className="w-4 h-4 text-red-500" />;
      case 'warning':
        return <AlertTriangle className="w-4 h-4 text-orange-500" />;
      case 'info':
        return <Activity className="w-4 h-4 text-blue-400" />;
    }
  };

  const getSensorStatusColor = (status: SensorReading['status']) => {
    switch (status) {
      case 'critical':
        return 'text-red-500';
      case 'warning':
        return 'text-orange-500';
      case 'normal':
        return 'text-green-400';
    }
  };

  return (
    <div className="space-y-4">
      {/* Active Alerts */}
      <div className="bg-[#0f1419] border border-[#1e2836] rounded-lg p-4">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-sm font-semibold text-gray-100">Active Alerts</h3>
            <p className="text-xs text-gray-400">{alerts.length} notifications</p>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse"></div>
            <span className="text-xs text-red-500">LIVE</span>
          </div>
        </div>
        <div className="space-y-2 max-h-[280px] overflow-y-auto">
          {alerts.map(alert => (
            <div
              key={alert.id}
              className={`border-l-2 ${getAlertColor(alert.type)} rounded p-3 hover:bg-opacity-20 transition-colors`}
            >
              <div className="flex items-start gap-2">
                {getAlertIcon(alert.type)}
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-gray-100 mb-1">{alert.message}</p>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-gray-400">{alert.zone}</span>
                    <span className="text-gray-500">{alert.time}</span>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Live Sensor Monitoring */}
      <div className="bg-[#0f1419] border border-[#1e2836] rounded-lg p-4">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-sm font-semibold text-gray-100">Live Sensors</h3>
            <p className="text-xs text-gray-400">Real-time monitoring</p>
          </div>
          <div className="text-xs text-green-400">● All Online</div>
        </div>
        <div className="space-y-3">
          {sensors.map(sensor => (
            <div
              key={sensor.id}
              className="bg-[#0a0e1a] border border-[#1e2836] rounded p-3 hover:border-[#2a3644] transition-colors"
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 bg-blue-500/10 rounded">
                    <sensor.icon className="w-4 h-4 text-blue-400" />
                  </div>
                  <span className="text-xs text-gray-300">{sensor.name}</span>
                </div>
                <span className={`text-xs ${getSensorStatusColor(sensor.status)}`}>
                  ●
                </span>
              </div>
              <div className="flex items-end justify-between">
                <span className="text-lg font-bold text-gray-100">{sensor.value}</span>
                <span className={`text-xs ${sensor.trend > 0 ? 'text-orange-500' : 'text-green-400'}`}>
                  {sensor.trend > 0 ? '↑' : '↓'} {Math.abs(sensor.trend).toFixed(1)}%
                </span>
              </div>
              {/* Mini progress bar */}
              <div className="mt-2 h-1 bg-[#1e2836] rounded-full overflow-hidden">
                <div 
                  className={`h-full ${
                    sensor.status === 'critical' ? 'bg-red-500' :
                    sensor.status === 'warning' ? 'bg-orange-500' :
                    'bg-blue-500'
                  }`}
                  style={{ width: `${Math.random() * 40 + 40}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* System Health */}
      <div className="bg-[#0f1419] border border-[#1e2836] rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-100 mb-3">System Health</h3>
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-400">AI Model</span>
            <span className="text-green-400">98.7%</span>
          </div>
          <div className="h-1.5 bg-[#1e2836] rounded-full overflow-hidden">
            <div className="h-full bg-green-500" style={{ width: '98.7%' }} />
          </div>

          <div className="flex items-center justify-between text-xs mt-3">
            <span className="text-gray-400">Network</span>
            <span className="text-green-400">100%</span>
          </div>
          <div className="h-1.5 bg-[#1e2836] rounded-full overflow-hidden">
            <div className="h-full bg-green-500" style={{ width: '100%' }} />
          </div>

          <div className="flex items-center justify-between text-xs mt-3">
            <span className="text-gray-400">Sensors</span>
            <span className="text-orange-500">92.3%</span>
          </div>
          <div className="h-1.5 bg-[#1e2836] rounded-full overflow-hidden">
            <div className="h-full bg-orange-500" style={{ width: '92.3%' }} />
          </div>
        </div>
      </div>
    </div>
  );
}
