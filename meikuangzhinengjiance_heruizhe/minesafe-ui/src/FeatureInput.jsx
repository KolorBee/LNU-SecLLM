import React from 'react';

function FeatureInput({ features, setFeatures }) {
  return (
    <div>
      <input
        type="number"
        placeholder="Size"
        value={features.size}
        onChange={(e) => setFeatures({ ...features, size: e.target.value })}
      />
      <input
        type="number"
        placeholder="Bedrooms"
        value={features.bedrooms}
        onChange={(e) => setFeatures({ ...features, bedrooms: e.target.value })}
      />
    </div>
  );
}

export default FeatureInput;