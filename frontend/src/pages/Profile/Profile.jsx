import React from 'react';
import { useAuth } from '../../App';
import { User, ShieldCheck, Mail, ShieldAlert } from 'lucide-react';

export default function Profile() {
  const { user, awsConnected } = useAuth();

  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
  };

  return (
    <div className="space-y-6 max-w-2xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
          <User className="h-6 w-6 text-slate-400" />
          <span>My Profile</span>
        </h1>
        <p className="text-slate-400 text-sm mt-1">Manage your user profile and security roles.</p>
      </div>

      {/* Profile Overview Card */}
      <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-6 relative overflow-hidden">
        <div className="flex flex-col sm:flex-row items-center gap-4">
          <div className="h-16 w-16 rounded-full bg-brand-600 flex items-center justify-center text-white text-2xl font-bold border-2 border-slate-800">
            {user?.email ? user.email[0].toUpperCase() : 'U'}
          </div>
          <div className="text-center sm:text-left">
            <h3 className="text-lg font-bold text-white">{user?.email || 'N/A'}</h3>
            <span className="inline-block mt-1 bg-brand-500/10 text-brand-400 border border-brand-500/20 text-xs font-semibold px-2.5 py-0.5 rounded-full">
              System Owner / Creator
            </span>
          </div>
        </div>

        <div className="border-t border-slate-800/80 pt-6 space-y-4 text-sm text-slate-300">
          <div className="flex justify-between items-center rounded-xl bg-dark-500 p-4 border border-slate-800/40">
            <div className="flex items-center gap-2">
              <Mail className="h-4.5 w-4.5 text-slate-400" />
              <span className="text-slate-400">Account Email</span>
            </div>
            <span className="font-semibold text-white">{user?.email}</span>
          </div>

          <div className="flex justify-between items-center rounded-xl bg-dark-500 p-4 border border-slate-800/40">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-4.5 w-4.5 text-slate-400" />
              <span className="text-slate-400">System Role</span>
            </div>
            <span className="font-semibold text-white capitalize">{user?.role || 'owner'}</span>
          </div>

          <div className="flex justify-between items-center rounded-xl bg-dark-500 p-4 border border-slate-800/40">
            <div className="flex items-center gap-2">
              {awsConnected ? (
                <ShieldCheck className="h-4.5 w-4.5 text-emerald-400" />
              ) : (
                <ShieldAlert className="h-4.5 w-4.5 text-slate-400" />
              )}
              <span className="text-slate-400">AWS Credentials State</span>
            </div>
            {awsConnected ? (
              <span className="font-semibold text-emerald-400 bg-emerald-500/10 px-2.5 py-0.5 rounded-full border border-emerald-500/20 text-xs">Connected</span>
            ) : (
              <span className="font-semibold text-slate-400 bg-slate-500/10 px-2.5 py-0.5 rounded-full border border-slate-500/20 text-xs">Not Linked</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
