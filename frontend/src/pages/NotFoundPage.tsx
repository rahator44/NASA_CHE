import React from 'react';
import { Link } from '../router/Router';

export const NotFoundPage: React.FC = () => {
  return (
    <div className="page-container not-found-page">
      <div className="card not-found-card">
        <div className="not-found-code">404</div>
        <h2 className="not-found-title">Page Not Found</h2>
        <p className="not-found-desc">
          The requested route does not exist in the Earth Pulse satellite intelligence system.
        </p>
        <div className="not-found-actions">
          <Link href="/" className="btn btn-primary">
            Return to Dashboard
          </Link>
          <Link href="/explorer" className="btn btn-secondary">
            Open Map Explorer
          </Link>
        </div>
      </div>
    </div>
  );
};

