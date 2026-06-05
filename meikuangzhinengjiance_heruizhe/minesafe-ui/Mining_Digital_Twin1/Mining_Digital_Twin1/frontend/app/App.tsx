import { MetricsBar } from './components/MetricsBar';
import { RiskAnalytics } from './components/RiskAnalytics';
import { MineVisualization3D } from './components/MineVisualization3D';
import { AlertsPanel } from './components/AlertsPanel';
import { ModelPerformance } from './components/ModelPerformance';

export default function App() {
  return (
    <div className="min-h-screen bg-[#0a0e1a] text-gray-100">
      {/* Header */}
      <header className="bg-[#0f1419] border-b border-[#1e2836] px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 bg-gradient-to-br from-orange-500 to-orange-600 rounded flex items-center justify-center">
              <span className="text-lg font-bold">M</span>
            </div>
            <div>
              <h1 className="text-xl font-semibold tracking-tight">Mining Digital Twin</h1>
              <p className="text-xs text-gray-400">AI-Powered Operations Control Center</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-right">
              <p className="text-xs text-gray-400">System Status</p>
              <p className="text-sm font-medium text-green-400">● OPERATIONAL</p>
            </div>
            <div className="text-right">
              <p className="text-xs text-gray-400">Last Updated</p>
              <p className="text-sm font-medium">{new Date().toLocaleTimeString()}</p>
            </div>
          </div>
        </div>
      </header>

      {/* Metrics Bar */}
      <MetricsBar />

      {/* Main Content Grid */}
      <div className="grid grid-cols-12 gap-4 p-4 h-[calc(100vh-240px)]">
        {/* Left Panel - Risk Analytics */}
        <div className="col-span-3 overflow-y-auto">
          <RiskAnalytics />
        </div>

        {/* Center Panel - 3D Visualization */}
        <div className="col-span-6">
          <MineVisualization3D />
        </div>

        {/* Right Panel - Alerts & Sensors */}
        <div className="col-span-3 overflow-y-auto">
          <AlertsPanel />
        </div>
      </div>

      {/* Bottom Section - Model Performance */}
      <div className="p-4 pt-0">
        <ModelPerformance />
      </div>
    </div>
  );
}
