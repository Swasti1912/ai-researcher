import React from 'react';

/**
 * Catches render crashes anywhere below it and shows a friendly reload prompt
 * instead of a blank white page.
 */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error('App crashed:', error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="app-crash">
          <div className="app-crash-card">
            <div className="app-crash-title">Something went wrong</div>
            <div className="app-crash-sub">
              The page hit an unexpected error. Reloading usually fixes it.
            </div>
            <button className="btn btn-p" onClick={() => window.location.reload()}>Reload</button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
