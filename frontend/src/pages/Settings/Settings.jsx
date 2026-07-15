import React, { useState, useEffect } from 'react';
import { useAuth } from '../../App';
import { awsAPI } from '../../services/api';
import { extractErrorMessage } from '../../utils/error';
import { 
  Settings as SettingsIcon, 
  Key, 
  Globe, 
  ShieldCheck, 
  ShieldAlert, 
  RefreshCw, 
  Unlink, 
  Link2,
  CheckCircle,
  AlertTriangle
} from 'lucide-react';

export default function Settings() {
  const { awsConnected, refreshAwsStatus } = useAuth();
  
  // Credentials form state
  const [accessKey, setAccessKey] = useState('');
  const [secretKey, setSecretKey] = useState('');
  const [region, setRegion] = useState('ap-south-1');
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);

  // Status state
  const [awsInfo, setAwsInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  const fetchStatus = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await awsAPI.status();
      setAwsInfo(data);
    } catch (err) {
      console.error('Failed to load AWS config status:', err);
      setError(extractErrorMessage(err, 'Could not query AWS configuration state.'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, [awsConnected]);

  const handleConnect = async (e) => {
    e.preventDefault();
    if (!accessKey.trim() || !secretKey.trim()) return;

    setConnecting(true);
    setError('');
    setSuccessMsg('');
    try {
      await awsAPI.connect({
        access_key_id: accessKey.trim(),
        secret_access_key: secretKey.trim(),
        region: region
      });
      
      setSuccessMsg('AWS credentials verified and encrypted in database successfully.');
      setAccessKey('');
      setSecretKey('');
      await refreshAwsStatus();
      fetchStatus();
    } catch (err) {
      console.error(err);
      setError(
        extractErrorMessage(err, 'AWS Authentication check failed. Double-check access keys and IAM policy attachments.')
      );
    } finally {
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    if (!window.confirm('Are you sure you want to disconnect S3 access? Stored keys will be permanently deleted from the DB.')) {
      return;
    }

    setDisconnecting(true);
    setError('');
    setSuccessMsg('');
    try {
      await awsAPI.disconnect();
      setSuccessMsg('AWS Credentials disconnected successfully.');
      await refreshAwsStatus();
      fetchStatus();
    } catch (err) {
      console.error(err);
      setError(extractErrorMessage(err, 'Failed to purge S3 credentials.'));
    } finally {
      setDisconnecting(false);
    }
  };

  const regionsList = [
    { code: 'us-east-1', name: 'US East (N. Virginia)' },
    { code: 'us-west-2', name: 'US West (Oregon)' },
    { code: 'eu-west-1', name: 'Europe (Ireland)' },
    { code: 'eu-central-1', name: 'Europe (Frankfurt)' },
    { code: 'ap-south-1', name: 'Asia Pacific (Mumbai)' },
    { code: 'ap-northeast-1', name: 'Asia Pacific (Tokyo)' },
    { code: 'ap-southeast-1', name: 'Asia Pacific (Singapore)' },
  ];

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
          <SettingsIcon className="h-6 w-6 text-slate-400" />
          <span>System Settings</span>
        </h1>
        <p className="text-slate-400 text-sm mt-1">Manage AWS S3 storage connection credentials and encryption configuration.</p>
      </div>

      {error && (
        <div className="rounded-xl bg-rose-500/10 border border-rose-500/20 p-4 text-sm text-rose-400 flex items-start gap-2.5">
          <AlertTriangle className="h-5 w-5 flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {successMsg && (
        <div className="rounded-xl bg-emerald-500/10 border border-emerald-500/20 p-4 text-sm text-emerald-400 flex items-start gap-2.5">
          <CheckCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
          <span>{successMsg}</span>
        </div>
      )}

      {loading ? (
        <div className="flex h-32 items-center justify-center">
          <RefreshCw className="h-6 w-6 text-brand-500 animate-spin" />
        </div>
      ) : awsConnected && awsInfo?.is_connected ? (
        /* ACTIVE CONNECTION PANEL */
        <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-6">
          <div className="flex justify-between items-start gap-4">
            <div className="flex gap-3">
              <div className="h-10 w-10 rounded-xl bg-emerald-500/10 text-emerald-400 flex items-center justify-center flex-shrink-0">
                <ShieldCheck className="h-5.5 w-5.5" />
              </div>
              <div>
                <h3 className="font-bold text-white text-md">AWS Connection Status: Active</h3>
                <p className="text-xs text-slate-400 mt-0.5">Your profile is successfully authenticated and linked with AWS S3.</p>
              </div>
            </div>
            <button
              onClick={handleDisconnect}
              disabled={disconnecting}
              className="px-4 py-2 border border-rose-500/20 hover:bg-rose-500/15 text-rose-400 hover:text-rose-300 font-semibold rounded-xl text-xs flex items-center gap-1.5 transition"
            >
              <Unlink className="h-4 w-4" />
              <span>{disconnecting ? 'Unlinking...' : 'Disconnect Account'}</span>
            </button>
          </div>

          <div className="border-t border-slate-800/80 pt-6 grid grid-cols-1 md:grid-cols-2 gap-6 text-sm text-slate-300">
            <div className="bg-dark-500 p-4 rounded-xl border border-slate-800/50 space-y-2.5">
              <div className="flex justify-between">
                <span className="text-slate-400 text-xs">AWS Account ID</span>
                <span className="font-mono text-white font-semibold">{awsInfo.aws_account_id || '************'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400 text-xs">S3 Region</span>
                <span className="font-semibold text-white uppercase">{awsInfo.region || 'ap-south-1'}</span>
              </div>
            </div>

            <div className="bg-dark-500 p-4 rounded-xl border border-slate-800/50 space-y-1">
              <span className="text-slate-400 text-xs block">Active IAM User ARN</span>
              <span className="font-mono text-[11px] text-brand-300 break-all leading-relaxed font-semibold">
                {awsInfo.iam_arn || 'arn:aws:iam::************:user/cloudvault-restricted'}
              </span>
            </div>
          </div>
        </div>
      ) : (
        /* CONNECT FORM PANEL */
        <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-6">
          <div className="flex gap-3">
            <div className="h-10 w-10 rounded-xl bg-rose-500/10 text-rose-400 flex items-center justify-center flex-shrink-0">
              <ShieldAlert className="h-5.5 w-5.5" />
            </div>
            <div>
              <h3 className="font-bold text-white text-md">AWS Connection Status: Disconnected</h3>
              <p className="text-xs text-slate-400 mt-0.5">Please provide an IAM User Access Credential key-pair containing S3 policy access rules.</p>
            </div>
          </div>

          <form onSubmit={handleConnect} className="space-y-4 pt-2 border-t border-slate-800/80">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">AWS Access Key ID</label>
                <div className="relative">
                  <Key className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                  <input
                    type="text"
                    required
                    value={accessKey}
                    onChange={(e) => setAccessKey(e.target.value)}
                    className="w-full pl-9 pr-4 py-2 bg-dark-500 border border-slate-800 rounded-xl text-slate-100 placeholder-slate-600 focus:outline-none focus:border-brand-500 text-xs"
                    placeholder="AKIAIOSFODNN7EXAMPLE"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">AWS Secret Access Key</label>
                <div className="relative">
                  <Key className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                  <input
                    type="password"
                    required
                    value={secretKey}
                    onChange={(e) => setSecretKey(e.target.value)}
                    className="w-full pl-9 pr-4 py-2 bg-dark-500 border border-slate-800 rounded-xl text-slate-100 placeholder-slate-600 focus:outline-none focus:border-brand-500 text-xs"
                    placeholder="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
                  />
                </div>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Default Home S3 Region</label>
              <div className="relative">
                <Globe className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                <select
                  value={region}
                  onChange={(e) => setRegion(e.target.value)}
                  className="w-full pl-9 pr-4 py-2 bg-dark-500 border border-slate-800 rounded-xl text-white text-xs focus:outline-none focus:border-brand-500"
                >
                  {regionsList.map(r => (
                    <option key={r.code} value={r.code}>{r.name} ({r.code})</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="bg-dark-500 rounded-xl p-4 border border-slate-800/40 text-xs text-slate-400 space-y-2.5">
              <h5 className="font-bold text-white uppercase text-[10px]">Credential Security Hardening Notice</h5>
              <p>
                Stored keys are fully encrypted symmetrically on write in the PostgreSQL engine via <strong>Fernet AES-256 keys</strong>. Credentials are only decrypted temporarily in memory scope during execution request lifespans.
              </p>
              <p>
                For strict security, please construct a dedicated AWS IAM user containing policy scopes limited to <code>s3:*</code> and <code>sts:GetCallerIdentity</code> only.
              </p>
            </div>

            <button
              type="submit"
              disabled={connecting}
              className="w-full py-2.5 bg-brand-500 hover:bg-brand-600 disabled:bg-brand-500/50 text-white font-semibold rounded-xl text-xs flex items-center justify-center gap-1.5 transition"
            >
              <Link2 className="h-4 w-4" />
              <span>{connecting ? 'Validating AWS Connection...' : 'Connect AWS Profile'}</span>
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
