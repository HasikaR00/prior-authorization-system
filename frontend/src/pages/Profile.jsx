import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Layout from '../components/Layout';
import { 
  User, 
  ArrowLeft, 
  Mail, 
  Building, 
  ShieldCheck, 
  Key, 
  Check, 
  FileText,
  BadgeCheck
} from 'lucide-react';

export default function Profile() {
  const navigate = useNavigate();
  const role = localStorage.getItem('user_role') || 'initiator';
  const userName = localStorage.getItem('user_name') || (role === 'insurer' ? 'Sarah Chen' : 'Dr. Sarah Chen');
  const userId = localStorage.getItem('user_id') || 'usr_89234190';
  const [savedSuccess, setSavedSuccess] = useState(false);

  const getInitials = (name) => {
    if (!name) return 'SC';
    const parts = name.replace(/^(Dr\.|Mr\.|Mrs\.|Ms\.)\s+/, '').split(' ');
    if (parts.length >= 2) {
      return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
    }
    return name.slice(0, 2).toUpperCase();
  };

  const handleSave = (e) => {
    e.preventDefault();
    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 3000);
  };

  return (
    <Layout role={role}>
      <div className="max-w-4xl mx-auto space-y-8 font-sans">
        {/* Top Header & Back Button */}
        <div className="flex items-center justify-between border-b border-[#E2E8F0] dark:border-slate-800 pb-5">
          <div className="flex items-center space-x-4">
            <button
              onClick={() => navigate(-1)}
              className="inline-flex items-center space-x-2 px-4 py-2 rounded-xl bg-white dark:bg-slate-800 border border-[#E2E8F0] dark:border-slate-700 text-[#0F172A] dark:text-slate-200 text-sm font-semibold shadow-sm hover:bg-slate-50 transition-all"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>Back to Dashboard</span>
            </button>
            <div>
              <h1 className="text-2xl font-extrabold text-[#0F172A] dark:text-white tracking-tight">User Account & Profile</h1>
              <p className="text-xs text-[#64748B] dark:text-slate-400 mt-0.5">Manage your healthcare provider profile, facility credentials, and security settings.</p>
            </div>
          </div>
        </div>

        {savedSuccess && (
          <div className="p-4 bg-[#DCFCE7] dark:bg-emerald-950/60 border border-emerald-300 dark:border-emerald-700 text-[#166534] dark:text-emerald-300 text-sm rounded-xl flex items-center space-x-2 font-medium shadow-sm">
            <Check className="w-5 h-5 flex-shrink-0" />
            <span>Profile information successfully updated!</span>
          </div>
        )}

        {/* Main Profile Card */}
        <div className="bg-white dark:bg-slate-800 border border-[#E2E8F0] dark:border-slate-700 rounded-2xl p-8 shadow-sm space-y-8">
          {/* Header Badge */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-6 pb-6 border-b border-[#E2E8F0] dark:border-slate-700">
            <div className="flex items-center space-x-5">
              <div className="w-16 h-16 rounded-2xl bg-[#2563EB] text-white font-black flex items-center justify-center text-2xl shadow-lg shadow-blue-500/20">
                {getInitials(userName)}
              </div>
              <div>
                <div className="flex items-center space-x-2">
                  <h2 className="text-xl font-bold text-[#0F172A] dark:text-white">{userName}</h2>
                  <BadgeCheck className="w-5 h-5 text-[#2563EB]" />
                </div>
                <p className="text-xs text-[#64748B] dark:text-slate-400 mt-0.5">
                  {role === 'insurer' ? 'Licensed Insurance Medical Reviewer' : 'Attending Ordering Physician & Hospital Staff'}
                </p>
                <div className="mt-2 inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-blue-50 dark:bg-blue-950/50 text-[#2563EB] dark:text-blue-300 text-xs font-semibold border border-blue-200 dark:border-blue-800">
                  <ShieldCheck className="w-3.5 h-3.5" />
                  <span className="capitalize">{role} Portal User</span>
                </div>
              </div>
            </div>

            <div className="bg-slate-50 dark:bg-slate-900/60 p-4 rounded-xl border border-[#E2E8F0] dark:border-slate-700 text-right">
              <span className="text-[10px] text-[#64748B] dark:text-slate-400 font-bold uppercase tracking-wider block">Account ID</span>
              <span className="font-mono text-xs font-bold text-[#0F172A] dark:text-slate-200">{userId}</span>
            </div>
          </div>

          {/* Form Specs */}
          <form onSubmit={handleSave} className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-xs">
              <div>
                <label className="block text-xs font-semibold text-[#0F172A] dark:text-slate-200 uppercase tracking-wider mb-2">Full Display Name</label>
                <div className="relative">
                  <User className="w-4 h-4 absolute left-3.5 top-3.5 text-slate-400" />
                  <input
                    type="text"
                    defaultValue={userName}
                    className="w-full pl-10 pr-4 py-3 bg-white dark:bg-slate-900 border border-[#E2E8F0] dark:border-slate-700 rounded-xl text-[#0F172A] dark:text-white text-sm focus:outline-none focus:border-[#2563EB]"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#0F172A] dark:text-slate-200 uppercase tracking-wider mb-2">Email Address</label>
                <div className="relative">
                  <Mail className="w-4 h-4 absolute left-3.5 top-3.5 text-slate-400" />
                  <input
                    type="email"
                    defaultValue="sarah.chen@springfield-health.org"
                    className="w-full pl-10 pr-4 py-3 bg-white dark:bg-slate-900 border border-[#E2E8F0] dark:border-slate-700 rounded-xl text-[#0F172A] dark:text-white text-sm focus:outline-none focus:border-[#2563EB]"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#0F172A] dark:text-slate-200 uppercase tracking-wider mb-2">Healthcare Facility / Provider Org</label>
                <div className="relative">
                  <Building className="w-4 h-4 absolute left-3.5 top-3.5 text-slate-400" />
                  <input
                    type="text"
                    defaultValue={role === 'insurer' ? 'Apex Health Insurance Services' : 'Springfield Medical Center'}
                    className="w-full pl-10 pr-4 py-3 bg-white dark:bg-slate-900 border border-[#E2E8F0] dark:border-slate-700 rounded-xl text-[#0F172A] dark:text-white text-sm focus:outline-none focus:border-[#2563EB]"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#0F172A] dark:text-slate-200 uppercase tracking-wider mb-2">National Provider Identifier (NPI)</label>
                <div className="relative">
                  <FileText className="w-4 h-4 absolute left-3.5 top-3.5 text-slate-400" />
                  <input
                    type="text"
                    defaultValue="1928304921"
                    className="w-full pl-10 pr-4 py-3 bg-white dark:bg-slate-900 border border-[#E2E8F0] dark:border-slate-700 rounded-xl text-[#0F172A] dark:text-white text-sm font-mono focus:outline-none focus:border-[#2563EB]"
                  />
                </div>
              </div>
            </div>

            <div className="pt-4 border-t border-[#E2E8F0] dark:border-slate-700 flex justify-end">
              <button
                type="submit"
                className="px-6 py-2.5 bg-[#2563EB] hover:bg-blue-700 text-white font-bold text-xs rounded-xl shadow-sm transition-all"
              >
                Save Profile Changes
              </button>
            </div>
          </form>
        </div>
      </div>
    </Layout>
  );
}
