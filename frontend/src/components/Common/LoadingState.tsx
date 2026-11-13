import React from 'react';

interface LoadingStateProps {
  message?: string;
}

export const LoadingState: React.FC<LoadingStateProps> = ({
  message = 'Loading Sentinel-1 SAR observation layers and scientific metrics...',
}) => {
  return (
    <div className="state-container loading-state">
      <div className="spinner"></div>
      <p className="state-message">{message}</p>
    </div>
  );
};

