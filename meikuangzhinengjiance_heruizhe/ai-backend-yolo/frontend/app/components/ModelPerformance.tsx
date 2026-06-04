import { Brain, Target, TrendingUp } from 'lucide-react';

export function ModelPerformance() {
  // Confusion matrix data
  const confusionMatrix = [
    [847, 23, 12],
    [18, 756, 31],
    [9, 27, 892]
  ];

  const labels = ['Safe', 'Warning', 'Critical'];

  const metrics = [
    { label: 'Accuracy', value: '98.7%', color: 'text-green-400' },
    { label: 'Precision', value: '97.2%', color: 'text-blue-400' },
    { label: 'Recall', value: '96.8%', color: 'text-blue-400' },
    { label: 'F1-Score', value: '97.0%', color: 'text-blue-400' }
  ];

  const recentPredictions = [
    { time: '14:32:18', zone: 'A-2', predicted: 'Safe', actual: 'Safe', confidence: 99.2 },
    { time: '14:32:15', zone: 'D-4', predicted: 'Critical', actual: 'Critical', confidence: 97.8 },
    { time: '14:32:12', zone: 'B-3', predicted: 'Warning', actual: 'Warning', confidence: 95.4 },
    { time: '14:32:09', zone: 'C-1', predicted: 'Safe', actual: 'Safe', confidence: 98.6 },
    { time: '14:32:06', zone: 'E-5', predicted: 'Warning', actual: 'Safe', confidence: 88.3 }
  ];

  const getMaxValue = () => {
    return Math.max(...confusionMatrix.flat());
  };

  const getCellColor = (value: number) => {
    const max = getMaxValue();
    const intensity = value / max;
    if (intensity > 0.8) return 'bg-blue-600';
    if (intensity > 0.6) return 'bg-blue-700';
    if (intensity > 0.4) return 'bg-blue-800';
    if (intensity > 0.2) return 'bg-blue-900';
    return 'bg-[#1e2836]';
  };

  const getPredictionColor = (predicted: string, actual: string) => {
    if (predicted === actual) return 'text-green-400';
    return 'text-orange-500';
  };

  return (
    <div className="bg-[#0f1419] border border-[#1e2836] rounded-lg p-6">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-500/10 rounded">
            <Brain className="w-5 h-5 text-blue-400" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-gray-100">AI Model Performance</h3>
            <p className="text-xs text-gray-400">Neural Network - Last updated 2 min ago</p>
          </div>
        </div>
        <div className="flex items-center gap-6">
          {metrics.map((metric, index) => (
            <div key={index} className="text-center">
              <p className="text-xs text-gray-400 mb-1">{metric.label}</p>
              <p className={`text-lg font-bold ${metric.color}`}>{metric.value}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Confusion Matrix */}
        <div className="col-span-1">
          <div className="flex items-center gap-2 mb-4">
            <Target className="w-4 h-4 text-gray-400" />
            <h4 className="text-sm font-semibold text-gray-100">Confusion Matrix</h4>
          </div>
          <div className="bg-[#0a0e1a] border border-[#1e2836] rounded-lg p-4">
            <div className="grid grid-cols-4 gap-2">
              {/* Header row */}
              <div className="text-xs text-gray-400"></div>
              {labels.map((label, i) => (
                <div key={i} className="text-xs text-gray-400 text-center font-medium">
                  {label}
                </div>
              ))}
              
              {/* Data rows */}
              {confusionMatrix.map((row, i) => (
                <div key={`row-${i}`} className="contents">
                  <div className="text-xs text-gray-400 flex items-center font-medium">
                    {labels[i]}
                  </div>
                  {row.map((value, j) => (
                    <div
                      key={`cell-${i}-${j}`}
                      className={`${getCellColor(value)} rounded flex items-center justify-center h-16 transition-colors hover:brightness-110`}
                    >
                      <span className="text-sm font-bold text-gray-100">{value}</span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between mt-4 text-xs text-gray-400">
              <span>Predicted</span>
              <span>Actual →</span>
            </div>
          </div>
        </div>

        {/* Recent Predictions */}
        <div className="col-span-2">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="w-4 h-4 text-gray-400" />
            <h4 className="text-sm font-semibold text-gray-100">Recent Predictions</h4>
            <span className="text-xs text-green-400 ml-auto">● Live Stream</span>
          </div>
          <div className="bg-[#0a0e1a] border border-[#1e2836] rounded-lg overflow-hidden">
            <table className="w-full">
              <thead className="bg-[#0f1419] border-b border-[#1e2836]">
                <tr>
                  <th className="text-left text-xs font-medium text-gray-400 px-4 py-3">Time</th>
                  <th className="text-left text-xs font-medium text-gray-400 px-4 py-3">Zone</th>
                  <th className="text-left text-xs font-medium text-gray-400 px-4 py-3">Predicted</th>
                  <th className="text-left text-xs font-medium text-gray-400 px-4 py-3">Actual</th>
                  <th className="text-left text-xs font-medium text-gray-400 px-4 py-3">Confidence</th>
                  <th className="text-left text-xs font-medium text-gray-400 px-4 py-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {recentPredictions.map((pred, index) => (
                  <tr 
                    key={index} 
                    className="border-b border-[#1e2836] hover:bg-[#1e2836]/30 transition-colors"
                  >
                    <td className="text-xs text-gray-300 px-4 py-3 font-mono">{pred.time}</td>
                    <td className="text-xs text-gray-300 px-4 py-3 font-medium">{pred.zone}</td>
                    <td className="text-xs px-4 py-3">
                      <span className={`px-2 py-1 rounded ${
                        pred.predicted === 'Safe' ? 'bg-green-500/10 text-green-400' :
                        pred.predicted === 'Warning' ? 'bg-orange-500/10 text-orange-400' :
                        'bg-red-500/10 text-red-400'
                      }`}>
                        {pred.predicted}
                      </span>
                    </td>
                    <td className="text-xs px-4 py-3">
                      <span className={`px-2 py-1 rounded ${
                        pred.actual === 'Safe' ? 'bg-green-500/10 text-green-400' :
                        pred.actual === 'Warning' ? 'bg-orange-500/10 text-orange-400' :
                        'bg-red-500/10 text-red-400'
                      }`}>
                        {pred.actual}
                      </span>
                    </td>
                    <td className="text-xs text-gray-300 px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-1.5 bg-[#1e2836] rounded-full overflow-hidden">
                          <div 
                            className={`h-full ${pred.confidence > 95 ? 'bg-green-500' : 'bg-orange-500'}`}
                            style={{ width: `${pred.confidence}%` }}
                          />
                        </div>
                        <span className="text-xs w-12">{pred.confidence}%</span>
                      </div>
                    </td>
                    <td className="text-xs px-4 py-3">
                      <span className={getPredictionColor(pred.predicted, pred.actual)}>
                        {pred.predicted === pred.actual ? '✓' : '✗'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}