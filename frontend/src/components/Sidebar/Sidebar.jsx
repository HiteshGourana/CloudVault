import React from 'react';
import { NavLink } from 'react-router-dom';
import { 
  LayoutDashboard, 
  Layers, 
  FolderOpen, 
  FileClock, 
  Settings, 
  User,
  ChevronLeft,
  Cloud
} from 'lucide-react';

export default function Sidebar({ isOpen, setIsOpen }) {
  const menuItems = [
    { name: 'Dashboard', path: '/dashboard', icon: LayoutDashboard },
    { name: 'S3 Buckets', path: '/buckets', icon: Layers },
    { name: 'Files Explorer', path: '/files', icon: FolderOpen },
    { name: 'Audit Logs', path: '/logs', icon: FileClock },
    { name: 'Settings', path: '/settings', icon: Settings },
    { name: 'My Profile', path: '/profile', icon: User },
  ];

  return (
    <aside
      className={`glass-panel border-r border-slate-800 text-slate-300 transition-all duration-300 flex flex-col h-screen ${
        isOpen ? 'w-64' : 'w-20'
      }`}
    >
      {/* Brand logo & collapse */}
      <div className="h-16 flex items-center justify-between px-4 border-b border-slate-800">
        <div className={`flex items-center gap-2 overflow-hidden ${!isOpen && 'justify-center w-full'}`}>
          <Cloud className="h-7 w-7 text-brand-500 flex-shrink-0" />
          {isOpen && (
            <span className="font-bold text-white tracking-wider text-md whitespace-nowrap">CloudVault</span>
          )}
        </div>
        {isOpen && (
          <button
            onClick={() => setIsOpen(false)}
            className="rounded-lg p-1 hover:bg-dark-400 text-slate-400 hover:text-white transition-colors"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Navigation menu */}
      <nav className="flex-1 py-6 space-y-1 px-3 overflow-y-auto">
        {menuItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.name}
              to={item.path}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-3 rounded-lg text-sm font-semibold transition-all duration-200 ${
                  isActive
                    ? 'bg-brand-600 text-white shadow-lg shadow-brand-500/20'
                    : 'hover:bg-dark-400 hover:text-white text-slate-400'
                } ${!isOpen && 'justify-center'}`
              }
              title={!isOpen ? item.name : ''}
            >
              <Icon className="h-5 w-5 flex-shrink-0" />
              {isOpen && <span>{item.name}</span>}
            </NavLink>
          );
        })}
      </nav>

      {/* Footer / Scope info */}
      <div className="p-4 border-t border-slate-800 text-center">
        {isOpen ? (
          <div className="text-[10px] text-slate-500 font-medium">
            CloudVault Engine v0.1.0
          </div>
        ) : (
          <div className="text-[10px] text-slate-500 font-bold">V0.1</div>
        )}
      </div>
    </aside>
  );
}
