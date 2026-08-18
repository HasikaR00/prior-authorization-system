import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import Layout from '../components/Layout';
import { requestAPI } from '../api';
import { getDisplayStatus } from '../utils/statusUtils';
import { 
  PlusCircle, 
  Clock, 
  CheckCircle2, 
  AlertCircle, 
  FileText, 
  Activity,
  ArrowRight
} from 'lucide-react';

export default function InitiatorDashboard() {
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filterTab, setFilterTab] = useState('ALL'); // ALL, PENDING, APPROVED, INFO

  useEffect(() => {
    fetchRequests();
  }, []);

  const fetchRequests = async () => {
    try {
      const res = await requestAPI.getUserRequests();
      setRequests(res.data);
    } catch (err) {
      setError('Failed to load authorization requests.');
    } finally {
      setLoading(false);
    }
  };

  const getStatusBadge = (status, insurerFinalStatus) => {
    const finalStat = insurerFinalStatus || status;
    switch (finalStat) {
      case 'APPROVED':
        return (
          <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-[#DCFCE7] text-[#166534] border border-emerald-200">
            <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> Approved
          </span>
        );
      case 'INFO_REQUESTED':
        return (
          <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-[#F3E8FF] text-[#6B21A8] border border-purple-200">
            <AlertCircle className="w-3.5 h-3.5 mr-1" /> Additional Info Required
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-[#FEF3C7] text-[#92400E] border border-amber-200">
            <Clock className="w-3.5 h-3.5 mr-1" /> Under Review
          </span>
        );
    }
  };

  const approvedCount = requests.filter(r => getDisplayStatus(r, 'initiator').label === 'Approved').length;
  const awaitingCount = requests.filter(r => !getDisplayStatus(r, 'initiator').isFinal).length;

  const filteredRequests = requests
    .filter(r => {
      const statusObj = getDisplayStatus(r, 'initiator');
      if (filterTab === 'APPROVED') return statusObj.label === 'Approved';
      if (filterTab === 'AWAITING') return !statusObj.isFinal;
      return true;
    });

  return (
    <Layout role="initiator">
      <div className="space-y-8 max-w-7xl mx-auto font-sans">
        {/* Welcome & Stats Banner */}
        <div className="bg-white border border-[#E2E8F0] rounded-2xl p-6 relative overflow-hidden shadow-sm">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 z-10 relative">
            <div>
              <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-blue-50 text-[#2563EB] border border-blue-200 text-xs font-semibold mb-3">
                <Activity className="w-3.5 h-3.5" />
                <span>Hospital Provider Portal</span>
              </div>
              <h1 className="text-2xl font-extrabold text-[#0F172A] tracking-tight">Prior Authorization Dashboard</h1>
              <p className="text-sm text-[#64748B] mt-1">Manage patient authorization requests, view decision tracking, and submit new cases.</p>
            </div>
            <Link
              to="/new-request"
              className="inline-flex items-center space-x-2 px-5 py-3 rounded-xl bg-[#2563EB] hover:bg-blue-700 text-white font-semibold text-sm shadow-md transition-all self-start md:self-auto"
            >
              <PlusCircle className="w-4 h-4" />
              <span>New PA Request</span>
            </Link>
          </div>
        </div>

        {/* Overview Metric Cards (Clickable to Filter) */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <button 
            onClick={() => setFilterTab('ALL')}
            className={`text-left bg-white border border-[#CBD2D9] border-l-4 border-l-[#0D3B66] rounded-xl p-5 shadow-sm transition-all hover:border-[#0D3B66] ${filterTab === 'ALL' ? 'ring-2 ring-[#0D3B66]/20 bg-blue-50/20' : ''}`}
          >
            <div className="flex justify-between items-start">
              <div>
                <p className="text-xs font-semibold text-[#3B7A99] uppercase tracking-wider">Total Requests</p>
                <h3 className="text-3xl font-extrabold text-[#0D3B66] mt-1">{requests.length}</h3>
              </div>
              <div className="p-2.5 bg-blue-50 rounded-xl text-[#0D3B66] border border-blue-100">
                <FileText className="w-5 h-5" />
              </div>
            </div>
          </button>

          <button 
            onClick={() => setFilterTab('APPROVED')}
            className={`text-left bg-white border border-[#CBD2D9] border-l-4 border-l-emerald-500 rounded-xl p-5 shadow-sm transition-all hover:border-emerald-500 ${filterTab === 'APPROVED' ? 'ring-2 ring-emerald-500/20 bg-emerald-50/20' : ''}`}
          >
            <div className="flex justify-between items-start">
              <div>
                <p className="text-xs font-semibold text-[#3B7A99] uppercase tracking-wider">Approved</p>
                <h3 className="text-3xl font-extrabold text-[#166534] mt-1">{approvedCount}</h3>
              </div>
              <div className="p-2.5 bg-emerald-50 rounded-xl text-[#166534] border border-emerald-100">
                <CheckCircle2 className="w-5 h-5" />
              </div>
            </div>
          </button>

          <button 
            onClick={() => setFilterTab('AWAITING')}
            className={`text-left bg-white border border-[#CBD2D9] border-l-4 border-l-amber-500 rounded-xl p-5 shadow-sm transition-all hover:border-amber-500 ${filterTab === 'AWAITING' ? 'ring-2 ring-amber-500/20 bg-amber-50/20' : ''}`}
          >
            <div className="flex justify-between items-start">
              <div>
                <p className="text-xs font-semibold text-[#3B7A99] uppercase tracking-wider">Awaiting Result</p>
                <h3 className="text-3xl font-extrabold text-[#92400E] mt-1">{awaitingCount}</h3>
              </div>
              <div className="p-2.5 bg-amber-50 rounded-xl text-[#92400E] border border-amber-100">
                <Clock className="w-5 h-5" />
              </div>
            </div>
          </button>
        </div>

        {/* Requests Table Container with Quick Filter Bar */}
        <div className="bg-white border border-[#CBD2D9] rounded-2xl overflow-hidden shadow-sm">
          {/* Quick Filter Bar */}
          <div className="px-6 py-3 border-b border-[#CBD2D9] bg-slate-50/80 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center space-x-2">
              <button
                onClick={() => setFilterTab('ALL')}
                className={`px-3.5 py-1.5 rounded-xl text-[13px] font-semibold transition-all ${filterTab === 'ALL' ? 'bg-[#0D3B66] text-white shadow-sm' : 'text-[#3B7A99] hover:bg-[#EDF1F5]'}`}
              >
                All ({requests.length})
              </button>
              <button
                onClick={() => setFilterTab('APPROVED')}
                className={`px-3.5 py-1.5 rounded-xl text-[13px] font-semibold transition-all ${filterTab === 'APPROVED' ? 'bg-[#2E7D5B]/20 text-[#2E7D5B] border border-[#2E7D5B]/40' : 'text-[#3B7A99] hover:bg-[#EDF1F5]'}`}
              >
                Approved ({approvedCount})
              </button>
              <button
                onClick={() => setFilterTab('AWAITING')}
                className={`px-3.5 py-1.5 rounded-xl text-[13px] font-semibold transition-all ${filterTab === 'AWAITING' ? 'bg-[#C08A1E]/20 text-[#C08A1E] border border-[#C08A1E]/40' : 'text-[#3B7A99] hover:bg-[#EDF1F5]'}`}
              >
                Awaiting Result ({awaitingCount})
              </button>
            </div>
            <span className="text-[13px] text-[#3B7A99]">Showing {filteredRequests.length} of {requests.length}</span>
          </div>

          {error ? (
            <div className="p-8 text-center text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/40 m-6 rounded-xl border border-red-200 dark:border-red-900 flex items-center justify-center space-x-2">
              <AlertCircle className="w-5 h-5 flex-shrink-0" />
              <span className="text-sm font-semibold">{error}</span>
            </div>
          ) : loading ? (
            <div className="p-12 text-center text-[#64748B] text-sm flex items-center justify-center space-x-2">
              <div className="w-5 h-5 border-2 border-[#14477A] border-t-transparent rounded-full animate-spin"></div>
              <span>Loading authorization requests...</span>
            </div>
          ) : filteredRequests.length === 0 ? (
            <div className="p-12 text-center text-[#64748B] text-sm space-y-3">
              <FileText className="w-8 h-8 text-slate-400 mx-auto" />
              <p>No requests match the selected filter tab.</p>
              <button onClick={() => setFilterTab('ALL')} className="text-[#2563EB] hover:underline text-xs font-semibold inline-block">
                View all requests &rarr;
              </button>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-slate-100 dark:bg-slate-800 border-b border-[#E2E5E9] text-[13px] font-semibold text-[#6B7280] dark:text-slate-300 uppercase tracking-wider">
                    <th className="py-3.5 px-5">Reference #</th>
                    <th className="py-3.5 px-5">Patient</th>
                    <th className="py-3.5 px-5">Requested Service</th>
                    <th className="py-3.5 px-5">Diagnosis</th>
                    <th className="py-3.5 px-5">Submitted</th>
                    <th className="py-3.5 px-5">Status</th>
                    <th className="py-3.5 px-5 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E2E5E9] dark:divide-slate-800 text-[15px]">
                  {filteredRequests.map((r) => {
                    const shortRef = `PA-2026-${r.request_id.slice(0, 6).toUpperCase()}`;
                    
                    return (
                      <tr key={r.request_id} className="hover:bg-[#EDF1F5]/50 dark:hover:bg-slate-800/50 transition-colors">
                        {/* Reference # */}
                        <td className="py-4 px-5">
                          <span className="font-mono font-bold text-[#14477A] dark:text-blue-400 cursor-help" title={`Full System UUID: ${r.request_id}`}>
                            {shortRef}
                          </span>
                          {r.parent_request_id && (
                            <span className="block text-[13px] text-[#6B7280]">Child of PA-2026-{r.parent_request_id.slice(0, 4).toUpperCase()}</span>
                          )}
                        </td>

                        {/* Patient */}
                        <td className="py-4 px-5">
                          <strong className="font-semibold text-[#1F2937] dark:text-white block">{r.first_name} {r.last_name}</strong>
                          <span className="text-[13px] text-[#6B7280] block">DOB: 15 Jun 1985</span>
                        </td>

                        {/* Requested Service (Code + Plain-English Description) */}
                        <td className="py-4 px-5 max-w-xs">
                          <span className="font-mono font-bold text-[#14477A] dark:text-blue-300">{r.requested_hcpcs}</span>
                          <span className="block text-[15px] text-[#1F2937] dark:text-slate-200 font-medium truncate" title={r.hcpc_description || r.hcpc_raw_description || r.requested_hcpcs}>
                            {r.hcpc_description || r.hcpc_raw_description || `Procedure (${r.requested_hcpcs})`}
                          </span>
                        </td>

                        {/* Diagnosis (Code + Plain-English Description) */}
                        <td className="py-4 px-5 max-w-xs">
                          <span className="font-mono font-bold text-[#14477A] dark:text-blue-300">{r.diagnosis_icd10}</span>
                          <span className="block text-[15px] text-[#1F2937] dark:text-slate-200 font-medium truncate" title={r.icd10_description || r.icd10_raw_description || r.diagnosis_icd10}>
                            {r.icd10_description || r.icd10_raw_description || `Diagnosis (${r.diagnosis_icd10})`}
                          </span>
                        </td>

                        {/* Submitted Date */}
                        <td className="py-4 px-5 text-[#6B7280] text-[13px]">
                          <div>Recently</div>
                          <div className="font-medium text-[#1F2937] dark:text-slate-300">{new Date(r.submitted_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</div>
                        </td>

                        {/* Status + Mini Stepper Progress */}
                        <td className="py-4 px-5">
                          <div className="space-y-1.5">
                            {(() => {
                              const statusObj = getDisplayStatus(r, 'initiator');
                              return (
                                <span className={`inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-[12px] font-bold ${statusObj.colorClass}`}>
                                  {statusObj.isFinal && statusObj.label === 'APPROVED' && <CheckCircle2 className="w-3.5 h-3.5" />}
                                  {statusObj.isFinal && statusObj.label === 'DENIED' && <AlertCircle className="w-3.5 h-3.5" />}
                                  {statusObj.isFinal && statusObj.label !== 'APPROVED' && statusObj.label !== 'DENIED' && <AlertCircle className="w-3.5 h-3.5" />}
                                  {!statusObj.isFinal && <Clock className="w-3.5 h-3.5" />}
                                  <span>{statusObj.label}</span>
                                </span>
                              );
                            })()}

                            {/* 4-Step Progress Bar Line */}
                            <div className="flex items-center space-x-1 w-28" title="Submitted -> Eligibility Verified -> Under Clinical Review -> Decision Confirmed">
                              <div className="h-1.5 flex-1 rounded-full bg-[#2E7D5B]"></div>
                              <div className="h-1.5 flex-1 rounded-full bg-[#2E7D5B]"></div>
                              <div className={`h-1.5 flex-1 rounded-full ${r.insurer_confirmed_by || r.insurer_final_status ? 'bg-[#2E7D5B]' : 'bg-blue-500 animate-pulse'}`}></div>
                              <div className={`h-1.5 flex-1 rounded-full ${
                                r.insurer_confirmed_by || r.insurer_final_status
                                  ? (r.insurer_final_status === 'APPROVED' ? 'bg-[#2E7D5B]' : r.insurer_final_status === 'DENIED' ? 'bg-red-500' : 'bg-amber-500')
                                  : 'bg-slate-200'
                              }`}></div>
                            </div>

                            {/* Reviewer Note Preview */}
                            {r.insurer_override_note && (
                              <div className="text-[11px] text-[#0D3B66] font-medium truncate max-w-xs" title={`Reviewer Note: ${r.insurer_override_note}`}>
                                <span className="font-bold text-blue-600">Reviewer Note:</span> {r.insurer_override_note}
                              </div>
                            )}
                          </div>
                        </td>

                        {/* Action Button */}
                        <td className="py-4 px-5 text-right flex items-center justify-end space-x-2">
                          <Link
                            to={`/requests/${r.request_id}`}
                            className="inline-flex items-center space-x-1 px-3 py-1.5 rounded-xl bg-[#0D3B66] hover:bg-[#1F4E79] text-white text-[12px] font-semibold shadow-sm transition-all"
                          >
                            <span>View Details</span>
                            <ArrowRight className="w-3.5 h-3.5" />
                          </Link>
                          <Link
                            to={`/requests/${r.request_id}?print=true`}
                            className="inline-flex items-center space-x-1 px-3 py-1.5 rounded-xl bg-white border border-[#CBD2D9] text-[#0D3B66] hover:bg-slate-100 text-[12px] font-semibold shadow-sm transition-all"
                          >
                            <FileText className="w-3.5 h-3.5" />
                            <span>View PDF</span>
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

