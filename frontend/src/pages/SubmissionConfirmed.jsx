import React from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import Layout from '../components/Layout';
import { CheckCircle2, Eye, Download, ArrowRight, ShieldCheck } from 'lucide-react';

export default function SubmissionConfirmed() {
  const location = useLocation();
  const navigate = useNavigate();
  const state = location.state || {};

  const rawRequestId = state.request_id || 'PA-2026-000184';
  const displayRefId = rawRequestId.startsWith('PA-') ? rawRequestId : `PA-2026-${rawRequestId.slice(0, 6).toUpperCase()}`;
  const patientName = state.patient_name || 'John Smith';
  const service = state.service || '70450 - CT Head/Brain';
  const submittedAt = state.submitted_at ? new Date(state.submitted_at).toLocaleString() : new Date().toLocaleString();
  const status = state.status || 'Submitted';

  return (
    <Layout role="initiator">
      <div className="max-w-3xl mx-auto space-y-8 text-center py-6 font-sans">
        {/* Green Check Icon Header */}
        <div className="flex justify-center">
          <div className="w-20 h-20 rounded-full bg-[#DCFCE7] dark:bg-emerald-950 border-4 border-emerald-300 dark:border-emerald-700 text-[#166534] dark:text-emerald-300 flex items-center justify-center shadow-xl">
            <CheckCircle2 className="w-10 h-10" />
          </div>
        </div>

        <div>
          <h1 className="text-3xl font-extrabold text-[#0F172A] dark:text-white tracking-tight">Request Successfully Submitted!</h1>
          <p className="text-sm text-[#64748B] dark:text-slate-400 mt-2 max-w-md mx-auto">
            Your Prior Authorization request has been submitted to <strong className="text-[#0F172A] dark:text-white font-bold">ABC Health Insurance</strong> and is being evaluated.
          </p>
        </div>

        {/* Card Component */}
        <div className="bg-white dark:bg-slate-800 rounded-3xl p-8 shadow-sm text-[#0F172A] dark:text-slate-100 text-left border border-[#E2E8F0] dark:border-slate-700 space-y-6">
          <div className="text-center pb-2 border-b border-[#E2E8F0] dark:border-slate-700">
            <p className="text-[11px] font-black text-[#64748B] dark:text-slate-400 uppercase tracking-widest">PA HUMAN-READABLE REFERENCE NUMBER</p>
            <h2 className="text-3xl font-black text-[#2563EB] dark:text-blue-400 tracking-tight mt-1 font-mono">{displayRefId}</h2>
            <p className="text-[11px] text-[#64748B] dark:text-slate-400 font-mono mt-1">System UUID: {rawRequestId}</p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
            <div className="bg-slate-50 dark:bg-slate-900/60 p-4 rounded-2xl border border-[#E2E8F0] dark:border-slate-700">
              <p className="text-[11px] font-bold text-[#64748B] dark:text-slate-400 uppercase">Submitted Date & Time</p>
              <p className="text-sm font-semibold text-[#0F172A] dark:text-white mt-1">{submittedAt}</p>
            </div>

            <div className="bg-slate-50 dark:bg-slate-900/60 p-4 rounded-2xl border border-[#E2E8F0] dark:border-slate-700">
              <p className="text-[11px] font-bold text-[#5F6368] uppercase">Current Status</p>
              <div className="mt-1">
                <span className="inline-flex items-center px-3 py-1 rounded-md text-xs font-bold bg-amber-50 text-[#92400E] border border-amber-200">
                  AWAITING RESULT
                </span>
              </div>
            </div>

            <div className="bg-slate-50 dark:bg-slate-900/60 p-4 rounded-2xl border border-[#E2E8F0] dark:border-slate-700">
              <p className="text-[11px] font-bold text-[#64748B] dark:text-slate-400 uppercase">Patient Name</p>
              <p className="text-sm font-semibold text-[#0F172A] dark:text-white mt-1">{patientName}</p>
            </div>

            <div className="bg-slate-50 dark:bg-slate-900/60 p-4 rounded-2xl border border-[#E2E8F0] dark:border-slate-700">
              <p className="text-[11px] font-bold text-[#64748B] dark:text-slate-400 uppercase">Service & Diagnosis</p>
              <p className="text-sm font-semibold text-[#0F172A] dark:text-white mt-1">{service}</p>
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex justify-center items-center space-x-4 pt-2">
          <button
            onClick={() => navigate(`/requests/${rawRequestId}`)}
            className="px-6 py-3.5 rounded-xl bg-[#2563EB] hover:bg-blue-700 text-white font-bold text-xs shadow-md transition-all flex items-center space-x-2"
          >
            <Eye className="w-4 h-4" />
            <span>View PA Request Details</span>
          </button>

          <button
            onClick={() => window.print()}
            className="px-6 py-3.5 rounded-xl bg-white dark:bg-slate-800 hover:bg-slate-50 text-[#0F172A] dark:text-slate-200 font-bold text-xs border border-[#E2E8F0] dark:border-slate-700 transition-all flex items-center space-x-2 shadow-sm"
          >
            <Download className="w-4 h-4" />
            <span>Print Evidence PDF</span>
          </button>
        </div>
      </div>
    </Layout>
  );
}
