import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("ErrorBoundary caught an uncaught error:", error, errorInfo);
    this.setState({ errorInfo });
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-[#EAF2F8] dark:bg-[#0D3B66] text-[#0D3B66] dark:text-[#EAF2F8] flex items-center justify-center p-6 font-sans">
          <div className="max-w-lg w-full bg-white dark:bg-[#1F4E79] rounded-2xl shadow-xl border border-red-200 dark:border-red-900/50 p-8 text-center space-y-6">
            <div className="w-16 h-16 bg-red-100 dark:bg-red-950/60 rounded-full flex items-center justify-center mx-auto text-red-600 dark:text-red-400">
              <AlertTriangle className="w-8 h-8" />
            </div>
            
            <div>
              <h2 className="text-xl font-black text-red-700 dark:text-red-300">Something went wrong</h2>
              <p className="text-sm text-[#0D3B66]/80 dark:text-[#A4C8E1] mt-2">
                The application encountered an unexpected runtime error.
              </p>
            </div>

            {this.state.error && (
              <div className="p-4 bg-slate-100 dark:bg-[#0D3B66] rounded-xl text-left text-xs font-mono text-red-800 dark:text-red-200 overflow-x-auto border border-slate-200 dark:border-slate-700 max-h-40">
                {this.state.error.toString()}
              </div>
            )}

            <div className="pt-2 flex justify-center space-x-4">
              <button
                onClick={() => window.location.reload()}
                className="px-5 py-2.5 rounded-xl bg-[#0D3B66] dark:bg-[#6FA3D8] hover:opacity-90 text-white dark:text-[#0D3B66] font-bold text-xs shadow-md transition-all flex items-center space-x-2"
              >
                <RefreshCw className="w-4 h-4" />
                <span>Reload Application</span>
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
