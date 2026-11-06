import { Component, type ErrorInfo, type ReactNode } from "react";

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("UI error", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <main className="app-shell">
          <div className="panel empty-state" role="alert">
            <div>
              <div className="empty-icon">!</div>
              <h2>Something went wrong</h2>
              <p>{this.state.error.message}</p>
              <button
                className="secondary-button"
                type="button"
                onClick={() => window.location.reload()}
              >
                Reload
              </button>
            </div>
          </div>
        </main>
      );
    }
    return this.props.children;
  }
}
