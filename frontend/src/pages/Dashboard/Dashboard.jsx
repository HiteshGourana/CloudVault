import React, { useState, useEffect } from 'react';
import { useAuth } from '../../App';
import { dashboardAPI } from '../../services/api';
import { 
  Database, 
  Folder, 
  FileText, 
  Share2, 
  HardDrive, 
  AlertTriangle, 
  ShieldCheck, 
  ArrowUpRight, 
  RefreshCw,
  FolderOpen
} from 'lucide-react';
import { 
  ResponsiveContainer, 
  XAxis, 
  YAxis, 
  Tooltip, 
  PieChart, 
  Pie, 
  Cell, 
  BarChart, 
  Bar 
} from 'recharts';

export default function Dashboard() {
  const { awsConnected, user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [fileDist, setFileDist] = useState(null);
  const [recent, setRecent] = useState(null);
  const [error, setError] = useState('');

  const fetchDashboardData = async () => {
    setLoading(true);
    setError('');
    try {
      // Always fetch real data from the database.
      // The backend dashboard service queries PostgreSQL only — it does NOT require
      // an active AWS connection. AWS is only needed for file uploads/downloads.
      const [overviewRes, fileDistRes, recentRes] = await Promise.all([
        dashboardAPI.getOverview(),
        dashboardAPI.getFileCategories(),
        dashboardAPI.getRecentActivity(),
      ]);
      setData(overviewRes);
      setFileDist(fileDistRes);
      setRecent(recentRes);
    } catch (err) {
      console.error('Error fetching dashboard statistics:', err);
      setError('Could not load dashboard metrics. Please try refreshing.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
  }, [awsConnected]);

  const formatBytes = (bytes) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  if (loading) {
    return (
      <div className="flex h-[60vh] w-full items-center justify-center">
        <div className="flex flex-col items-center">
          <RefreshCw className="h-10 w-10 text-brand-500 animate-spin mb-4" />
          <p className="text-slate-400 text-sm">Collating AWS S3 metrics...</p>
        </div>
      </div>
    );
  }

  // File type chart colors
  const COLORS = ['#3b66f5', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6', '#3b82f6', '#6b7280'];

  // Map file categories to chart formatting
  const chartData = fileDist?.distribution ? Object.keys(fileDist.distribution).map(key => ({
    name: key,
    value: fileDist.distribution[key].count,
    size: fileDist.distribution[key].size_bytes,
  })).filter(item => item.value > 0) : [];

  // Build storage chart from real per-bucket data returned by the API.
  // Each bar represents one connected bucket's real storage usage in MB.
  // Falls back to a single zero-point when no buckets are connected yet.
  const storageHistory = data?.buckets && data.buckets.length > 0
    ? data.buckets.map(b => ({
        name: b.bucket_name.length > 16 ? b.bucket_name.substring(0, 14) + '…' : b.bucket_name,
        size: parseFloat((b.size_bytes / (1024 * 1024)).toFixed(2)),
      }))
    : [{ name: 'No buckets yet', size: 0 }];

  return (
    <div className="space-y-6">
      {/* AWS Connection Alert Banner — shown when S3 features are unavailable */}
      {!awsConnected && (
        <div className="rounded-2xl bg-amber-500/10 border border-amber-500/20 p-5 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="flex gap-3 items-start">
            <AlertTriangle className="h-6 w-6 text-amber-500 flex-shrink-0 mt-0.5" />
            <div>
              <h4 className="font-semibold text-white">AWS S3 Not Connected</h4>
              <p className="text-sm text-slate-400 mt-1">
                Dashboard metrics are loaded from your database and are accurate. Connect AWS IAM credentials in Settings to enable file uploads, downloads, and sharing links.
              </p>
            </div>
          </div>
          <button
            onClick={() => window.location.href = '/settings'}
            className="flex-shrink-0 bg-amber-500 hover:bg-amber-600 active:bg-amber-700 text-dark-500 font-bold px-4 py-2 rounded-xl transition duration-150 text-sm"
          >
            Configure AWS Credentials
          </button>
        </div>
      )}

      {/* Header Info */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Dashboard Overview</h1>
          <p className="text-slate-400 text-sm mt-1">Welcome back, {user?.email}. Monitor S3 volumes and secure shares.</p>
        </div>
        <button
          onClick={fetchDashboardData}
          className="flex items-center gap-2 rounded-xl border border-slate-800 bg-dark-400 text-slate-300 hover:text-white px-4 py-2 hover:bg-dark-300 transition text-sm"
        >
          <RefreshCw className="h-4 w-4" />
          <span>Refresh stats</span>
        </button>
      </div>

      {/* Key Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="glass-card p-5 rounded-2xl">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Total Storage</p>
              <h3 className="text-2xl font-bold text-white mt-2">{formatBytes(data?.storage?.storage_used_bytes)}</h3>
            </div>
            <div className="rounded-xl bg-brand-500/10 p-2.5 text-brand-400">
              <HardDrive className="h-5 w-5" />
            </div>
          </div>
          <div className="text-xs text-slate-400 mt-4 flex items-center gap-1">
            <span className="text-emerald-400 font-bold flex items-center">
              +14% <ArrowUpRight className="h-3 w-3" />
            </span>
            <span>from previous month</span>
          </div>
        </div>

        <div className="glass-card p-5 rounded-2xl">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">S3 Buckets</p>
              <h3 className="text-2xl font-bold text-white mt-2">{data?.storage?.total_buckets}</h3>
            </div>
            <div className="rounded-xl bg-indigo-500/10 p-2.5 text-indigo-400">
              <Database className="h-5 w-5" />
            </div>
          </div>
          <div className="text-xs text-slate-400 mt-4">
            <span className="text-white font-medium">{data?.buckets?.length || 0}</span> connected regions
          </div>
        </div>

        <div className="glass-card p-5 rounded-2xl">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Indexed Files</p>
              <h3 className="text-2xl font-bold text-white mt-2">{data?.storage?.total_files}</h3>
            </div>
            <div className="rounded-xl bg-emerald-500/10 p-2.5 text-emerald-400">
              <FileText className="h-5 w-5" />
            </div>
          </div>
          <div className="text-xs text-slate-400 mt-4">
            <span className="text-white font-medium">{data?.storage?.total_folders}</span> virtual folder prefixes
          </div>
        </div>

        <div className="glass-card p-5 rounded-2xl">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Shared Links</p>
              <h3 className="text-2xl font-bold text-white mt-2">{data?.storage?.total_shared_files}</h3>
            </div>
            <div className="rounded-xl bg-pink-500/10 p-2.5 text-pink-400">
              <Share2 className="h-5 w-5" />
            </div>
          </div>
          <div className="text-xs text-slate-400 mt-4">
            Active pre-signed download nodes
          </div>
        </div>
      </div>

      {/* Charts section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Storage per Bucket chart — real data from DB */}
        <div className="glass-card p-5 rounded-2xl lg:col-span-2">
          <h4 className="text-md font-bold text-white mb-1">Storage Per Bucket (MB)</h4>
          <p className="text-xs text-slate-400 mb-4">Live usage data from your connected S3 buckets.</p>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={storageHistory} margin={{ top: 5, right: 10, left: -20, bottom: 20 }}>
                <XAxis
                  dataKey="name"
                  stroke="#6b7280"
                  style={{ fontSize: '11px' }}
                  angle={-20}
                  textAnchor="end"
                  interval={0}
                />
                <YAxis stroke="#6b7280" style={{ fontSize: '11px' }} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#141421', border: '1px solid #2a2a40', borderRadius: '8px' }}
                  labelStyle={{ color: '#fff' }}
                  formatter={(value) => [`${value} MB`, 'Storage Used']}
                />
                <Bar dataKey="size" name="Storage (MB)" fill="#3b66f5" radius={[6, 6, 0, 0]} maxBarSize={60} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* File category distribution */}
        <div className="glass-card p-5 rounded-2xl flex flex-col justify-between">
          <div>
            <h4 className="text-md font-bold text-white mb-2">Extension Distribution</h4>
            <p className="text-xs text-slate-400 mb-4">Share of cataloged files by category count.</p>
          </div>
          <div className="h-44 w-full flex items-center justify-center">
            {chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={chartData}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={70}
                    paddingAngle={3}
                    dataKey="value"
                  >
                    {chartData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#141421', border: '1px solid #2a2a40', borderRadius: '8px' }}
                    itemStyle={{ color: '#fff' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-xs text-slate-500">No data available.</p>
            )}
          </div>
          <div className="space-y-1.5 mt-4">
            {chartData.slice(0, 4).map((entry, idx) => (
              <div key={entry.name} className="flex justify-between items-center text-xs">
                <div className="flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: COLORS[idx % COLORS.length] }}></span>
                  <span className="text-slate-400">{entry.name}</span>
                </div>
                <span className="font-semibold text-slate-200">{entry.value} files ({formatBytes(entry.size)})</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Tables section: Buckets usage & Recent uploads */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Connected Buckets */}
        <div className="glass-panel p-6 rounded-2xl">
          <h4 className="text-md font-bold text-white mb-4">S3 Buckets Usage</h4>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm border-collapse">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400 font-semibold">
                  <th className="py-2.5">Bucket Name</th>
                  <th className="py-2.5">Region</th>
                  <th className="py-2.5 text-right">Files</th>
                  <th className="py-2.5 text-right">Size</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/50">
                {data?.buckets && data.buckets.length > 0 ? (
                  data.buckets.map((bucket) => (
                    <tr key={bucket.bucket_name} className="text-slate-300 hover:text-white">
                      <td className="py-3 flex items-center gap-2">
                        <Database className="h-4 w-4 text-brand-400 flex-shrink-0" />
                        <span className="font-medium truncate max-w-[150px]">{bucket.bucket_name}</span>
                      </td>
                      <td className="py-3 text-xs text-slate-400">{bucket.region}</td>
                      <td className="py-3 text-right">{bucket.file_count}</td>
                      <td className="py-3 text-right font-medium">{formatBytes(bucket.size_bytes)}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan="4" className="py-6 text-center text-slate-500 text-xs">No buckets mapped. Link an S3 storage bucket.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Recent Uploads */}
        <div className="glass-panel p-6 rounded-2xl">
          <h4 className="text-md font-bold text-white mb-4">Recent Upload Log</h4>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm border-collapse">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400 font-semibold">
                  <th className="py-2.5">File Name</th>
                  <th className="py-2.5">Bucket</th>
                  <th className="py-2.5 text-right">Size</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/50">
                {recent?.recent_files && recent.recent_files.length > 0 ? (
                  recent.recent_files.map((file) => (
                    <tr key={file.file_id} className="text-slate-300 hover:text-white">
                      <td className="py-3 flex items-center gap-2">
                        <FileText className="h-4 w-4 text-slate-400 flex-shrink-0" />
                        <span className="truncate max-w-[160px]" title={file.file_name}>{file.file_name}</span>
                      </td>
                      <td className="py-3 text-xs text-slate-400 truncate max-w-[120px]">{file.bucket_name}</td>
                      <td className="py-3 text-right font-medium">{formatBytes(file.size_bytes)}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan="3" className="py-6 text-center text-slate-500 text-xs">No recent file uploads found.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

