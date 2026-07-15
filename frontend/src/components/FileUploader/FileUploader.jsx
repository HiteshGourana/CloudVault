import React, { useState, useRef } from 'react';
import { Upload, X, FileText, CheckCircle, AlertCircle, RefreshCw, Folder } from 'lucide-react';
import { filesAPI } from '../../services/api';

export default function FileUploader({ bucketName, folderId, onUploadSuccess }) {
  const [dragActive, setDragActive] = useState(false);
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef(null);
  const folderInputRef = useRef(null);

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const traverseFileTree = async (entry, currentPath = '') => {
    let filesList = [];
    if (entry.isFile) {
      const file = await new Promise((resolve) => entry.file(resolve));
      filesList.push({
        file,
        relativePath: currentPath ? `${currentPath}/${file.name}` : file.name
      });
    } else if (entry.isDirectory) {
      const dirReader = entry.createReader();
      let entries = [];
      
      const readAllEntries = async () => {
        const chunk = await new Promise((resolve) => dirReader.readEntries(resolve));
        if (chunk.length > 0) {
          entries = [...entries, ...chunk];
          await readAllEntries();
        }
      };
      
      await readAllEntries();
      
      const nextPath = currentPath ? `${currentPath}/${entry.name}` : entry.name;
      for (const child of entries) {
        const subFiles = await traverseFileTree(child, nextPath);
        filesList.push(...subFiles);
      }
    }
    return filesList;
  };

  const handleDrop = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.items) {
      const filesList = [];
      const promises = [];

      for (let i = 0; i < e.dataTransfer.items.length; i++) {
        const item = e.dataTransfer.items[i];
        if (item.kind === "file") {
          const entry = item.webkitGetAsEntry();
          if (entry) {
            promises.push(
              traverseFileTree(entry, "").then(results => {
                filesList.push(...results);
              })
            );
          }
        }
      }

      await Promise.all(promises);
      addFiles(filesList);
    } else if (e.dataTransfer.files) {
      const mapped = Array.from(e.dataTransfer.files).map(file => ({
        file,
        relativePath: file.name
      }));
      addFiles(mapped);
    }
  };

  const handleChange = (e) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      const mapped = Array.from(e.target.files).map(file => ({
        file,
        relativePath: file.name
      }));
      addFiles(mapped);
    }
  };

  const handleFolderChange = (e) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      const mapped = Array.from(e.target.files).map(file => ({
        file,
        relativePath: file.webkitRelativePath || file.name
      }));
      addFiles(mapped);
    }
  };

  const addFiles = (newFilesWithPaths) => {
    const filteredFiles = newFilesWithPaths.map(({ file, relativePath }) => {
      const isTooLarge = file.size > 100 * 1024 * 1024;
      const normalizedPath = (relativePath || file.name).replace(/\\/g, '/');
      return {
        id: Math.random().toString(36).substring(2, 9),
        file,
        name: file.name,
        size: file.size,
        relativePath: normalizedPath,
        progress: 0,
        status: isTooLarge ? 'failed' : 'idle',
        error: isTooLarge ? 'Exceeds 100MB limit' : ''
      };
    });
    setFiles(prev => [...prev, ...filteredFiles]);
  };

  const removeFile = (id) => {
    setFiles(prev => prev.filter(f => f.id !== id));
  };

  const clearQueue = () => {
    setFiles([]);
  };

  const startUploads = async () => {
    const idleFiles = files.filter(f => f.status === 'idle');
    if (idleFiles.length === 0) return;

    setUploading(true);
    let anySucceeded = false;

    // Check if there are any nested folder structures in the queue
    const hasFolder = idleFiles.some(f => f.relativePath && f.relativePath.includes('/'));

    if (hasFolder) {
      // Update status to uploading for all idle files
      setFiles(prev => prev.map(f => f.status === 'idle' ? { ...f, status: 'uploading' } : f));

      const formData = new FormData();
      idleFiles.forEach(fileObj => {
        formData.append('files', fileObj.file);
        formData.append('relative_paths', fileObj.relativePath);
      });
      formData.append('bucket_name', bucketName);
      if (folderId) {
        formData.append('folder_id', folderId);
      }
      formData.append('duplicate_strategy', 'rename');

      try {
        await filesAPI.uploadFolder(formData, (progressEvent) => {
          const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          setFiles(prev => prev.map(f => f.status === 'uploading' ? { ...f, progress: percentCompleted } : f));
        });

        setFiles(prev => prev.map(f => f.status === 'uploading' ? { ...f, status: 'completed', progress: 100 } : f));
        anySucceeded = true;
      } catch (err) {
        console.error('Failed to upload folder structure:', err);
        const errMsg = err.response?.data?.detail || 'Folder upload failed';
        setFiles(prev => prev.map(f => f.status === 'uploading' ? { ...f, status: 'failed', error: errMsg } : f));
      }
    } else {
      // Individual file uploads
      for (let fileObj of idleFiles) {
        setFiles(prev => prev.map(f => f.id === fileObj.id ? { ...f, status: 'uploading' } : f));

        const formData = new FormData();
        formData.append('file', fileObj.file);
        formData.append('bucket_name', bucketName);
        if (folderId) {
          formData.append('folder_id', folderId);
        }
        formData.append('duplicate_strategy', 'rename');

        try {
          await filesAPI.uploadFile(formData, (progressEvent) => {
            const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            setFiles(prev => prev.map(f => f.id === fileObj.id ? { ...f, progress: percentCompleted } : f));
          });

          setFiles(prev => prev.map(f => f.id === fileObj.id ? { ...f, status: 'completed', progress: 100 } : f));
          anySucceeded = true;
        } catch (err) {
          console.error('Failed to upload:', fileObj.name, err);
          const errMsg = err.response?.data?.detail || 'Upload failed';
          setFiles(prev => prev.map(f => f.id === fileObj.id ? { ...f, status: 'failed', error: errMsg } : f));
        }
      }
    }

    setUploading(false);

    if (anySucceeded && onUploadSuccess) {
      onUploadSuccess();
    }
  };

  const formatBytes = (bytes) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  return (
    <div className="space-y-4">
      {/* Upload Drag & Drop Box */}
      <div
        onDragEnter={handleDrag}
        onDragOver={handleDrag}
        onDragLeave={handleDrag}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-2xl p-6 text-center transition-all duration-200 flex flex-col items-center justify-center ${
          dragActive
            ? 'border-brand-500 bg-brand-500/10 scale-[0.99]'
            : 'border-slate-800 hover:border-brand-500/60 bg-dark-500/30'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          onChange={handleChange}
          className="hidden"
        />
        <input
          ref={folderInputRef}
          type="file"
          webkitdirectory=""
          directory=""
          multiple
          onChange={handleFolderChange}
          className="hidden"
        />
        <div className="h-12 w-12 rounded-xl bg-brand-500/10 text-brand-400 flex items-center justify-center mb-3">
          <Upload className="h-6 w-6" />
        </div>
        <h4 className="font-bold text-white text-sm">Drag &amp; drop files/folders here</h4>
        <p className="text-xs text-slate-400 mt-1 mb-3">or choose an action below</p>
        
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="px-3.5 py-1.5 bg-dark-400 hover:bg-dark-300 border border-slate-800 text-slate-200 hover:text-white rounded-xl text-xs font-semibold transition"
          >
            Select Files
          </button>
          <button
            type="button"
            onClick={() => folderInputRef.current?.click()}
            className="px-3.5 py-1.5 bg-dark-400 hover:bg-dark-300 border border-slate-800 text-slate-200 hover:text-white rounded-xl text-xs font-semibold flex items-center gap-1.5 transition"
          >
            <Folder className="h-3.5 w-3.5 text-brand-400" />
            Select Folder
          </button>
        </div>
        <span className="text-[10px] text-slate-500 uppercase tracking-wide mt-3">Max size: 100MB per file</span>
      </div>

      {/* Upload Progress Queue */}
      {files.length > 0 && (
        <div className="glass-panel rounded-2xl p-4 border border-slate-800/60 space-y-3 flex flex-col">
          <div className="flex justify-between items-center pb-2 border-b border-slate-800/80">
            <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Upload Queue ({files.length})</span>
            <button
              type="button"
              onClick={clearQueue}
              disabled={uploading}
              className="text-xs text-rose-400 hover:text-rose-300 font-semibold disabled:text-slate-600"
            >
              Clear Queue
            </button>
          </div>

          <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
            {files.map((fileObj) => (
              <div key={fileObj.id} className="bg-dark-500/50 rounded-xl p-3 border border-slate-800/30 flex justify-between items-center gap-3">
                <div className="flex items-center gap-2.5 min-w-0 flex-1">
                  {fileObj.relativePath.includes('/') ? (
                    <Folder className="h-4.5 w-4.5 text-brand-400 flex-shrink-0" />
                  ) : (
                    <FileText className="h-4.5 w-4.5 text-slate-400 flex-shrink-0" />
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="flex justify-between text-xs font-semibold text-white mb-1">
                      <span className="truncate max-w-[200px]" title={fileObj.relativePath}>{fileObj.relativePath}</span>
                      <span className="text-slate-400 flex-shrink-0">{formatBytes(fileObj.size)}</span>
                    </div>
                    {/* Progress Bar */}
                    <div className="h-1.5 w-full bg-dark-600 rounded-full overflow-hidden">
                      <div
                        className={`h-full transition-all duration-300 ${
                          fileObj.status === 'failed'
                            ? 'bg-rose-500'
                            : fileObj.status === 'completed'
                            ? 'bg-emerald-500'
                            : 'bg-brand-500'
                        }`}
                        style={{ width: `${fileObj.progress}%` }}
                      ></div>
                    </div>
                    {fileObj.error && (
                      <span className="text-[10px] text-rose-400 block mt-1">{fileObj.error}</span>
                    )}
                  </div>
                </div>

                <div className="flex-shrink-0">
                  {fileObj.status === 'completed' ? (
                    <CheckCircle className="h-5 w-5 text-emerald-400" />
                  ) : fileObj.status === 'failed' ? (
                    <AlertCircle className="h-5 w-5 text-rose-400" />
                  ) : fileObj.status === 'uploading' ? (
                    <RefreshCw className="h-4 w-4 text-brand-400 animate-spin" />
                  ) : (
                    <button
                      type="button"
                      onClick={() => removeFile(fileObj.id)}
                      className="p-1 hover:bg-dark-400 text-slate-400 hover:text-white rounded-lg transition"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>

          <button
            type="button"
            onClick={startUploads}
            disabled={uploading || files.filter(f => f.status === 'idle').length === 0}
            className="w-full py-2 bg-brand-500 hover:bg-brand-600 disabled:bg-brand-500/30 text-white font-semibold rounded-xl text-xs flex items-center justify-center gap-1.5 transition"
          >
            {uploading ? (
              <>
                <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                <span>Uploading...</span>
              </>
            ) : (
              <span>Start Upload ({files.filter(f => f.status === 'idle').length} items)</span>
            )}
          </button>
        </div>
      )}
    </div>
  );
}

