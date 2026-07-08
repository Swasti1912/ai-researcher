import React from 'react';
import { Sparkles } from 'lucide-react';
import { loginUrl } from '../services/api';

/**
 * Login gate — shown when auth is enabled and the visitor isn't signed in.
 * Sign-in redirects to the backend OAuth flow, which returns to "/".
 */
export default function Login({ error }) {
  return (
    <div className="login-screen">
      <div className="login-card">
        <div className="login-logo">R</div>
        <div className="login-badge">
          <Sparkles size={12} style={{ verticalAlign: '-1px' }} /> AI Researcher
        </div>
        <h1 className="login-title">Read papers, deeply.</h1>
        <p className="login-sub">
          Sign in to summarize, visualize, and question papers — your library stays
          private to your session.
        </p>

        {error && <div className="login-error">Sign-in failed. Please try again.</div>}

        {/* target=_top so OAuth escapes the HF Spaces iframe (Google blocks
            being rendered inside an iframe → otherwise a 403). */}
        <a className="login-btn" href={loginUrl('google')} target="_top" rel="noopener">
          <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
            <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z"/>
            <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.83.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18z"/>
            <path fill="#FBBC05" d="M3.97 10.72a5.4 5.4 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33z"/>
            <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.47.9 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58z"/>
          </svg>
          Continue with Google
        </a>

        <div className="login-foot">
          LinkedIn sign-in coming soon.
          <br />
          Help &amp; support: <a href="mailto:ai.researcher4@gmail.com">ai.researcher4@gmail.com</a>
        </div>
      </div>
    </div>
  );
}
