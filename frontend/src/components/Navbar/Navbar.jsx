import React, { useState } from 'react';
import { useAuth } from '../../App';
import { useNavigate, Link } from 'react-router-dom';
import { Menu, Bell, User, LogOut, ShieldCheck, ShieldAlert, Settings, Cloud } from 'lucide-react';

export default function Navbar({ toggleSidebar }) {
  const { user, logout, awsConnected, refreshAwsStatus } = useAuth();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await refreshAwsStatus();
    setRefreshing(false);
  };

  return (
    <header className="glass-panel sticky top-0 z-30 flex h-16 w-full items-center justify-between px-4 sm:px-6">
      {/* Sidebar toggle button */}
      <div className="flex items-center gap-4">
        <button
          onClick={toggleSidebar}
          className="rounded-lg p-2 text-slate-400 hover:bg-dark-400 hover:text-white transition-colors duration-150"
        >
          <Menu className="h-5 w-5" />
        </button>
        <div className="flex items-center gap-2">
          <Cloud className="h-6 w-6 text-brand-500" />
          <span className="hidden sm:inline font-bold text-lg tracking-wide text-white">CloudVault</span>
        </div>
      </div>

      {/* Right-aligned actions */}
      <div className="flex items-center gap-4">
        {/* AWS Connection Badge */}
        <div className="flex items-center">
          {awsConnected ? (
            <div className="flex items-center gap-2 rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-400 border border-emerald-500/20">
              <ShieldCheck className="h-3.5 w-3.5" />
              <span className="hidden md:inline">AWS Linked</span>
            </div>
          ) : (
            <Link
              to="/settings"
              className="flex items-center gap-2 rounded-full bg-rose-500/10 px-3 py-1 text-xs font-semibold text-rose-400 border border-rose-500/20 hover:bg-rose-500/20 transition-all"
            >
              <ShieldAlert className="h-3.5 w-3.5" />
              <span>Link AWS</span>
            </Link>
          )}
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className={`ml-2 rounded-full p-1.5 text-slate-400 hover:bg-dark-400 hover:text-white transition-colors ${refreshing ? 'animate-spin' : ''}`}
            title="Refresh AWS connection status"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 7.89M9 11l3 3L22 4" />
            </svg>
          </button>
        </div>

        {/* Notifications Icon (Placeholder placeholder, can link to Activity log) */}
        <Link
          to="/logs"
          className="rounded-lg p-2 text-slate-400 hover:bg-dark-400 hover:text-white transition-colors duration-150 relative"
        >
          <Bell className="h-5 w-5" />
          <span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-brand-500"></span>
        </Link>

        {/* User Account Settings Dropdown */}
        <div className="relative">
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center gap-2 focus:outline-none"
          >
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-600 text-white font-bold text-sm">
              {user?.email ? user.email[0].toUpperCase() : 'U'}
            </div>
            <div className="hidden lg:flex flex-col text-left">
              <span className="text-xs text-slate-400">Owner</span>
              <span className="text-sm font-semibold text-white max-w-[120px] truncate">{user?.email}</span>
            </div>
          </button>

          {dropdownOpen && (
            <>
              <div
                className="fixed inset-0 z-30"
                onClick={() => setDropdownOpen(false)}
              ></div>
              <div className="absolute right-0 mt-2 w-48 rounded-lg bg-dark-400 border border-slate-800 shadow-xl py-1 z-40 animate-in fade-in slide-in-from-top-2 duration-150">
                <Link
                  to="/profile"
                  onClick={() => setDropdownOpen(false)}
                  className="flex items-center gap-2 px-4 py-2 text-sm text-slate-300 hover:bg-dark-300 hover:text-white"
                >
                  <User className="h-4 w-4" />
                  <span>My Profile</span>
                </Link>
                <Link
                  to="/settings"
                  onClick={() => setDropdownOpen(false)}
                  className="flex items-center gap-2 px-4 py-2 text-sm text-slate-300 hover:bg-dark-300 hover:text-white"
                >
                  <Settings className="h-4 w-4" />
                  <span>Settings</span>
                </Link>
                <hr className="border-slate-800 my-1" />
                <button
                  onClick={handleLogout}
                  className="flex w-full items-center gap-2 px-4 py-2 text-sm text-rose-400 hover:bg-dark-300 hover:text-rose-300"
                >
                  <LogOut className="h-4 w-4" />
                  <span>Sign Out</span>
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
