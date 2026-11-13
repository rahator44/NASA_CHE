import React from 'react';

interface ErrorStateProps {
  error: string;
  onRetry?: () => void;
}

export const ErrorState: React.FC<ErrorStateProps> = ({ error, onRetry }) => {
  return (
    <div className="state-container error-state">
      <div className="error-icon">⚠️</div>
      <h3 className="error-title">Data Loading Error</h3>
      <p className="error-message">{error}</p>
      {onRetry && (
        <button className="retry-btn" onClick={onRetry}>
          Retry Connection
        </button>
      )}
    </div>
  );
};

