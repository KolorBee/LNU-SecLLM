import React from 'react';

function PredictionDisplay({ prediction }) {
  return (
    <div>
      {prediction !== null && <h2>Predicted Price: {prediction}</h2>}
    </div>
  );
}

export default PredictionDisplay;