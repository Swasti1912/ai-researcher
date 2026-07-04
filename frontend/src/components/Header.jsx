import React from 'react';
import { FlaskConical, FileText, Sun, Moon, LogOut } from 'lucide-react';

export default function Header({ mode, onModeChange, theme, onThemeToggle, user, onLogout }) {
  const isDark = theme === 'dark';
  return (
    <header className="hdr">
      <div className="hdr-left">
        <div className="hdr-logo">R</div>
        <h1>AI&nbsp;<span className="accent">Researcher</span></h1>
      </div>

      <div className="seg">
        <button className={`seg-btn ${mode === 'research' ? 'on' : ''}`} onClick={() => onModeChange('research')}>
          <FlaskConical size={15} /> Research
        </button>
        <button className={`seg-btn ${mode === 'paper' ? 'on' : ''}`} onClick={() => onModeChange('paper')}>
          <FileText size={15} /> Paper Q&amp;A
        </button>
      </div>

      <div className="hdr-actions">
        <button
          className="icon-btn"
          onClick={onThemeToggle}
          title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {isDark ? <Sun size={17} /> : <Moon size={17} />}
        </button>

        {user && (
          <div className="hdr-user">
            {user.picture
              ? <img className="hdr-avatar" src={user.picture} alt="" referrerPolicy="no-referrer" />
              : <div className="hdr-avatar hdr-avatar-fb">{(user.name || user.email || '?').slice(0, 1).toUpperCase()}</div>}
            <button className="icon-btn" onClick={onLogout} title={`Log out (${user.email || ''})`}>
              <LogOut size={16} />
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
