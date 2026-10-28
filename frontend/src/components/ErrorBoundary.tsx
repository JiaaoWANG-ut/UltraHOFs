import { Alert, Button } from 'antd';
import { Component, type ErrorInfo, type ReactNode } from 'react';

interface State {
  error: Error | null;
}

/** Keeps a failing page from blanking the whole application. */
export class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('UI error', error, info.componentStack);
  }

  componentDidUpdate(prev: { resetKey?: string }) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null });
  }

  render() {
    if (this.state.error) {
      return (
        <Alert
          type="error"
          showIcon
          message="页面渲染出错 / Page error"
          description={
            <div>
              <div className="mono" style={{ fontSize: 12 }}>{this.state.error.message}</div>
              <Button size="small" style={{ marginTop: 8 }} onClick={() => this.setState({ error: null })}>
                Retry
              </Button>
            </div>
          }
        />
      );
    }
    return this.props.children;
  }
}
