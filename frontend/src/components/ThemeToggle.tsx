import { useEffect, useRef, useState } from 'react';

type Theme = 'light' | 'dark';

const STORAGE_KEY = 'studysync-theme';
const THEME_FADE_MS = 600; // matches .theme-transition in index.css

function initialTheme(): Theme {
  // index.html sets data-theme before first paint; reuse it so React agrees.
  const attr = document.documentElement.getAttribute('data-theme');
  if (attr === 'light' || attr === 'dark') return attr;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const fadeTimer = useRef<number | undefined>(undefined);

  function changeTheme(next: Theme) {
    if (next === theme) return;
    const root = document.documentElement;
    root.classList.add('theme-transition');
    window.clearTimeout(fadeTimer.current);
    fadeTimer.current = window.setTimeout(
      () => root.classList.remove('theme-transition'),
      THEME_FADE_MS,
    );
    setTheme(next);
  }

  useEffect(() => () => window.clearTimeout(fadeTimer.current), []);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // Storage unavailable (private mode) — theme still applies for this session
    }
  }, [theme]);

  return (
    <div className="theme-toggle" role="group" aria-label="Colour theme">
      <button
        className={`theme-toggle-btn ${theme === 'light' ? 'active' : ''}`}
        aria-pressed={theme === 'light'}
        onClick={() => changeTheme('light')}
        title="Light mode"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
        </svg>
        <span>Light</span>
      </button>
      <button
        className={`theme-toggle-btn ${theme === 'dark' ? 'active' : ''}`}
        aria-pressed={theme === 'dark'}
        onClick={() => changeTheme('dark')}
        title="Dark mode"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
        <span>Dark</span>
      </button>
    </div>
  );
}
