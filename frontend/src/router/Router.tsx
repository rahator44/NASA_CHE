import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { mergeNavigationTarget } from '../state/analysisSelection';

export type AppRoute = '/' | '/explorer' | '/comparison' | '/explainable-ai' | '/science' | '/new-analysis';

interface RouterContextType {
  currentPath: string;
  queryParams: URLSearchParams;
  navigate: (to: string) => void;
  setQueryParam: (key: string, value: string) => void;
  replaceQueryParam: (key: string, value: string) => void;
}

const RouterContext = createContext<RouterContextType | null>(null);

const rawBase =
  (typeof import.meta !== 'undefined' && (import.meta as any)?.env?.BASE_URL) ||
  '/';
export const BASE_PATH = rawBase.replace(/\/+$/, '');

export function stripBasePath(path: string): string {
  if (BASE_PATH && (path === BASE_PATH || path.startsWith(`${BASE_PATH}/`))) {
    const stripped = path.slice(BASE_PATH.length);
    return stripped || '/';
  }
  return path;
}

export function withBasePath(path: string): string {
  if (!BASE_PATH || path.startsWith(BASE_PATH) || /^https?:\/\//i.test(path)) {
    return path;
  }
  const clean = path.startsWith('/') ? path : `/${path}`;
  return `${BASE_PATH}${clean}`;
}

export function normalizePath(path: string): string {
  const stripped = stripBasePath(path);
  // Strip trailing slashes, keep root
  if (stripped.length > 1 && stripped.endsWith('/')) {
    return stripped.slice(0, -1);
  }
  return stripped || '/';
}

export const RouterProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [currentPath, setCurrentPath] = useState<string>(() => {
    if (typeof window === 'undefined') return '/';
    const p = normalizePath(window.location.pathname);
    // Backward compatibility: ?view=xai routes to /explainable-ai
    const params = new URLSearchParams(window.location.search);
    if (params.get('view') === 'xai') {
      return '/explainable-ai';
    }
    return p;
  });

  const [queryParams, setQueryParams] = useState<URLSearchParams>(() => {
    if (typeof window === 'undefined') return new URLSearchParams();
    return new URLSearchParams(window.location.search);
  });

  useEffect(() => {
    const handlePopState = () => {
      setCurrentPath(normalizePath(window.location.pathname));
      setQueryParams(new URLSearchParams(window.location.search));
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const navigate = useCallback((to: string) => {
    const dest = mergeNavigationTarget(to, window.location.search);
    const url = new URL(dest, window.location.origin);
    const inAppPath = normalizePath(url.pathname);
    const newSearch = url.search;
    const historyPath = withBasePath(inAppPath);

    if (window.location.pathname !== historyPath || window.location.search !== newSearch) {
      window.history.pushState(null, '', `${historyPath}${newSearch}`);
    }
    setCurrentPath(inAppPath);
    setQueryParams(new URLSearchParams(newSearch));
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  const writeQueryParam = useCallback((key: string, value: string, mode: 'push' | 'replace') => {
    const params = new URLSearchParams(window.location.search);
    if (params.get(key) === value) {
      setQueryParams(params);
      return;
    }
    params.set(key, value);
    const newUrl = `${window.location.pathname}?${params.toString()}`;
    if (mode === 'replace') {
      window.history.replaceState(null, '', newUrl);
    } else {
      window.history.pushState(null, '', newUrl);
    }
    setQueryParams(params);
  }, []);

  const setQueryParam = useCallback((key: string, value: string) => {
    writeQueryParam(key, value, 'push');
  }, [writeQueryParam]);

  const replaceQueryParam = useCallback((key: string, value: string) => {
    writeQueryParam(key, value, 'replace');
  }, [writeQueryParam]);

  return (
    <RouterContext.Provider value={{ currentPath, queryParams, navigate, setQueryParam, replaceQueryParam }}>
      {children}
    </RouterContext.Provider>
  );
};

export function useRouter(): RouterContextType {
  const ctx = useContext(RouterContext);
  if (!ctx) {
    throw new Error('useRouter must be used within a RouterProvider');
  }
  return ctx;
}

interface LinkProps extends React.AnchorHTMLAttributes<HTMLAnchorElement> {
  to?: string;
  href?: string;
  className?: string;
  activeClassName?: string;
}

export const Link: React.FC<LinkProps> = ({
  to,
  href,
  className = '',
  activeClassName = 'active',
  children,
  onClick,
  ...rest
}) => {
  const { currentPath, navigate } = useRouter();
  const dest = to || href || '/';
  const inAppTarget = normalizePath(dest.split('?')[0]);
  const isActive = currentPath === inAppTarget;
  const hrefPath = withBasePath(dest);

  const handleClick = (e: React.MouseEvent<HTMLAnchorElement>) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) {
      return; // Allow open in new tab
    }
    e.preventDefault();
    navigate(dest);
    if (onClick) onClick(e);
  };

  const combinedClass = [className, isActive ? activeClassName : ''].filter(Boolean).join(' ');

  return (
    <a href={hrefPath} className={combinedClass} onClick={handleClick} {...rest}>
      {children}
    </a>
  );
};
