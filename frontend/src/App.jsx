import React, { createContext, useContext, useState, useEffect, Component } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { authAPI, awsAPI } from './services/api';
import Navbar from './components/Navbar/Navbar';
import Sidebar from './components/Sidebar/Sidebar';
import Login from './pages/Login/Login';
import Register from './pages/Register/Register';
import Dashboard from './pages/Dashboard/Dashboard';
import Buckets from './pages/Buckets/Buckets';
import Files from './pages/Files/Files';
import Logs from './pages/Logs/Logs';
import Profile from './pages/Profile/Profile';
import Settings from './pages/Settings/Settings';

const AuthContext = createContext(null);

export const useAuth = () => useContext(AuthContext);

// ── Page-level Error Boundary ─────────────────────────────────────────────────
// Catches any render/runtime crash inside a page and shows a recovery UI
// instead of a blank white screen.
class PageErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  componentDidCatch(error, info) {
    console.error('[PageErrorBoundary] Caught error:', error, info);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-[60vh] w-full items-center justify-center">
          <div className="glass-panel p-8 rounded-2xl border border-rose-500/20 max-w-md text-center">
            <div className="h-12 w-12 rounded-xl bg-rose-500/10 flex items-center justify-center mx-auto mb-4">
              <svg className="h-6 w-6 text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
              </svg>
            </div>
            <h3 className="text-lg font-bold text-white mb-2">Page Error</h3>
            <p className="text-sm text-slate-400 mb-1">
              {this.state.error?.message || 'An unexpected error occurred rendering this page.'}
            </p>
            <p className="text-xs text-slate-500 mb-6">Check the browser console for details.</p>
            <button
              onClick={() => { this.setState({ hasError: false, error: null }); window.location.href = '/dashboard'; }}
              className="bg-brand-500 hover:bg-brand-600 text-white font-semibold px-5 py-2 rounded-xl text-sm transition"
            >
              Go to Dashboard
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function App() {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem('token'));
  const [loading, setLoading] = useState(true);
  const [awsConnected, setAwsConnected] = useState(false);

  useEffect(() => {
    const initAuth = async () => {
      if (token) {
        try {
          const userData = await authAPI.getMe();
          setUser(userData);
        } catch (err) {
          console.error('Session initialization failed:', err);
          logout();
          setLoading(false);
          return;
        }

        // Set main app loading state to false immediately so components render
        setLoading(false);

        // Fetch AWS Status in the background asynchronously
        try {
          const res = await awsAPI.status();
          setAwsConnected(res.is_connected);
        } catch (err) {
          // 404 = no AWS account connected yet — not an auth error, ignore silently.
          setAwsConnected(false);
        }
      } else {
        setLoading(false);
      }
    };
    initAuth();
  }, [token]);

  const login = (newToken, userData) => {
    localStorage.setItem('token', newToken);
    setUser(userData);
    setToken(newToken);
  };

  const logout = () => {
    localStorage.removeItem('token');
    setUser(null);
    setToken(null);
    setAwsConnected(false);
  };

  const refreshAwsStatus = async () => {
    try {
      const res = await awsAPI.status();
      setAwsConnected(res.is_connected);
    } catch (err) {
      // If status returns 404 it means no AWS account is connected.
      setAwsConnected(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-dark-600 flex items-center justify-center">
        <div className="flex flex-col items-center">
          <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-brand-500 mb-4"></div>
          <p className="text-slate-400 font-medium text-sm">Initializing CloudVault secure session...</p>
        </div>
      </div>
    );
  }

  return (
    <AuthContext.Provider value={{ user, token, awsConnected, login, logout, refreshAwsStatus }}>
      <Router>
        <Routes>
          {/* Public Routes */}
          <Route path="/login" element={!token ? <Login /> : <Navigate to="/dashboard" />} />
          <Route path="/register" element={!token ? <Register /> : <Navigate to="/dashboard" />} />

          {/* Protected Main Layout Routes */}
          <Route
            path="/*"
            element={
              token ? (
                <MainLayout />
              ) : (
                <Navigate to="/login" />
              )
            }
          />
        </Routes>
      </Router>
    </AuthContext.Provider>
  );
}

function MainLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(true);

  return (
    <div className="min-h-screen flex bg-dark-600">
      {/* Sidebar Panel */}
      <Sidebar isOpen={sidebarOpen} setIsOpen={setSidebarOpen} />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Navbar Header */}
        <Navbar toggleSidebar={() => setSidebarOpen(!sidebarOpen)} />

        {/* Dynamic Pages Render */}
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
          <PageErrorBoundary>
            <Routes>
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/buckets" element={<Buckets />} />
              <Route path="/files" element={<Files />} />
              <Route path="/logs" element={<Logs />} />
              <Route path="/profile" element={<Profile />} />
              <Route path="/settings" element={<Settings />} />
              {/* Fallback */}
              <Route path="*" element={<Navigate to="/dashboard" />} />
            </Routes>
          </PageErrorBoundary>
        </main>
      </div>
    </div>
  );
}
