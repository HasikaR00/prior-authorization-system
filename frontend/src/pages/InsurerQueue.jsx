import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import Layout from '../components/Layout';
import { reviewAPI } from '../api';
import { getDisplayStatus } from '../utils/statusUtils';
import { 
  ShieldCheck, 
  Clock, 
  ArrowRight, 
  FileText,
  UserCheck,
  CheckCircle2,
  AlertCircle
} from 'lucide-react';

export default function InsurerQueue() {
  const [queue, setQueue] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filterTab, setFilterTab] = useState('ALL'); // ALL, UNCOMPLETED, COMPLETED

  useEffect(() => {
    fetchQueue();
  }, []);

  const fetchQueue = async () => {
    try {
      const res = await reviewAPI.getQueue();
      setQueue(res.data);
    } catch (err) {
      setError('Failed to load review queue.');
    } finally {
      setLoading(false);
    }
  };

  const getHumanDecisionBadge = (item) => {
    const statusObj = getDisplayStatus(item, 'insurer');
    return (
      <span className={`inline-flex items-center px-2.5 py-1 rounded-md text-xs font-semibold ${statusObj.colorClass}`}>
        {statusObj.isFinal && statusObj.label.includes('APPROVED') && <CheckCircle2 className="w-3.5 h-3.5 mr-1" />}
        {statusObj.isFinal && !statusObj.label.includes('APPROVED') && <AlertCircle className="w-3.5 h-3.5 mr-1" />}
        {!statusObj.isFinal && <Clock className="w-3.5 h-3.5 mr-1" />}
        <span>{statusObj.label}</span>
      </span>
    );
  };

  const uncompletedCount = queue.filter(q => !q.insurer_confirmed_by).length;
  const completedCount = queue.filter(q => !!q.insurer_confirmed_by).length;

  const filteredQueue = queue.filter(q => {
    if (filterTab === 'UNCOMPLETED') return !q.insurer_confirmed_by;
    if (filterTab === 'COMPLETED') return !!q.insurer_confirmed_by;
    return true;
  });

  return (
    <Layout role="insurer">
      <div className="space-y-6 max-w-7xl mx-auto font-sans">
        {/* Header Banner */}
        <div className="bg-white border border-[#E2E8F0] rounded-xl p-6 shadow-sm">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <div className="inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded bg-blue-50 text-[#0D3B66] border border-blue-200 text-xs font-bold mb-2">
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>Payer Clinical Review Board</span>
              </div>
              <h1 className="text-xl font-bold text-[#0D3B66] tracking-tight">Review Workload Dashboard</h1>
              <p className="text-xs text-[#5F6368] mt-1">Review authorization requests, verify policy criteria, and finalize clinical determinations.</p>
            </div>
            <div className="flex items-center space-x-3">
              <div className="bg-slate-50 px-4 py-2 rounded-xl border border-[#CBD2D9] text-right">
                <span className="text-[10px] text-[#5F6368] font-bold uppercase block">Action Needed</span>
                <span className="text-lg font-bold text-[#92400E]">{uncompletedCount} Cases</span>
              </div>
            </div>
          </div>
        </div>

        {/* Workload Metric Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <button 
            onClick={() => setFilterTab('ALL')}
            className={`text-left bg-white border border-[#CBD2D9] border-l-4 border-l-[#0D3B66] rounded-xl p-4 shadow-sm transition-all ${filterTab === 'ALL' ? 'ring-1 ring-[#0D3B66]' : 'hover:border-slate-400'}`}
          >
            <div className="flex justify-between items-start">
              <div>
                <p className="text-[11px] font-bold text-[#5F6368] uppercase tracking-wider">Total Workload</p>
                <h3 className="text-2xl font-bold text-[#0D3B66] mt-0.5">{queue.length}</h3>
              </div>
              <div className="p-2 bg-blue-50 rounded-lg text-[#0D3B66] border border-blue-100">
                <FileText className="w-4 h-4" />
              </div>
            </div>
          </button>

          <button 
            onClick={() => setFilterTab('UNCOMPLETED')}
            className={`text-left bg-white border border-[#CBD2D9] border-l-4 border-l-amber-500 rounded-xl p-4 shadow-sm transition-all ${filterTab === 'UNCOMPLETED' ? 'ring-1 ring-amber-500' : 'hover:border-slate-400'}`}
          >
            <div className="flex justify-between items-start">
              <div>
                <p className="text-[11px] font-bold text-[#5F6368] uppercase tracking-wider">Uncompleted Action</p>
                <h3 className="text-2xl font-bold text-[#92400E] mt-0.5">{uncompletedCount}</h3>
              </div>
              <div className="p-2 bg-amber-50 rounded-lg text-[#92400E] border border-amber-100">
                <Clock className="w-4 h-4" />
              </div>
            </div>
          </button>

          <button 
            onClick={() => setFilterTab('COMPLETED')}
            className={`text-left bg-white border border-[#CBD2D9] border-l-4 border-l-emerald-600 rounded-xl p-4 shadow-sm transition-all ${filterTab === 'COMPLETED' ? 'ring-1 ring-emerald-600' : 'hover:border-slate-400'}`}
          >
            <div className="flex justify-between items-start">
              <div>
                <p className="text-[11px] font-bold text-[#5F6368] uppercase tracking-wider">Completed Determinations</p>
                <h3 className="text-2xl font-bold text-[#166534] mt-0.5">{completedCount}</h3>
              </div>
              <div className="p-2 bg-emerald-50 rounded-lg text-[#166534] border border-emerald-100">
                <CheckCircle2 className="w-4 h-4" />
              </div>
            </div>
          </button>
        </div>

        {/* Requests Table Container */}
        <div className="bg-white border border-[#E2E8F0] rounded-xl overflow-hidden shadow-sm">
          {/* Quick Filter Bar */}
          <div className="px-6 py-2.5 border-b border-[#E2E8F0] bg-slate-50 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center space-x-2">
              <button
                onClick={() => setFilterTab('ALL')}
                className={`px-3 py-1 rounded-lg text-xs font-bold transition-all ${filterTab === 'ALL' ? 'bg-[#0D3B66] text-white shadow-sm' : 'text-[#5F6368] hover:bg-slate-200'}`}
              >
                All Workload ({queue.length})
              </button>
              <button
                onClick={() => setFilterTab('UNCOMPLETED')}
                className={`px-3 py-1 rounded-lg text-xs font-bold transition-all ${filterTab === 'UNCOMPLETED' ? 'bg-amber-100 text-[#92400E] border border-amber-300' : 'text-[#5F6368] hover:bg-slate-200'}`}
              >
                Uncompleted ({uncompletedCount})
              </button>
              <button
                onClick={() => setFilterTab('COMPLETED')}
                className={`px-3 py-1 rounded-lg text-xs font-bold transition-all ${filterTab === 'COMPLETED' ? 'bg-emerald-100 text-[#166534] border border-emerald-300' : 'text-[#5F6368] hover:bg-slate-200'}`}
              >
                Completed ({completedCount})
              </button>
            </div>
            <span className="text-xs text-[#5F6368]">Showing {filteredQueue.length} of {queue.length}</span>
          </div>

          {error ? (
            <div className="p-6 text-center text-red-700 bg-red-50 m-6 rounded-xl border border-red-200 flex items-center justify-center space-x-2 text-xs font-bold">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          ) : loading ? (
            <div className="p-10 text-center text-[#5F6368] text-xs flex items-center justify-center space-x-2">
              <div className="w-4 h-4 border-2 border-[#0D3B66] border-t-transparent rounded-full animate-spin"></div>
              <span>Loading review queue...</span>
            </div>
          ) : filteredQueue.length === 0 ? (
            <div className="p-10 text-center text-[#5F6368] text-xs space-y-2">
              <UserCheck className="w-6 h-6 text-[#166534] mx-auto" />
              <p className="text-[#0D3B66] font-semibold">No prior authorization cases match the selected category.</p>
              <button onClick={() => setFilterTab('ALL')} className="text-[#1F4E79] hover:underline font-bold text-xs inline-block">
                View all cases &rarr;
              </button>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-slate-50 border-b border-[#E2E8F0] text-[11px] font-bold text-[#5F6368] uppercase tracking-wider">
                    <th className="py-3 px-4">Reference #</th>
                    <th className="py-3 px-4">Patient</th>
                    <th className="py-3 px-4">Requested Service</th>
                    <th className="py-3 px-4">Diagnosis</th>
                    <th className="py-3 px-4">Submitted</th>
                    <th className="py-3 px-4">ML Approval Likelihood</th>
                    <th className="py-3 px-4">Recommended Action</th>
                    <th className="py-3 px-4 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E2E8F0] text-xs">
                  {filteredQueue.map((item) => {
                    const shortRef = `PA-2026-${item.request_id.slice(0, 6).toUpperCase()}`;

                    return (
                      <tr key={item.request_id} className="hover:bg-slate-50 transition-colors">
                        {/* Reference # */}
                        <td className="py-3.5 px-4 font-mono font-bold text-[#0D3B66]">
                          {shortRef}
                        </td>

                        {/* Patient */}
                        <td className="py-3.5 px-4">
                          <strong className="font-semibold text-[#0D3B66] block">{item.first_name} {item.last_name}</strong>
                          <span className="text-[11px] text-[#5F6368] block font-mono">ID: {item.patient_id.slice(0, 8)}...</span>
                        </td>

                        {/* Service */}
                        <td className="py-3.5 px-4 max-w-xs">
                          <span className="font-mono font-bold text-[#1F4E79]">{item.requested_hcpcs}</span>
                          <span className="block text-xs text-[#334155] font-medium truncate" title={item.hcpc_description}>
                            {item.hcpc_description}
                          </span>
                        </td>

                        {/* Diagnosis */}
                        <td className="py-3.5 px-4 max-w-xs">
                          <span className="font-mono font-bold text-[#1F4E79]">{item.diagnosis_icd10}</span>
                          <span className="block text-xs text-[#334155] font-medium truncate" title={item.icd10_description}>
                            {item.icd10_description}
                          </span>
                        </td>

                        {/* Submitted Date */}
                        <td className="py-3.5 px-4 text-[#5F6368]">
                          <div className="font-medium text-[#1E293B]">{new Date(item.submitted_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</div>
                        </td>

                        {/* ML Approval Likelihood (Secondary Signal) */}
                        <td className="py-3.5 px-4">
                          {item.ml_model_available && item.predicted_approval_prob !== null && item.predicted_approval_prob !== undefined ? (
                            <div className="space-y-0.5">
                              <span className="inline-block font-bold text-[#0D3B66] bg-slate-100 border border-slate-200 px-2 py-0.5 rounded text-xs">
                                ML Approval Likelihood: {Math.round(item.predicted_approval_prob * 100)}%
                              </span>
                              <span className="block text-[10px] text-[#5F6368]">
                                Informational triage signal only
                              </span>
                              {item.is_synthetic_model && (
                                <span className="block text-[10px] text-amber-800 font-bold uppercase tracking-wider">
                                  Demo / Synthetic Model
                                </span>
                              )}
                            </div>
                          ) : (
                            <span className="text-[11px] text-[#5F6368] italic">Approval likelihood unavailable</span>
                          )}
                        </td>

                        {/* Recommended Action / Status */}
                        <td className="py-3.5 px-4">
                          {getHumanDecisionBadge(item)}
                        </td>

                        {/* Action Button */}
                        <td className="py-3.5 px-4 text-right">
                          <Link
                            to={`/review/${item.request_id}`}
                            className={`inline-flex items-center space-x-1 px-3.5 py-1.5 rounded-lg text-xs font-bold shadow-sm transition-all ${
                              item.insurer_confirmed_by 
                                ? 'bg-slate-100 border border-[#CBD2D9] text-[#0D3B66] hover:bg-slate-200'
                                : 'bg-[#0D3B66] text-white hover:bg-[#1F4E79]'
                            }`}
                          >
                            <span>{item.insurer_confirmed_by ? 'View Review' : 'Perform Review'}</span>
                            <ArrowRight className="w-3.5 h-3.5" />
                          </Link>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
}
