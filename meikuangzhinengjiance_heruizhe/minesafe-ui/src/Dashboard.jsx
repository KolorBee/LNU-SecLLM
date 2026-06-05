import React, { useState } from 'react';
import FeatureInput from './FeatureInput';
import PredictionDisplay from './PredictionDisplay';

function Dashboard() {
  // STATE: stores feature inputs and prediction
  const [features, setFeatures] = useState({ size: '', bedrooms: '' });
  const [prediction, setPrediction] = useState(null);

  // Function to handle Predict button
  const handlePredict = () => {
    // Dummy formula: prediction = size * 10000 + bedrooms * 5000
    const pred = features.size * 10000 + features.bedrooms * 5000;
    setPrediction(pred);
  };

  return (
    <div>
      <h1>Mini ML Dashboard</h1>
      <FeatureInput features={features} setFeatures={setFeatures} />
      <button onClick={handlePredict}>Predict</button>
      <PredictionDisplay prediction={prediction} />
    </div>
  );
}

export default Dashboard;