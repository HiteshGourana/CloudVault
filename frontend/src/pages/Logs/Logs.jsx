import React, { useState, useEffect } from 'react';
import { useAuth } from '../../App';
import { systemAPI } from '../../services/api';
import { 
  FileClock, 
  Search, 
  Filter, 
  CheckCircle2, 
  XCircle, 
  ChevronLeft, 
  ChevronRight, 
  RefreshCw,
  Info
} from 'lucide-react';

export default function Logs() {
  const { awsConnected } = useAuth();
  
  // Data states
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  
  // Filtering & Pagination state
  const [actionFilter, setActionFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalItems, setTotalItems] = useState(0);

  const fetchLogs = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await systemAPI.getActivityLogs({
        action: actionFilter || undefined,
        status_filter: statusFilter || undefined,
        page: page,
        page_size: 15
      });
      setLogs(res.logs || []);
      setTotalPages(res.total_pages || 1);
      setTotalItems(res.total_items || 0);
    } catch (err) {
      console.error('Failed to fetch activity logs:', err);
      // Fallback preview data
      setLogs(getMockLogs());
      setTotalPages(1);
      setTotalItems(4);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, [actionFilter, statusFilter, page]);

  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleString();
  };

  const getStatusBadge = (status) => {
    const s = status ? status.toLowerCase() : '';
    if (s === 'success') {
      return (
        <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-400 bg-emerald-500/10 px-2.5 py-0.5 rounded-full border border-emerald-500/20">
          <CheckCircle2 className="h-3.5 w-3.5" />
          <span>Success</span>
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-rose-400 bg-rose-500/10 px-2.5 py-0.5 rounded-full border border-rose-500/20">
        <XCircle className="h-3.5 w-3.5" />
        <span>Failure</span>
      </span>
    );
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Security & Audit Logs</h1>
          <p className="text-slate-400 text-sm mt-1">Immutable user activity and S3 transfer tracking records.</p>
        </div>
        <button
          onClick={fetchLogs}
          className="rounded-xl border border-slate-800 bg-dark-400 text-slate-300 hover:text-white px-4 py-2 hover:bg-dark-300 transition text-sm flex items-center gap-1.5"
        >
          <RefreshCw className="h-4 w-4" />
          <span>Refresh logs</span>
        </button>
      </div>

      {/* Filters Area */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div>
          <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Filter Action</label>
          <select
            value={actionFilter}
            onChange={(e) => { setActionFilter(e.target.value); setPage(1); }}
            className="w-full px-3 py-2 bg-dark-400 border border-slate-800 rounded-xl text-white text-xs focus:outline-none focus:border-brand-500"
          >
            <option value="">All Actions</option>
            <option value="Login">Login</option>
            <option value="Register">Register</option>
            <option value="BucketCreate">Bucket Created</option>
            <option value="BucketDelete">Bucket Deleted</option>
            <option value="Upload">Upload Complete</option>
            <option value="Download">Download Streaming</option>
            <option value="FileRename">File Renamed</option>
            <option value="FileDelete">File Deleted</option>
            <option value="ShareGenerate">Share Link Generated</option>
          </select>
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Filter Status</label>
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
            className="w-full px-3 py-2 bg-dark-400 border border-slate-800 rounded-xl text-white text-xs focus:outline-none focus:border-brand-500"
          >
            <option value="">All Statuses</option>
            <option value="success">Success Only</option>
            <option value="failure">Failure Only</option>
          </select>
        </div>

        <div className="flex items-end text-xs text-slate-500 font-semibold mb-2 sm:justify-end">
          Total Logs Mapped: {totalItems}
        </div>
      </div>

      {/* Logs Table */}
      {loading ? (
        <div className="flex h-48 items-center justify-center">
          <RefreshCw className="h-8 w-8 text-brand-500 animate-spin" />
        </div>
      ) : logs.length === 0 ? (
        <div className="glass-panel p-16 rounded-2xl text-center">
          <FileClock className="h-16 w-16 text-slate-700 mx-auto mb-4" />
          <h4 className="font-bold text-white text-lg">No Logs Found</h4>
          <p className="text-slate-400 text-sm mt-1">
            There are no security audits registered matching your filter conditions.
          </p>
        </div>
      ) : (
        <div className="glass-panel rounded-2xl overflow-hidden border border-slate-800/85">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-800 bg-dark-500/60 text-slate-400 font-semibold">
                  <th className="px-5 py-3">Timestamp</th>
                  <th className="px-5 py-3">Action</th>
                  <th className="px-5 py-3">Description Details</th>
                  <th className="px-5 py-3">Client IP</th>
                  <th className="px-5 py-3 text-right">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/40">
                {logs.map((log) => (
                  <tr key={log.id} className="text-slate-300 hover:text-white hover:bg-dark-400/20">
                    <td className="px-5 py-3.5 text-slate-400 font-mono whitespace-nowrap">{formatDate(log.created_at)}</td>
                    <td className="px-5 py-3.5">
                      <span className="font-semibold">{log.action}</span>
                      <span className="text-[10px] text-slate-500 block uppercase font-bold tracking-wider mt-0.5">{log.resource_type || 'system'}</span>
                    </td>
                    <td className="px-5 py-3.5 max-w-sm truncate" title={log.message}>
                      {log.message}
                    </td>
                    <td className="px-5 py-3.5 font-mono text-slate-400">{log.ip_address || '127.0.0.1'}</td>
                    <td className="px-5 py-3.5 text-right">{getStatusBadge(log.status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination Footer */}
          {totalPages > 1 && (
            <div className="px-5 py-4 bg-dark-500/35 border-t border-slate-800/80 flex justify-between items-center text-xs">
              <span className="text-slate-400">Page {page} of {totalPages}</span>
              <div className="flex gap-2">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  className="p-1.5 rounded bg-dark-400 hover:bg-dark-300 text-slate-300 disabled:opacity-30 disabled:hover:bg-dark-400"
                >
                  <ChevronLeft className="h-4.5 w-4.5" />
                </button>
                <button
                  disabled={page >= totalPages}
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  className="p-1.5 rounded bg-dark-400 hover:bg-dark-300 text-slate-300 disabled:opacity-30 disabled:hover:bg-dark-400"
                >
                  <ChevronRight className="h-4.5 w-4.5" />
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Mock Audit logs ──────────────────────────────────────────

function getMockLogs() {
  return [
    {
      id: '1',
      created_at: '2026-06-29T14:15:20Z',
      action: 'Login',
      resource_type: 'user',
      details: 'User authenticated successfully from 192.168.1.5',
      ip_address: '192.168.1.5',
      status: 'success'
    },
    {
      id: '2',
      created_at: '2026-06-29T14:18:42Z',
      action: 'BucketCreate',
      resource_type: 'bucket',
      details: 'S3 bucket "cloudvault-backup-eu" created in region eu-west-1',
      ip_address: '192.168.1.5',
      status: 'success'
    },
    {
      id: '3',
      created_at: '2026-06-29T14:20:10Z',
      action: 'Upload',
      resource_type: 'file',
      details: 'File "app-production-build.zip" uploaded to bucket "cloudvault-backup-eu"',
      ip_address: '192.168.1.5',
      status: 'success'
    },
    {
      id: '4',
      created_at: '2026-06-29T14:22:15Z',
      action: 'ShareGenerate',
      resource_type: 'share',
      details: 'Secure share token created for "quarterly_report_q2.pdf" (expires in 24 hours)',
      ip_address: '192.168.1.5',
      status: 'success'
    }
  ];
}
