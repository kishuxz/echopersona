import { Component, type ErrorInfo, type ReactNode } from 'react'

interface State {
  hasError: boolean
}

export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(_error: Error, _info: ErrorInfo) {
    // intentionally empty — add Sentry or similar here if monitoring is added later
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-bg px-6 text-center">
          <span className="font-fraunces text-xl font-semibold text-text">Something went wrong</span>
          <p className="max-w-sm font-sans text-sm text-textdim">
            An unexpected error occurred. Try reloading the page.
          </p>
          <button
            className="rounded-lg bg-accent px-6 py-2.5 font-sans text-sm font-medium text-white transition-opacity hover:opacity-90"
            onClick={() => { window.location.href = '/' }}
          >
            Reload
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
