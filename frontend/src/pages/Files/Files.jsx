import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../../App';
import { bucketsAPI, foldersAPI, filesAPI, shareAPI } from '../../services/api';
import { extractErrorMessage } from '../../utils/error';
import FileUploader from '../../components/FileUploader/FileUploader';
import { 
  Folder, 
  File, 
  Search, 
  ArrowLeft, 
  Plus, 
  Upload, 
  MoreVertical, 
  Download, 
  Trash2, 
  Edit2, 
  Move, 
  Copy, 
  Share2, 
  Database,
  ArrowRight,
  ChevronRight,
  FolderPlus,
  RefreshCw,
  X,
  Clock,
  ExternalLink,
  Clipboard,
  CheckCircle,
  FileArchive,
  FileImage,
  FileVideo,
  FileAudio,
  CheckSquare,
  Square
} from 'lucide-react';
import axios from 'axios';

export default function Files() {
  const { awsConnected } = useAuth();
  
  // Navigation states
  const [buckets, setBuckets] = useState([]);
  const [currentBucket, setCurrentBucket] = useState('');
  const [currentFolderId, setCurrentFolderId] = useState(null);
  const [breadcrumbs, setBreadcrumbs] = useState([]);

  // Data states
  const [folders, setFolders] = useState([]);
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedItem, setSelectedItem] = useState(null); // { type: 'file'/'folder', data: obj }

  // Action modals
  const [uploaderOpen, setUploaderOpen] = useState(false);
  
  const [folderModalOpen, setFolderModalOpen] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const [creatingFolder, setCreatingFolder] = useState(false);

  const [renameModalOpen, setRenameModalOpen] = useState(false);
  const [renameName, setRenameName] = useState('');
  const [renaming, setRenaming] = useState(false);

  const [moveModalOpen, setMoveModalOpen] = useState(false);
  const [allFoldersList, setAllFoldersList] = useState([]);
  const [targetFolderId, setTargetFolderId] = useState('root');
  const [moving, setMoving] = useState(false);
  const [isCopyOperation, setIsCopyOperation] = useState(false);

  const [shareModalOpen, setShareModalOpen] = useState(false);
  const [shareExpiration, setShareExpiration] = useState('1h');
  const [sharingUrl, setSharingUrl] = useState('');
  const [copiedUrl, setCopiedUrl] = useState(false);
  const [generatingShare, setGeneratingShare] = useState(false);

  // ── Multi-select / Bulk delete state ───────────────────────────────────────
  // selectedIds is a Set of strings: `file:uuid` or `folder:uuid`
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);

  const [syncing, setSyncing] = useState(false);

  const handleSyncBucket = async () => {
    if (!currentBucket) return;
    setSyncing(true);
    setError('');
    try {
      const res = await filesAPI.syncBucket(currentBucket);
      alert(res.message || 'S3 sync completed successfully.');
      fetchContents();
    } catch (err) {
      console.error(err);
      setError(extractErrorMessage(err, 'Failed to sync with S3 bucket.'));
    } finally {
      setSyncing(false);
    }
  };

  // ── Pagination state ────────────────────────────────────────────────────────
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(50); // Default to 50 for better list view
  const [totalPages, setTotalPages] = useState(1);
  const [totalItems, setTotalItems] = useState(0);

  // Fetch buckets list first
  useEffect(() => {
    const initBuckets = async () => {
      if (!awsConnected) return;
      try {
        const res = await bucketsAPI.list();
        // Backend returns { total, managed, buckets: [...] } — unwrap the array
        const bucketData = Array.isArray(res) ? res : (res.buckets || []);
        setBuckets(bucketData);
        if (bucketData.length > 0) {
          setCurrentBucket(bucketData[0].bucket_name);
        }
      } catch (err) {
        console.error('Failed to load S3 buckets:', err);
      }
    };
    initBuckets();
  }, [awsConnected]);

  // Fetch files and folders whenever bucket/folder changes
  // Wrapped in useCallback so the reference is stable across renders.
  // Without this, passing fetchContents as onUploadSuccess to FileUploader
  // captures a stale closure that may miss updated bucket/folderId state.
  const fetchContents = useCallback(async () => {
    if (!currentBucket) return;
    setLoading(true);
    setError('');
    setSelectedItem(null);
    setSelectedIds(new Set()); // clear selection on every refresh / navigation
    try {
      // 1. Fetch folders
      const foldersData = await foldersAPI.list({
        bucket_name: currentBucket,
        parent_folder_id: currentFolderId || undefined
      });
      setFolders(foldersData);

      // 2. Fetch files metadata
      const filesData = await filesAPI.list({
        bucket_name: currentBucket,
        folder_id: currentFolderId || undefined,
        filter_root: currentFolderId ? false : true,
        page: currentPage,
        page_size: pageSize
      });
      setFiles(filesData.files || []);
      setTotalPages(filesData.total_pages || 1);
      setTotalItems(filesData.total_items || 0);
    } catch (err) {
      console.error('Failed to list S3 explorer contents:', err);
      setError(extractErrorMessage(err, 'Could not query directory objects.'));
    } finally {
      setLoading(false);
    }
  }, [currentBucket, currentFolderId, currentPage, pageSize]); // re-create when these change

  useEffect(() => {
    fetchContents();
  }, [currentBucket, currentFolderId, currentPage, pageSize]);

  // Navigate deeper into a folder
  const handleNavigateToFolder = (folder) => {
    setCurrentFolderId(folder.id);
    setBreadcrumbs(prev => [...prev, { id: folder.id, name: folder.folder_name }]);
    setCurrentPage(1); // reset to page 1
  };

  // Navigate via Breadcrumbs
  const handleNavigateBreadcrumb = (index) => {
    setCurrentPage(1); // reset to page 1
    if (index === -1) {
      setCurrentFolderId(null);
      setBreadcrumbs([]);
    } else {
      const nextBreadcrumbs = breadcrumbs.slice(0, index + 1);
      const target = nextBreadcrumbs[nextBreadcrumbs.length - 1];
      setCurrentFolderId(target.id);
      setBreadcrumbs(nextBreadcrumbs);
    }
  };

  // Create Virtual Folder placeholder
  const handleCreateFolder = async (e) => {
    e.preventDefault();
    if (!newFolderName.trim() || !currentBucket) return;
    setCreatingFolder(true);
    setError('');
    try {
      await foldersAPI.create({
        bucket_name: currentBucket,
        folder_name: newFolderName.trim(),
        parent_folder_id: currentFolderId || undefined
      });
      setFolderModalOpen(false);
      setNewFolderName('');
      fetchContents();
    } catch (err) {
      console.error(err);
      setError(extractErrorMessage(err, 'Could not create folder placeholder.'));
    } finally {
      setCreatingFolder(false);
    }
  };

  // Delete folder / soft-delete file
  const handleDeleteItem = async (item, type) => {
    const name = type === 'folder' ? item.folder_name : item.file_name;
    if (!window.confirm(`Are you sure you want to delete ${type} "${name}"?`)) {
      return;
    }
    setError('');
    try {
      if (type === 'folder') {
        await foldersAPI.delete(item.id);
      } else {
        await filesAPI.delete(item.id);
      }
      fetchContents();
    } catch (err) {
      console.error(err);
      setError(extractErrorMessage(err, `Failed to delete ${type}.`));
    }
  };

  // ── Multi-select helpers ───────────────────────────────────────────────

  const toggleSelectItem = (key) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  // Select all files in this folder across all pages
  const selectAllItemsInDirectory = async () => {
    setLoading(true);
    try {
      const allFileIds = [];
      const promises = [];
      for (let p = 1; p <= totalPages; p++) {
        promises.push(
          filesAPI.list({
            bucket_name: currentBucket,
            folder_id: currentFolderId || undefined,
            filter_root: currentFolderId ? false : true,
            page: p,
            page_size: pageSize
          })
        );
      }
      const results = await Promise.all(promises);
      results.forEach(res => {
        if (res.files) {
          res.files.forEach(f => allFileIds.push(`file:${f.id}`));
        }
      });

      // Also add all current folders in the current view
      const allFolderKeys = folders.map(f => `folder:${f.id}`);
      
      setSelectedIds(new Set([...allFolderKeys, ...allFileIds]));
    } catch (err) {
      console.error('Failed to select all items in directory:', err);
      setError('Could not retrieve all item IDs.');
    } finally {
      setLoading(false);
    }
  };

  // Bulk delete all selected items (uses single bulkDelete call for files)
  const handleBulkDelete = async () => {
    const count = selectedIds.size;
    if (count === 0) return;
    if (!window.confirm(`Delete ${count} selected item${count > 1 ? 's' : ''}? This cannot be undone.`)) return;

    setBulkDeleting(true);
    setError('');
    
    // Separate folder and file IDs
    const folderIds = [];
    const fileIds = [];
    for (const key of selectedIds) {
      const [type, id] = key.split(':');
      if (type === 'folder') {
        folderIds.push(id);
      } else {
        fileIds.push(id);
      }
    }

    let errorOccurred = false;

    try {
      // 1. Bulk delete files in one call
      if (fileIds.length > 0) {
        await filesAPI.bulkDelete(fileIds);
      }
      
      // 2. Delete folders sequentially (since S3 prefix/db deletion is unique per folder)
      for (const fId of folderIds) {
        try {
          await foldersAPI.delete(fId);
        } catch (err) {
          console.error(`Failed to delete folder ${fId}:`, err);
          errorOccurred = true;
        }
      }
    } catch (err) {
      console.error('Failed bulk files delete request:', err);
      errorOccurred = true;
    }

    setBulkDeleting(false);
    setSelectedIds(new Set());
    if (errorOccurred) {
      setError('Some items could not be deleted. They may be non-empty folders or already removed.');
    }
    fetchContents();
  };

  // Rename folder / file
  const handleOpenRename = (item, type) => {
    setSelectedItem({ type, data: item });
    setRenameName(type === 'folder' ? item.folder_name : item.file_name);
    setRenameModalOpen(true);
  };

  const handleRenameSubmit = async (e) => {
    e.preventDefault();
    if (!renameName.trim() || !selectedItem) return;
    setRenaming(true);
    setError('');
    try {
      if (selectedItem.type === 'folder') {
        await foldersAPI.rename(selectedItem.data.id, renameName.trim());
      } else {
        await filesAPI.rename(selectedItem.data.id, renameName.trim());
      }
      setRenameModalOpen(false);
      fetchContents();
    } catch (err) {
      console.error(err);
      setError(extractErrorMessage(err, 'Failed to rename directory item.'));
    } finally {
      setRenaming(false);
    }
  };

  // Download streaming file binary
  const handleDownloadFile = async (file) => {
    try {
      const response = await axios.get(`/api/v1/files/${file.id}/download`, {
        headers: {
          Authorization: `Bearer ${localStorage.getItem('token')}`,
        },
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', file.file_name);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Streaming download failed:', err);
      alert('Could not download file. Verify network or permissions.');
    }
  };

  // Open Move / Copy modal
  const handleOpenMoveCopy = async (item, type, isCopy = false) => {
    setSelectedItem({ type, data: item });
    setIsCopyOperation(isCopy);
    setMoveModalOpen(true);
    setMoving(false);
    setTargetFolderId('root');
    
    // Fetch folders lists for move targets
    try {
      // Flatten hierarchy for dropdown mapping
      const tree = await foldersAPI.getTree({ bucket_name: currentBucket });
      const flatList = [];
      const traverse = (node, depth = 0) => {
        flatList.push({ id: node.id, name: '— '.repeat(depth) + node.folder_name });
        if (node.children) {
          node.children.forEach(c => traverse(c, depth + 1));
        }
      };
      tree.forEach(node => traverse(node));
      
      // Filter out itself if moving a folder to prevent circular loops
      const finalFolders = type === 'folder' 
        ? flatList.filter(f => f.id !== item.id) 
        : flatList;
        
      setAllFoldersList(finalFolders);
    } catch (err) {
      console.error('Failed to load folder targets:', err);
    }
  };

  const handleMoveCopySubmit = async (e) => {
    e.preventDefault();
    if (!selectedItem) return;
    setMoving(true);
    setError('');
    
    const folderIdParam = targetFolderId === 'root' ? null : targetFolderId;
    
    try {
      if (isCopyOperation) {
        // Copy file
        await filesAPI.copy(selectedItem.data.id, folderIdParam);
      } else {
        // Move file or folder
        if (selectedItem.type === 'folder') {
          await foldersAPI.move(selectedItem.data.id, folderIdParam);
        } else {
          await filesAPI.move(selectedItem.data.id, folderIdParam);
        }
      }
      setMoveModalOpen(false);
      fetchContents();
    } catch (err) {
      console.error(err);
      setError(extractErrorMessage(err, 'Failed to move/copy item.'));
    } finally {
      setMoving(false);
    }
  };

  // Open Sharing link modal
  const handleOpenShare = (file) => {
    setSelectedItem({ type: 'file', data: file });
    setShareModalOpen(true);
    setSharingUrl('');
    setCopiedUrl(false);
  };

  const handleGenerateShareLink = async () => {
    if (!selectedItem) return;
    setGeneratingShare(true);
    setSharingUrl('');
    try {
      const res = await shareAPI.createDownloadLink({
        file_id: selectedItem.data.id,
        expiration: shareExpiration
      });
      // Backend returns presigned_url as defined in ShareResponse
      setSharingUrl(res.presigned_url);
    } catch (err) {
      console.error('Failed to generate pre-signed link:', err);
      setError(extractErrorMessage(err, 'Could not generate sharing pre-signed URL.'));
    } finally {
      setGeneratingShare(false);
    }
  };

  const handleCopyClipboard = () => {
    if (!sharingUrl) return;
    navigator.clipboard.writeText(sharingUrl);
    setCopiedUrl(true);
    setTimeout(() => setCopiedUrl(false), 2000);
  };

  const formatBytes = (bytes) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const getFileIcon = (ext) => {
    const e = ext ? ext.toLowerCase() : '';
    if (['.zip', '.rar', '.tar', '.gz', '.7z'].includes(e)) return <FileArchive className="h-5 w-5 text-amber-500" />;
    if (['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'].includes(e)) return <FileImage className="h-5 w-5 text-indigo-400" />;
    if (['.mp4', '.avi', '.mov', '.mkv'].includes(e)) return <FileVideo className="h-5 w-5 text-rose-500" />;
    if (['.mp3', '.wav', '.ogg', '.aac'].includes(e)) return <FileAudio className="h-5 w-5 text-emerald-400" />;
    return <File className="h-5 w-5 text-slate-400" />;
  };

  const filteredFolders = folders.filter(f => 
    f.folder_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const filteredFiles = files.filter(f => 
    f.file_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Computed from filtered results — must be placed AFTER filteredFolders/filteredFiles
  const allVisibleKeys = [
    ...filteredFolders.map(f => `folder:${f.id}`),
    ...filteredFiles.map(f => `file:${f.id}`),
  ];
  const allSelected = allVisibleKeys.length > 0 && allVisibleKeys.every(k => selectedIds.has(k));
  const someSelected = allVisibleKeys.some(k => selectedIds.has(k));

  const toggleSelectAll = () => {
    if (allSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(allVisibleKeys));
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Banner/Setup Checks */}
      {!awsConnected && (
        <div className="glass-panel p-12 rounded-2xl flex flex-col items-center justify-center text-center">
          <Database className="h-16 w-16 text-slate-600 mb-4" />
          <h3 className="text-xl font-bold text-white">AWS Connection Required</h3>
          <p className="text-slate-400 text-sm max-w-md mt-2 mb-6">
            Configure S3 credentials in Settings to start uploading, generating share codes, and sorting virtual directory nodes.
          </p>
          <button
            onClick={() => window.location.href = '/settings'}
            className="bg-brand-500 hover:bg-brand-600 text-white px-5 py-2.5 rounded-xl font-semibold text-sm transition"
          >
            Configure AWS Credentials
          </button>
        </div>
      )}

      {awsConnected && (
        <>
          {/* Header Controls */}
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-slate-800 pb-4">
            <div className="flex items-center gap-3">
              <Database className="h-6 w-6 text-brand-400" />
              <select
                value={currentBucket}
                onChange={(e) => {
                  setCurrentBucket(e.target.value);
                  setCurrentFolderId(null);
                  setBreadcrumbs([]);
                  setCurrentPage(1);
                }}
                className="bg-dark-500 border border-slate-800 rounded-xl px-3 py-1.5 text-white font-bold text-md focus:outline-none focus:border-brand-500"
              >
                {buckets.map(b => (
                  <option key={b.bucket_name} value={b.bucket_name}>{b.bucket_name}</option>
                ))}
              </select>
            </div>

            <div className="flex gap-2 w-full sm:w-auto">
              <button
                onClick={() => setFolderModalOpen(true)}
                className="flex-1 sm:flex-initial flex items-center justify-center gap-1.5 border border-slate-800 bg-dark-400 text-slate-300 hover:text-white px-4 py-2 rounded-xl text-xs font-semibold hover:bg-dark-300 transition"
              >
                <FolderPlus className="h-4 w-4" />
                <span>New Folder</span>
              </button>
              <button
                onClick={() => setUploaderOpen(!uploaderOpen)}
                className="flex-1 sm:flex-initial flex items-center justify-center gap-1.5 bg-brand-500 hover:bg-brand-600 text-white px-4 py-2 rounded-xl text-xs font-semibold transition shadow-lg shadow-brand-500/10"
              >
                <Upload className="h-4 w-4" />
                <span>Upload Files</span>
              </button>
              <button
                onClick={handleSyncBucket}
                disabled={syncing}
                className="flex-1 sm:flex-initial flex items-center justify-center gap-1.5 border border-slate-800 bg-dark-400 hover:bg-dark-300 text-slate-300 hover:text-white px-4 py-2 rounded-xl text-xs font-semibold disabled:opacity-50 transition"
              >
                <RefreshCw className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} />
                <span>{syncing ? 'Syncing...' : 'Sync S3'}</span>
              </button>
              <button
                onClick={fetchContents}
                className="rounded-xl border border-slate-800 bg-dark-400 text-slate-300 hover:text-white px-3 py-2 hover:bg-dark-300 transition"
              >
                <RefreshCw className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Error display */}
          {error && (
            <div className="rounded-xl bg-rose-500/10 border border-rose-500/20 p-4 text-xs text-rose-400">
              {error}
            </div>
          )}

          {/* Breadcrumbs Navigation */}
          <div className="flex items-center gap-1 text-sm text-slate-400 overflow-x-auto whitespace-nowrap py-1">
            <button
              onClick={() => handleNavigateBreadcrumb(-1)}
              className="hover:text-brand-400 transition"
            >
              Root
            </button>
            {breadcrumbs.map((crumb, idx) => (
              <React.Fragment key={crumb.id}>
                <ChevronRight className="h-3.5 w-3.5 text-slate-600 flex-shrink-0" />
                <button
                  onClick={() => handleNavigateBreadcrumb(idx)}
                  className={`hover:text-brand-400 transition ${idx === breadcrumbs.length - 1 ? 'text-white font-semibold' : ''}`}
                >
                  {crumb.name}
                </button>
              </React.Fragment>
            ))}
          </div>

          {/* Slide-out uploader tray */}
          {uploaderOpen && (
            <div className="glass-panel p-5 rounded-2xl border border-slate-800/80">
              <div className="flex justify-between items-center mb-3">
                <h4 className="font-bold text-white text-sm">Upload to S3 Folder</h4>
                <button onClick={() => setUploaderOpen(false)} className="text-slate-400 hover:text-white p-1 rounded-lg">
                  <X className="h-4 w-4" />
                </button>
              </div>
              <FileUploader
                bucketName={currentBucket}
                folderId={currentFolderId}
                onUploadSuccess={() => {
                  // Close the tray so the user sees the refreshed file list
                  setUploaderOpen(false);
                  // Refresh both folders and files
                  fetchContents();
                }}
              />
            </div>
          )}

          {/* Explorer Search */}
          <div className="relative max-w-sm">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 bg-dark-400 border border-slate-800 rounded-xl text-slate-100 placeholder-slate-500 focus:outline-none focus:border-brand-500 transition duration-200 text-xs"
              placeholder="Search folders and files..."
            />
          </div>

          {/* Core Explorer List View */}
          {loading ? (
            <div className="flex h-48 items-center justify-center">
              <RefreshCw className="h-8 w-8 text-brand-500 animate-spin" />
            </div>
          ) : filteredFolders.length === 0 && filteredFiles.length === 0 ? (
            <div className="glass-panel p-16 rounded-2xl text-center">
              <Folder className="h-16 w-16 text-slate-700 mx-auto mb-4" />
              <h4 className="font-bold text-white text-lg">Directory Empty</h4>
              <p className="text-slate-400 text-sm mt-1 max-w-xs mx-auto">
                No folders or files here. Create a new folder prefix or drag and drop items here to sync with S3.
              </p>
            </div>
          ) : (
            <div className="glass-panel rounded-2xl overflow-hidden border border-slate-800/85">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-slate-800 bg-dark-500/60 text-slate-400 font-semibold">
                      {/* Select All Checkbox Header */}
                      <th className="pl-5 pr-2 py-3 w-8">
                        <button
                          type="button"
                          onClick={toggleSelectAll}
                          className="text-slate-400 hover:text-brand-400 transition-colors"
                          title={allSelected ? 'Deselect all' : 'Select all'}
                        >
                          {allSelected ? (
                            <CheckSquare className="h-4.5 w-4.5 text-brand-400" />
                          ) : someSelected ? (
                            <CheckSquare className="h-4.5 w-4.5 text-brand-400/50" />
                          ) : (
                            <Square className="h-4.5 w-4.5" />
                          )}
                        </button>
                      </th>
                      <th className="px-3 py-3">Name</th>
                      <th className="px-5 py-3">Type</th>
                      <th className="px-5 py-3 text-right">Size</th>
                      <th className="px-5 py-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/40">
                    {/* Folders first */}
                    {filteredFolders.map((folder) => {
                      const key = `folder:${folder.id}`;
                      const isSelected = selectedIds.has(key);
                      return (
                        <tr 
                          key={folder.id} 
                          className={`text-slate-300 hover:text-white cursor-pointer transition-colors ${
                            isSelected ? 'bg-brand-500/8 hover:bg-brand-500/12' : 'hover:bg-dark-400/20'
                          }`}
                          onDoubleClick={() => handleNavigateToFolder(folder)}
                        >
                          {/* Folder Checkbox Cell */}
                          <td 
                            className="pl-5 pr-2 py-3.5 w-8"
                            onClick={(e) => { e.stopPropagation(); toggleSelectItem(key); }}
                          >
                            <button type="button" className="text-slate-400 hover:text-brand-400 transition-colors">
                              {isSelected ? (
                                <CheckSquare className="h-4.5 w-4.5 text-brand-400" />
                              ) : (
                                <Square className="h-4.5 w-4.5" />
                              )}
                            </button>
                          </td>
                          <td className="px-3 py-3.5 flex items-center gap-2.5" onClick={() => handleNavigateToFolder(folder)}>
                            <Folder className="h-5 w-5 text-brand-400 flex-shrink-0" />
                            <span className="font-medium truncate max-w-[250px]">{folder.folder_name}</span>
                          </td>
                          <td className="px-5 py-3.5 text-slate-500">Folder</td>
                          <td className="px-5 py-3.5 text-right text-slate-500">—</td>
                          <td className="px-5 py-3.5 text-right" onClick={(e) => e.stopPropagation()}>
                            <div className="flex justify-end gap-1.5">
                              <button
                                onClick={() => handleOpenRename(folder, 'folder')}
                                className="p-1 rounded text-slate-500 hover:bg-dark-300 hover:text-white"
                                title="Rename folder"
                              >
                                <Edit2 className="h-3.5 w-3.5" />
                              </button>
                              <button
                                onClick={() => handleOpenMoveCopy(folder, 'folder', false)}
                                className="p-1 rounded text-slate-500 hover:bg-dark-300 hover:text-white"
                                title="Move folder"
                              >
                                <Move className="h-3.5 w-3.5" />
                              </button>
                              <button
                                onClick={() => handleDeleteItem(folder, 'folder')}
                                className="p-1 rounded text-slate-500 hover:bg-rose-500/10 hover:text-rose-400"
                                title="Delete folder"
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}

                    {/* Files list */}
                    {filteredFiles.map((file) => {
                      const key = `file:${file.id}`;
                      const isSelected = selectedIds.has(key);
                      return (
                        <tr 
                          key={file.id} 
                          className={`text-slate-300 hover:text-white transition-colors ${
                            isSelected ? 'bg-brand-500/8 hover:bg-brand-500/12' : 'hover:bg-dark-400/20'
                          }`}
                        >
                          {/* File Checkbox Cell */}
                          <td 
                            className="pl-5 pr-2 py-3.5 w-8"
                            onClick={() => toggleSelectItem(key)}
                          >
                            <button type="button" className="text-slate-400 hover:text-brand-400 transition-colors">
                              {isSelected ? (
                                <CheckSquare className="h-4.5 w-4.5 text-brand-400" />
                              ) : (
                                <Square className="h-4.5 w-4.5" />
                              )}
                            </button>
                          </td>
                          <td className="px-3 py-3.5 flex items-center gap-2.5">
                            {getFileIcon(file.extension)}
                            <span className="truncate max-w-[250px] font-medium" title={file.file_name}>{file.file_name}</span>
                          </td>
                          <td className="px-5 py-3.5 text-slate-500 font-mono uppercase text-[10px]">{file.extension ? file.extension.replace('.', '') : 'binary'}</td>
                          <td className="px-5 py-3.5 text-right font-medium">{formatBytes(file.size_bytes)}</td>
                          <td className="px-5 py-3.5 text-right">
                            <div className="flex justify-end gap-1.5">
                              <button
                                onClick={() => handleDownloadFile(file)}
                                className="p-1 rounded text-slate-500 hover:bg-dark-300 hover:text-white"
                                title="Download file"
                              >
                                <Download className="h-3.5 w-3.5" />
                              </button>
                              <button
                                onClick={() => handleOpenShare(file)}
                                className="p-1 rounded text-slate-500 hover:bg-dark-300 hover:text-white"
                                title="Generate Share link"
                              >
                                <Share2 className="h-3.5 w-3.5" />
                              </button>
                              <button
                                onClick={() => handleOpenRename(file, 'file')}
                                className="p-1 rounded text-slate-500 hover:bg-dark-300 hover:text-white"
                                title="Rename file"
                              >
                                <Edit2 className="h-3.5 w-3.5" />
                              </button>
                              <button
                                onClick={() => handleOpenMoveCopy(file, 'file', false)}
                                className="p-1 rounded text-slate-500 hover:bg-dark-300 hover:text-white"
                                title="Move file"
                              >
                                <Move className="h-3.5 w-3.5" />
                              </button>
                              <button
                                onClick={() => handleOpenMoveCopy(file, 'file', true)}
                                className="p-1 rounded text-slate-500 hover:bg-dark-300 hover:text-white"
                                title="Copy file"
                              >
                                <Copy className="h-3.5 w-3.5" />
                              </button>
                              <button
                                onClick={() => handleDeleteItem(file, 'file')}
                                className="p-1 rounded text-slate-500 hover:bg-rose-500/10 hover:text-rose-400"
                                title="Delete file"
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {/* Pagination controls footer block */}
              {totalPages > 1 && (
                <div className="flex items-center justify-between px-6 py-4 border-t border-slate-800 bg-dark-500/20 text-xs text-slate-400">
                  <div>
                    Showing <span className="font-semibold text-slate-200">{((currentPage - 1) * pageSize) + 1}</span> to{' '}
                    <span className="font-semibold text-slate-200">
                      {Math.min(currentPage * pageSize, totalItems)}
                    </span> of{' '}
                    <span className="font-semibold text-slate-200">{totalItems}</span> items
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
                      disabled={currentPage === 1}
                      className="px-3 py-1.5 rounded-lg border border-slate-800 hover:bg-dark-300 disabled:opacity-50 disabled:pointer-events-none hover:text-white transition duration-200 font-semibold"
                    >
                      Previous
                    </button>
                    <button
                      type="button"
                      onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))}
                      disabled={currentPage === totalPages}
                      className="px-3 py-1.5 rounded-lg border border-slate-800 hover:bg-dark-300 disabled:opacity-50 disabled:pointer-events-none hover:text-white transition duration-200 font-semibold"
                    >
                      Next
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── Floating Bulk Action Bar ── appears when items are selected */}
          {someSelected && (
            <div
              className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 flex items-center gap-4 px-5 py-3 rounded-2xl shadow-2xl border border-rose-500/30 animate-in fade-in slide-in-from-bottom-4 duration-200"
              style={{ background: 'rgba(18,18,35,0.97)', backdropFilter: 'blur(16px)', minWidth: '340px' }}
            >
              {/* Count badge with select all option */}
              <div className="flex flex-col flex-1">
                <div className="flex items-center gap-2">
                  <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-rose-500/15 text-rose-400 font-bold text-xs">
                    {selectedIds.size}
                  </span>
                  <span className="text-slate-300 text-sm font-medium">
                    item{selectedIds.size > 1 ? 's' : ''} selected
                  </span>
                </div>
                {/* Select all across pages helper link */}
                {selectedIds.size === filteredFiles.length && totalItems > filteredFiles.length && (
                  <button
                    type="button"
                    onClick={selectAllItemsInDirectory}
                    className="text-[10px] text-brand-400 hover:text-brand-300 underline text-left mt-1 font-semibold"
                  >
                    Select all {totalItems} items in folder
                  </button>
                )}
              </div>

              {/* Clear selection */}
              <button
                type="button"
                onClick={() => setSelectedIds(new Set())}
                className="text-slate-400 hover:text-white text-xs px-3 py-1.5 rounded-lg hover:bg-slate-800 transition font-semibold"
              >
                Clear
              </button>

              {/* Delete button */}
              <button
                type="button"
                onClick={handleBulkDelete}
                disabled={bulkDeleting}
                className="flex items-center gap-2 px-4 py-2 bg-rose-500 hover:bg-rose-600 disabled:bg-rose-500/50 text-white font-bold rounded-xl text-xs transition"
              >
                <Trash2 className="h-3.5 w-3.5" />
                {bulkDeleting
                  ? `Deleting…`
                  : `Delete Selected`
                }
              </button>
            </div>
          )}

          {/* CREATE FOLDER MODAL */}
          {folderModalOpen && (
            <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
              <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setFolderModalOpen(false)}></div>
              <div className="bg-dark-400 border border-slate-800 rounded-2xl w-full max-w-sm shadow-2xl relative z-10 p-6 animate-in zoom-in-95 duration-150">
                <div className="flex justify-between items-start mb-4">
                  <h3 className="text-lg font-bold text-white">Create Virtual Folder</h3>
                  <button onClick={() => setFolderModalOpen(false)} className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-dark-300">
                    <X className="h-5 w-5" />
                  </button>
                </div>
                <form onSubmit={handleCreateFolder} className="space-y-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Folder Name</label>
                    <input
                      type="text"
                      required
                      value={newFolderName}
                      onChange={(e) => setNewFolderName(e.target.value)}
                      className="w-full px-4 py-2.5 bg-dark-500 border border-slate-800 rounded-xl text-slate-100 placeholder-slate-500 focus:outline-none focus:border-brand-500 text-sm"
                      placeholder="My Documents"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={creatingFolder}
                    className="w-full py-2.5 bg-brand-500 hover:bg-brand-600 disabled:bg-brand-500/50 text-white font-semibold rounded-xl text-sm transition"
                  >
                    {creatingFolder ? 'Creating Folder...' : 'Create Folder'}
                  </button>
                </form>
              </div>
            </div>
          )}

          {/* RENAME MODAL */}
          {renameModalOpen && selectedItem && (
            <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
              <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setRenameModalOpen(false)}></div>
              <div className="bg-dark-400 border border-slate-800 rounded-2xl w-full max-w-sm shadow-2xl relative z-10 p-6 animate-in zoom-in-95 duration-150">
                <div className="flex justify-between items-start mb-4">
                  <h3 className="text-lg font-bold text-white">Rename {selectedItem.type === 'folder' ? 'Folder' : 'File'}</h3>
                  <button onClick={() => setRenameModalOpen(false)} className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-dark-300">
                    <X className="h-5 w-5" />
                  </button>
                </div>
                <form onSubmit={handleRenameSubmit} className="space-y-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">New Name</label>
                    <input
                      type="text"
                      required
                      value={renameName}
                      onChange={(e) => setRenameName(e.target.value)}
                      className="w-full px-4 py-2.5 bg-dark-500 border border-slate-800 rounded-xl text-slate-100 placeholder-slate-500 focus:outline-none focus:border-brand-500 text-sm"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={renaming}
                    className="w-full py-2.5 bg-brand-500 hover:bg-brand-600 disabled:bg-brand-500/50 text-white font-semibold rounded-xl text-sm transition"
                  >
                    {renaming ? 'Saving Rename...' : 'Save Rename'}
                  </button>
                </form>
              </div>
            </div>
          )}

          {/* MOVE / COPY MODAL */}
          {moveModalOpen && selectedItem && (
            <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
              <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setMoveModalOpen(false)}></div>
              <div className="bg-dark-400 border border-slate-800 rounded-2xl w-full max-w-sm shadow-2xl relative z-10 p-6 animate-in zoom-in-95 duration-150">
                <div className="flex justify-between items-start mb-4">
                  <h3 className="text-lg font-bold text-white">
                    {isCopyOperation ? 'Copy File' : `Move ${selectedItem.type === 'folder' ? 'Folder' : 'File'}`}
                  </h3>
                  <button onClick={() => setMoveModalOpen(false)} className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-dark-300">
                    <X className="h-5 w-5" />
                  </button>
                </div>
                <form onSubmit={handleMoveCopySubmit} className="space-y-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Target S3 Destination Directory</label>
                    <select
                      value={targetFolderId}
                      onChange={(e) => setTargetFolderId(e.target.value)}
                      className="w-full px-4 py-2.5 bg-dark-500 border border-slate-800 rounded-xl text-white text-sm focus:outline-none focus:border-brand-500"
                    >
                      <option value="root">Root Level (Bucket Root)</option>
                      {allFoldersList.map(f => (
                        <option key={f.id} value={f.id}>{f.name}</option>
                      ))}
                    </select>
                  </div>
                  <button
                    type="submit"
                    disabled={moving}
                    className="w-full py-2.5 bg-brand-500 hover:bg-brand-600 disabled:bg-brand-500/50 text-white font-semibold rounded-xl text-sm transition"
                  >
                    {moving ? (isCopyOperation ? 'Copying...' : 'Moving...') : (isCopyOperation ? 'Copy Item' : 'Move Item')}
                  </button>
                </form>
              </div>
            </div>
          )}

          {/* SHARE LINK MODAL */}
          {shareModalOpen && selectedItem && selectedItem.type === 'file' && (
            <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
              <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setShareModalOpen(false)}></div>
              <div className="bg-dark-400 border border-slate-800 rounded-2xl w-full max-w-md shadow-2xl relative z-10 p-6 animate-in zoom-in-95 duration-150">
                <div className="flex justify-between items-start mb-4">
                  <div className="flex items-center gap-2">
                    <Share2 className="h-5 w-5 text-brand-400" />
                    <h3 className="text-lg font-bold text-white">Generate Secure Sharing Link</h3>
                  </div>
                  <button onClick={() => setShareModalOpen(false)} className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-dark-300">
                    <X className="h-5 w-5" />
                  </button>
                </div>

                <div className="space-y-4">
                  <div className="bg-dark-500 rounded-xl p-3 border border-slate-800/40 text-xs">
                    <span className="text-slate-400 block font-semibold mb-1">Target File:</span>
                    <span className="text-white font-mono break-all">{selectedItem.data.file_name}</span>
                  </div>

                  {!sharingUrl ? (
                    <div className="space-y-4">
                      <div>
                        <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">URL Expiration Timer</label>
                        <select
                          value={shareExpiration}
                          onChange={(e) => setShareExpiration(e.target.value)}
                          className="w-full px-4 py-2.5 bg-dark-500 border border-slate-800 rounded-xl text-white text-sm focus:outline-none focus:border-brand-500"
                        >
                          <option value="15m">15 Minutes</option>
                          <option value="1h">1 Hour</option>
                          <option value="24h">24 Hours (1 Day)</option>
                          <option value="7d">7 Days</option>
                        </select>
                        <p className="text-[10px] text-slate-500 mt-2">
                          The generated link uses a transient AWS S3 pre-signed credential token. After this time expires, access is automatically revoked by AWS.
                        </p>
                      </div>
                      <button
                        onClick={handleGenerateShareLink}
                        disabled={generatingShare}
                        className="w-full py-2.5 bg-brand-500 hover:bg-brand-600 disabled:bg-brand-500/50 text-white font-semibold rounded-xl text-sm transition"
                      >
                        {generatingShare ? 'Generating Token...' : 'Generate Sharing URL'}
                      </button>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      <div className="space-y-2">
                        <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider">Shareable URL Link</label>
                        <div className="flex gap-2">
                          <input
                            type="text"
                            readOnly
                            value={sharingUrl}
                            className="flex-1 px-3 py-2 bg-dark-500 border border-slate-800 rounded-xl text-xs text-brand-300 font-mono focus:outline-none"
                          />
                          <button
                            onClick={handleCopyClipboard}
                            className="bg-brand-500 hover:bg-brand-600 text-white p-2.5 rounded-xl transition duration-150 flex items-center justify-center"
                            title="Copy to clipboard"
                          >
                            {copiedUrl ? <CheckCircle className="h-4.5 w-4.5" /> : <Clipboard className="h-4.5 w-4.5" />}
                          </button>
                        </div>
                        {copiedUrl && (
                          <span className="text-[10px] text-emerald-400 block text-right font-medium">Link copied to clipboard!</span>
                        )}
                      </div>

                      <div className="rounded-xl bg-emerald-500/10 border border-emerald-500/20 p-3 flex gap-2 items-start text-xs text-emerald-400">
                        <Clock className="h-4 w-4 mt-0.5 flex-shrink-0" />
                        <span>This link is active and will expire automatically in {shareExpiration === '15m' ? '15 minutes' : shareExpiration === '1h' ? '1 hour' : shareExpiration === '24h' ? '24 hours' : '7 days'}.</span>
                      </div>

                      <div className="flex gap-2">
                        <a
                          href={sharingUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="flex-1 py-2 bg-brand-500/10 hover:bg-brand-500/20 text-brand-400 border border-brand-500/20 rounded-xl text-xs font-semibold flex items-center justify-center gap-1 transition"
                        >
                          <span>Open in Tab</span>
                          <ExternalLink className="h-3.5 w-3.5" />
                        </a>
                        <button
                          onClick={() => setShareModalOpen(false)}
                          className="flex-1 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded-xl text-xs font-semibold transition"
                        >
                          Close Panel
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
