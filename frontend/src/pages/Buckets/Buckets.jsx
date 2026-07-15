import React, { useState, useEffect } from 'react';
import { useAuth } from '../../App';
import { bucketsAPI } from '../../services/api';
import { extractErrorMessage } from '../../utils/error';
import { 
  Database, 
  Plus, 
  Trash2, 
  ShieldAlert, 
  ShieldCheck, 
  RefreshCw, 
  Search, 
  Info, 
  ExternalLink,
  Lock,
  Unlock,
  ToggleLeft,
  X,
  AlertTriangle,
  Flame
} from 'lucide-react';

export default function Buckets() {
  const { awsConnected } = useAuth();
  const [buckets, setBuckets] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  
  // Create bucket state
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [newBucketName, setNewBucketName] = useState('');
  const [newBucketRegion, setNewBucketRegion] = useState('ap-south-1');
  const [creating, setCreating] = useState(false);
  
  // Detail modal state
  const [detailsModalOpen, setDetailsModalOpen] = useState(false);
  const [selectedBucket, setSelectedBucket] = useState(null);
  const [bucketDetails, setBucketDetails] = useState(null);
  const [loadingDetails, setLoadingDetails] = useState(false);

  // Delete confirmation modal state
  const [deleteModal, setDeleteModal] = useState(null); // { bucketName, fileCount }
  const [deleting, setDeleting] = useState(false);
  const [deleteResult, setDeleteResult] = useState(null); // { objectsDeleted, versionsDeleted }

  const fetchBuckets = async () => {
    if (!awsConnected) return;
    setLoading(true);
    setError('');
    try {
      const data = await bucketsAPI.list();
      // Backend returns { total, managed, buckets: [...] } — unwrap the array
      setBuckets(Array.isArray(data) ? data : (data.buckets || []));
    } catch (err) {
      console.error('Failed to fetch S3 buckets:', err);
      setError(extractErrorMessage(err, 'Could not list S3 buckets. Verify AWS Credentials connection configuration.'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBuckets();
  }, [awsConnected]);

  const handleCreateBucket = async (e) => {
    e.preventDefault();
    if (!newBucketName.trim()) return;
    setCreating(true);
    setError('');
    try {
      const created = await bucketsAPI.create(newBucketName.trim(), newBucketRegion);
      // Optimistic update: add the new bucket immediately so it shows without delay
      setBuckets(prev => {
        const optimistic = created || {
          bucket_name: newBucketName.trim(),
          region: newBucketRegion,
          bucket_type: 'private',
          creation_date: new Date().toISOString(),
        };
        // Avoid duplicates in case fetchBuckets already returned it
        const exists = prev.some(b => b.bucket_name === optimistic.bucket_name);
        return exists ? prev : [...prev, optimistic].sort((a, b) => a.bucket_name.localeCompare(b.bucket_name));
      });
      setCreateModalOpen(false);
      setNewBucketName('');
      // Also refresh from server in the background for authoritative data
      fetchBuckets();
    } catch (err) {
      console.error('Failed to create S3 bucket:', err);
      setError(extractErrorMessage(err, 'Bucket name already taken or invalid DNS name.'));
    } finally {
      setCreating(false);
    }
  };

  const openDeleteModal = (bucket) => {
    setDeleteResult(null);
    setDeleteModal({ bucketName: bucket.bucket_name, fileCount: bucket.file_count || 0 });
  };

  const handleConfirmDelete = async (forceEmpty) => {
    if (!deleteModal) return;
    setDeleting(true);
    setError('');
    try {
      const res = await bucketsAPI.delete(deleteModal.bucketName, forceEmpty);
      if (forceEmpty) {
        setDeleteResult({
          objectsDeleted: res.objects_deleted ?? 0,
          versionsDeleted: res.versions_deleted ?? 0,
        });
      }
      // Remove from list immediately
      setBuckets(prev => prev.filter(b => b.bucket_name !== deleteModal.bucketName));
      if (!forceEmpty) {
        setDeleteModal(null);
      }
      // Refresh authoritative list in background
      fetchBuckets();
    } catch (err) {
      console.error('Failed to delete S3 bucket:', err);
      setError(extractErrorMessage(err, 'Could not delete S3 bucket. Ensure the bucket is completely empty first.'));
      setDeleteModal(null);
    } finally {
      setDeleting(false);
    }
  };

  const handleViewDetails = async (bucket) => {
    setSelectedBucket(bucket);
    setDetailsModalOpen(true);
    setLoadingDetails(true);
    setBucketDetails(null);
    try {
      const details = await bucketsAPI.getDetails(bucket.bucket_name);
      setBucketDetails(details);
    } catch (err) {
      console.error('Failed to fetch S3 details:', err);
      setError(extractErrorMessage(err, 'Could not load detailed S3 parameters.'));
    } finally {
      setLoadingDetails(false);
    }
  };

  const formatBytes = (bytes) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const filteredBuckets = buckets.filter(b => 
    b.bucket_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">S3 Buckets Manager</h1>
          <p className="text-slate-400 text-sm mt-1">Audit, create, and delete buckets inside your connected AWS profile.</p>
        </div>
        <div className="flex gap-3 w-full md:w-auto">
          {awsConnected && (
            <button
              onClick={() => setCreateModalOpen(true)}
              className="flex-1 md:flex-initial flex items-center justify-center gap-2 bg-brand-500 hover:bg-brand-600 active:bg-brand-700 text-white font-semibold px-4 py-2 rounded-xl transition duration-150 text-sm shadow-lg shadow-brand-500/10"
            >
              <Plus className="h-4 w-4" />
              <span>Create Bucket</span>
            </button>
          )}
          <button
            onClick={fetchBuckets}
            className="rounded-xl border border-slate-800 bg-dark-400 text-slate-300 hover:text-white px-3 py-2 hover:bg-dark-300 transition text-sm"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl bg-rose-500/10 border border-rose-500/20 p-4 text-sm text-rose-400 flex items-start gap-2.5">
          <ShieldAlert className="h-5 w-5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Filter / Search Bar */}
      {awsConnected && (
        <div className="relative max-w-md">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 bg-dark-400 border border-slate-800 rounded-xl text-slate-100 placeholder-slate-500 focus:outline-none focus:border-brand-500 transition duration-200 text-sm"
            placeholder="Filter S3 buckets by name..."
          />
        </div>
      )}

      {/* Buckets Card Grid */}
      {!awsConnected ? (
        <div className="glass-panel p-12 rounded-2xl flex flex-col items-center justify-center text-center">
          <Database className="h-16 w-16 text-slate-600 mb-4" />
          <h3 className="text-xl font-bold text-white">AWS Integration Required</h3>
          <p className="text-slate-400 text-sm max-w-md mt-2 mb-6">
            Connect AWS restricted credentials in Settings to auto-discover, query, and provision S3 storage buckets.
          </p>
          <button
            onClick={() => window.location.href = '/settings'}
            className="bg-brand-500 hover:bg-brand-600 text-white px-5 py-2.5 rounded-xl font-semibold text-sm transition"
          >
            Configure AWS Credentials
          </button>
        </div>
      ) : loading ? (
        <div className="flex h-48 items-center justify-center">
          <RefreshCw className="h-8 w-8 text-brand-500 animate-spin" />
        </div>
      ) : filteredBuckets.length === 0 ? (
        <div className="glass-panel p-12 rounded-2xl flex flex-col items-center justify-center text-center">
          <Database className="h-12 w-12 text-slate-600 mb-3" />
          <h3 className="text-lg font-bold text-white">No Buckets Discovered</h3>
          <p className="text-slate-400 text-sm max-w-sm mt-1">
            {searchQuery ? 'No buckets match your search query.' : 'There are no active S3 buckets registered to your profile. Click "Create Bucket" to configure one.'}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredBuckets.map((bucket) => (
            <div key={bucket.bucket_name} className="glass-card p-5 rounded-2xl flex flex-col justify-between">
              <div>
                <div className="flex justify-between items-start gap-2">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-500/10 text-brand-400">
                    <Database className="h-5 w-5" />
                  </div>
                  <button
                    onClick={() => openDeleteModal(bucket)}
                    className="p-1.5 rounded-lg text-slate-500 hover:bg-rose-500/15 hover:text-rose-400 transition"
                    title="Delete bucket"
                  >
                    <Trash2 className="h-4.5 w-4.5" />
                  </button>
                </div>
                <div className="mt-4">
                  <h3 className="font-bold text-white truncate" title={bucket.bucket_name}>
                    {bucket.bucket_name}
                  </h3>
                  <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mt-1 block">
                    Region: {bucket.region}
                  </span>
                </div>
              </div>

              <div className="border-t border-slate-800/80 my-4 pt-4 flex justify-between items-center text-xs text-slate-400">
                <div>
                  <span className="text-white font-semibold">{bucket.file_count || 0}</span> files
                </div>
                <div>
                  <span className="text-white font-semibold">{formatBytes(bucket.size_bytes)}</span> used
                </div>
              </div>

              <button
                onClick={() => handleViewDetails(bucket)}
                className="w-full py-2 bg-dark-400 hover:bg-dark-300 text-slate-300 hover:text-white rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 transition"
              >
                <Info className="h-3.5 w-3.5" />
                <span>Security & Details</span>
              </button>
            </div>
          ))}
        </div>
      )}

      {/* CREATE BUCKET MODAL */}
      {createModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setCreateModalOpen(false)}></div>
          <div className="bg-dark-400 border border-slate-800 rounded-2xl w-full max-w-md shadow-2xl relative z-10 p-6 animate-in zoom-in-95 duration-150">
            <div className="flex justify-between items-start mb-4">
              <h3 className="text-lg font-bold text-white">Create S3 Bucket</h3>
              <button onClick={() => setCreateModalOpen(false)} className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-dark-300">
                <X className="h-5 w-5" />
              </button>
            </div>
            <form onSubmit={handleCreateBucket} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">S3 Bucket Name</label>
                <input
                  type="text"
                  required
                  value={newBucketName}
                  onChange={(e) => setNewBucketName(e.target.value)}
                  className="w-full px-4 py-2.5 bg-dark-500 border border-slate-800 rounded-xl text-slate-100 placeholder-slate-500 focus:outline-none focus:border-brand-500 text-sm"
                  placeholder="my-unique-s3-bucket-name"
                />
                <p className="text-[10px] text-slate-400 mt-2">
                  Names must be globally unique, 3-63 characters, lowercase letters, numbers and hyphens only.
                </p>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">AWS Region</label>
                <select
                  value={newBucketRegion}
                  onChange={(e) => setNewBucketRegion(e.target.value)}
                  className="w-full px-4 py-2.5 bg-dark-500 border border-slate-800 rounded-xl text-white text-sm focus:outline-none focus:border-brand-500"
                >
                  <option value="us-east-1">US East (N. Virginia) — us-east-1</option>
                  <option value="us-west-2">US West (Oregon) — us-west-2</option>
                  <option value="eu-west-1">Europe (Ireland) — eu-west-1</option>
                  <option value="eu-central-1">Europe (Frankfurt) — eu-central-1</option>
                  <option value="ap-south-1">Asia Pacific (Mumbai) — ap-south-1</option>
                  <option value="ap-northeast-1">Asia Pacific (Tokyo) — ap-northeast-1</option>
                  <option value="ap-southeast-1">Asia Pacific (Singapore) — ap-southeast-1</option>
                </select>
              </div>
              <button
                type="submit"
                disabled={creating}
                className="w-full py-2.5 bg-brand-500 hover:bg-brand-600 disabled:bg-brand-500/50 text-white font-semibold rounded-xl text-sm transition"
              >
                {creating ? 'Creating S3 Bucket...' : 'Create S3 Bucket'}
              </button>
            </form>
          </div>
        </div>
      )}

      {/* DETAIL MODAL */}
      {detailsModalOpen && selectedBucket && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setDetailsModalOpen(false)}></div>
          <div className="bg-dark-400 border border-slate-800 rounded-2xl w-full max-w-lg shadow-2xl relative z-10 p-6 animate-in zoom-in-95 duration-150">
            <div className="flex justify-between items-start mb-4">
              <div className="flex items-center gap-2">
                <Database className="h-5 w-5 text-brand-400" />
                <h3 className="text-lg font-bold text-white truncate max-w-[300px]" title={selectedBucket.bucket_name}>
                  {selectedBucket.bucket_name}
                </h3>
              </div>
              <button onClick={() => setDetailsModalOpen(false)} className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-dark-300">
                <X className="h-5 w-5" />
              </button>
            </div>

            {loadingDetails ? (
              <div className="flex h-40 items-center justify-center">
                <RefreshCw className="h-6 w-6 text-brand-500 animate-spin" />
              </div>
            ) : bucketDetails ? (
              <div className="space-y-4 text-sm text-slate-300">
                <div className="bg-dark-500 rounded-xl p-4 space-y-2 border border-slate-800/40">
                  <div className="flex justify-between">
                    <span className="text-slate-400">AWS S3 Region</span>
                    <span className="font-semibold text-white uppercase">{bucketDetails.region}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Total Cataloged Files</span>
                    <span className="font-semibold text-white">{selectedBucket.file_count || 0} files</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Total Storage Consumed</span>
                    <span className="font-semibold text-white">{formatBytes(selectedBucket.size_bytes)}</span>
                  </div>
                </div>

                <div className="space-y-3 pt-2">
                  <h4 className="font-bold text-white text-xs uppercase tracking-wider text-slate-400">AWS Security Configuration Audit</h4>
                  
                  {/* Public Block Access */}
                  <div className="flex justify-between items-center rounded-xl bg-dark-500 p-3.5 border border-slate-800/40">
                    <div className="flex flex-col">
                      <span className="font-semibold text-white text-sm">Public Access Block</span>
                      <span className="text-[11px] text-slate-400 mt-0.5">Blocks public access via policies or ACLs</span>
                    </div>
                    {bucketDetails.public_access_blocked ? (
                      <div className="flex items-center gap-1.5 text-xs text-emerald-400 font-semibold bg-emerald-500/10 px-2.5 py-1 rounded-full border border-emerald-500/20">
                        <Lock className="h-3.5 w-3.5" />
                        <span>Enabled</span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1.5 text-xs text-rose-400 font-semibold bg-rose-500/10 px-2.5 py-1 rounded-full border border-rose-500/20">
                        <Unlock className="h-3.5 w-3.5" />
                        <span>Public Warning</span>
                      </div>
                    )}
                  </div>

                  {/* Versioning */}
                  <div className="flex justify-between items-center rounded-xl bg-dark-500 p-3.5 border border-slate-800/40">
                    <div className="flex flex-col">
                      <span className="font-semibold text-white text-sm">S3 Object Versioning</span>
                      <span className="text-[11px] text-slate-400 mt-0.5">Retains historical file mutations</span>
                    </div>
                    {bucketDetails.versioning_enabled ? (
                      <div className="flex items-center gap-1.5 text-xs text-emerald-400 font-semibold bg-emerald-500/10 px-2.5 py-1 rounded-full border border-emerald-500/20">
                        <ShieldCheck className="h-3.5 w-3.5" />
                        <span>Enabled</span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1.5 text-xs text-slate-400 font-semibold bg-slate-500/10 px-2.5 py-1 rounded-full border border-slate-500/20">
                        <ToggleLeft className="h-3.5 w-3.5" />
                        <span>Disabled</span>
                      </div>
                    )}
                  </div>

                  {/* Server Encryption */}
                  <div className="flex justify-between items-center rounded-xl bg-dark-500 p-3.5 border border-slate-800/40">
                    <div className="flex flex-col">
                      <span className="font-semibold text-white text-sm">Default Encryption</span>
                      <span className="text-[11px] text-slate-400 mt-0.5">Encrypts objects at rest (SSE-S3 / SSE-KMS)</span>
                    </div>
                    {bucketDetails.encryption_enabled ? (
                      <div className="flex items-center gap-1.5 text-xs text-emerald-400 font-semibold bg-emerald-500/10 px-2.5 py-1 rounded-full border border-emerald-500/20">
                        <Lock className="h-3.5 w-3.5" />
                        <span>{bucketDetails.encryption_type || 'AES-256'}</span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1.5 text-xs text-amber-400 font-semibold bg-amber-500/10 px-2.5 py-1 rounded-full border border-amber-500/20">
                        <Unlock className="h-3.5 w-3.5" />
                        <span>None</span>
                      </div>
                    )}
                  </div>
                </div>

                <div className="pt-4 flex gap-3">
                  <a
                    href={`https://s3.console.aws.amazon.com/s3/buckets/${selectedBucket.bucket_name}`}
                    target="_blank"
                    rel="noreferrer"
                    className="flex-1 py-2 bg-brand-500/10 hover:bg-brand-500/20 text-brand-400 hover:text-brand-300 border border-brand-500/20 rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 transition"
                  >
                    <span>View in AWS Console</span>
                    <ExternalLink className="h-3 w-3" />
                  </a>
                  <button
                    onClick={() => setDetailsModalOpen(false)}
                    className="flex-1 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded-xl text-xs font-semibold transition"
                  >
                    Close Panel
                  </button>
                </div>
              </div>
            ) : (
              <p className="text-center py-6 text-slate-500 text-sm">Failed to retrieve security configuration status.</p>
            )}
          </div>
        </div>
      )}
      {/* DELETE CONFIRMATION MODAL */}
      {deleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="fixed inset-0 bg-black/70 backdrop-blur-sm" onClick={() => !deleting && setDeleteModal(null)} />
          <div className="bg-dark-400 border border-slate-800 rounded-2xl w-full max-w-md shadow-2xl relative z-10 p-6 animate-in zoom-in-95 duration-150">

            {/* Result view (shown after force-empty completes) */}
            {deleteResult ? (
              <div className="text-center">
                <div className="flex h-14 w-14 mx-auto mb-4 items-center justify-center rounded-full bg-emerald-500/10 border border-emerald-500/20">
                  <ShieldCheck className="h-7 w-7 text-emerald-400" />
                </div>
                <h3 className="text-lg font-bold text-white mb-1">Bucket Deleted</h3>
                <p className="text-slate-400 text-sm mb-4">
                  <span className="font-semibold text-white">{deleteModal.bucketName}</span> has been permanently removed.
                </p>
                <div className="bg-dark-500 rounded-xl p-4 text-xs text-slate-300 space-y-1.5 border border-slate-800/60 mb-5">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Objects deleted</span>
                    <span className="font-bold text-white">{deleteResult.objectsDeleted}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Versions / markers removed</span>
                    <span className="font-bold text-white">{deleteResult.versionsDeleted}</span>
                  </div>
                </div>
                <button
                  onClick={() => setDeleteModal(null)}
                  className="w-full py-2.5 bg-brand-500 hover:bg-brand-600 text-white font-semibold rounded-xl text-sm transition"
                >
                  Done
                </button>
              </div>

            ) : deleting ? (
              /* Loading / in-progress view */
              <div className="text-center py-4">
                <div className="flex h-14 w-14 mx-auto mb-4 items-center justify-center rounded-full bg-amber-500/10 border border-amber-500/20">
                  <RefreshCw className="h-7 w-7 text-amber-400 animate-spin" />
                </div>
                <h3 className="text-lg font-bold text-white mb-2">Emptying Bucket…</h3>
                <p className="text-slate-400 text-sm">
                  Deleting all objects and versions from
                  <span className="text-white font-semibold"> {deleteModal.bucketName}</span>.
                  This may take a moment for large buckets.
                </p>
              </div>

            ) : (
              /* Normal confirmation view */
              <>
                <div className="flex justify-between items-start mb-5">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-rose-500/10">
                      <Trash2 className="h-5 w-5 text-rose-400" />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-white">Delete Bucket</h3>
                      <p className="text-xs text-slate-400 truncate max-w-[220px]" title={deleteModal.bucketName}>
                        {deleteModal.bucketName}
                      </p>
                    </div>
                  </div>
                  <button onClick={() => setDeleteModal(null)} className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-dark-300">
                    <X className="h-5 w-5" />
                  </button>
                </div>

                {/* Warning banner when bucket has files */}
                {deleteModal.fileCount > 0 && (
                  <div className="mb-5 rounded-xl bg-amber-500/8 border border-amber-500/20 p-3.5 flex items-start gap-3">
                    <AlertTriangle className="h-5 w-5 text-amber-400 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm font-semibold text-amber-300">
                        Bucket contains {deleteModal.fileCount} tracked file{deleteModal.fileCount !== 1 ? 's' : ''}
                      </p>
                      <p className="text-xs text-slate-400 mt-0.5">
                        AWS won't delete a non-empty bucket. Use <span className="text-amber-300 font-semibold">Force Empty &amp; Delete</span> to wipe everything first.
                      </p>
                    </div>
                  </div>
                )}

                <p className="text-sm text-slate-400 mb-5">
                  This action is <span className="text-white font-semibold">permanent and irreversible</span>.
                  Once deleted, the bucket and all its contents cannot be recovered.
                </p>

                <div className="space-y-2.5">
                  {/* Force Empty & Delete — prominent red danger button */}
                  <button
                    onClick={() => handleConfirmDelete(true)}
                    className="w-full py-2.5 bg-rose-600 hover:bg-rose-500 active:bg-rose-700 text-white font-bold rounded-xl text-sm flex items-center justify-center gap-2 transition shadow-lg shadow-rose-500/20"
                  >
                    <Flame className="h-4 w-4" />
                    Force Empty &amp; Delete Bucket
                  </button>

                  {/* Normal delete — only works if already empty */}
                  <button
                    onClick={() => handleConfirmDelete(false)}
                    className="w-full py-2.5 bg-dark-500 hover:bg-dark-300 text-slate-300 hover:text-white border border-slate-700 font-semibold rounded-xl text-sm transition"
                  >
                    Delete (bucket must be empty)
                  </button>

                  <button
                    onClick={() => setDeleteModal(null)}
                    className="w-full py-2 text-slate-500 hover:text-slate-300 text-sm font-medium transition"
                  >
                    Cancel
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
