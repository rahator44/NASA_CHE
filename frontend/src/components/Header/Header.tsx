import React, { useState } from 'react';
import { CampaignOption } from '../../api/types';
import { Link, useRouter } from '../../router/Router';

interface HeaderProps {
  selectedRunId: string;
  campaigns: CampaignOption[];
  catalogueError: string | null;
  onSelectRun: (id: string) => void;
  isLoading: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  selectedRunId,
  campaigns,
  catalogueError,
  onSelectRun,
  isLoading,
}) => {
  const { currentPath } = useRouter();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const navItems = [
    { to: '/', label: 'Dashboard', icon: '📊' },
    { to: '/explorer', label: 'Map Explorer', icon: '🗺️' },
    { to: '/comparison', label: 'Flood Comparison', icon: '⚖️' },
    { to: '/explainable-ai', label: 'Explainable AI', icon: '🧠' },
    { to: '/science', label: 'Science & Data', icon: '🔬' },
    { to: '/new-analysis', label: 'New Analysis', icon: '📡' },
  ];

  return (
    <header className="app-header">
      <div className="header-top-row">
        {/* Brand / Logo */}
        <Link to="/" className="header-branding" onClick={() => setMobileMenuOpen(false)}>
          <div className="logo-badge">
            <span className="logo-icon">🛰️</span>
          </div>
          <div className="brand-text">
            <h1 className="header-title">Earth Pulse</h1>
            <p className="header-subtitle">
              Satellite Radar Hydrology & Explainable AI
            </p>
          </div>
        </Link>

        {/* Global Run Selector & Status */}
        <div className="header-right-controls">
          <div className="selector-wrapper">
            <label htmlFor="run-select" className="selector-label">
              Active Campaign:
            </label>
            <select
              id="run-select"
              className="run-select"
              value={selectedRunId}
              onChange={(e) => onSelectRun(e.target.value)}
              aria-busy={isLoading}
              title={catalogueError || 'Select a published analysis. Archived Jamuna campaigns are labelled.'}
            >
              {campaigns.map((run) => (
                <option key={run.id} value={run.id}>
                  {run.label} ({run.dateRange})
                </option>
              ))}
            </select>
          </div>

          <div className="status-indicator" title="Safe execution mode: compute endpoints protected, serving genuine precomputed satellite products">
            <span className="status-dot live"></span>
            <span className="status-text">Public Demo Mode</span>
          </div>

          {/* Mobile hamburger menu toggle */}
          <button
            className="mobile-nav-toggle"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-label="Toggle navigation menu"
            aria-expanded={mobileMenuOpen}
          >
            {mobileMenuOpen ? '✕' : '☰'}
          </button>
        </div>
      </div>

      {/* Main Navigation Bar */}
      <nav className={`header-nav-bar ${mobileMenuOpen ? 'mobile-open' : ''}`}>
        <ul className="nav-list">
          {navItems.map((item) => {
            const isActive = currentPath === item.to;
            return (
              <li key={item.to} className="nav-item">
                <Link
                  to={item.to}
                  className={`nav-link ${isActive ? 'active' : ''}`}
                  onClick={() => setMobileMenuOpen(false)}
                >
                  <span className="nav-icon">{item.icon}</span>
                  <span className="nav-label">{item.label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </header>
  );
};
