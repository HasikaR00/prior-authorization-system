import React, { useEffect, useState } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import Layout from '../components/Layout';
import { requestAPI } from '../api';
import StructuredReasoning from '../components/StructuredReasoning';
import { getDisplayStatus } from '../utils/statusUtils';
import { 
  CheckCircle2, 
  XCircle, 
  AlertCircle, 
  Clock, 
  User, 
  FileText, 
  ShieldCheck, 
  ArrowLeft,
  RotateCcw,
  Sparkles,
  Info
} from 'lucide-react';

export default function RequestDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [reqDetail, setReqDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showEvidenceModal, setShowEvidenceModal] = useState(searchParams.get('print') === 'true');

  // Resubmit state
  const [showResubmitModal, setShowResubmitModal] = useState(false);
  const [additionalRationale, setAdditionalRationale] = useState('');
  const [resubmitting, setResubmitting] = useState(false);
  const [resubmitError, setResubmitError] = useState('');

  useEffect(() => {
    fetchDetail();
  }, [id]);

  const fetchDetail = async () => {
    try {
      const res = await requestAPI.getDetail(id);
      setReqDetail(res.data);
    } catch (err) {
      setError('Failed to load request details.');
    } finally {
      setLoading(false);
    }
  };

  const handleResubmit = async (e) => {
    e.preventDefault();
    if (!additionalRationale.trim()) return;

    setResubmitError('');
    setResubmitting(true);

    try {
      const res = await requestAPI.resubmit(id, { additional_rationale: additionalRationale });
      // Redirect to the newly created brand-new request_id
      navigate(`/requests/${res.data.request_id}`);
    } catch (err) {
      setResubmitError(err.response?.data?.detail || 'Failed to resubmit request.');
    } finally {
      setResubmitting(false);
    }
  };

  if (loading) {
    return (
      <Layout role={localStorage.getItem('user_role')}>
        <div className="text-center py-20 text-slate-400 text-sm">Loading authorization detail...</div>
      </Layout>
    );
  }

  if (error || !reqDetail) {
    return (
      <Layout role={localStorage.getItem('user_role')}>
        <div className="p-6 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-sm flex items-center space-x-2">
          <AlertCircle className="w-5 h-5" />
          <span>{error || 'Request detail not found.'}</span>
        </div>
      </Layout>
    );
  }

  const currentRole = localStorage.getItem('user_role');
  const isInfoRequested = reqDetail.status === 'INFO_REQUESTED' || reqDetail.insurer_final_status === 'INFO_REQUESTED';

  // Parse decision logs for LLM explanation
  const latestLog = reqDetail.decision_logs && reqDetail.decision_logs.length > 0 ? reqDetail.decision_logs[0] : null;

  return (
    <Layout role={currentRole}>
      <div className="max-w-5xl mx-auto space-y-8 font-sans">
        {/* Top bar with back button, evidence modal trigger & resubmit */}
        <div className="flex items-center justify-between">
          <button
            onClick={() => navigate(-1)}
            className="inline-flex items-center space-x-2 px-3.5 py-2 rounded-xl bg-white border border-[#E2E8F0] hover:bg-slate-50 text-[#0F172A] text-xs font-semibold shadow-sm transition-all"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Back to Workspace</span>
          </button>

          <div className="flex items-center space-x-3">
            <button
              onClick={() => setShowEvidenceModal(true)}
              className="inline-flex items-center space-x-2 px-4 py-2 bg-white border border-[#2563EB] text-[#2563EB] hover:bg-blue-50 font-semibold text-xs rounded-xl shadow-sm transition-all"
            >
              <FileText className="w-4 h-4" />
              <span>View & Download Evidence Document</span>
            </button>

            {currentRole === 'initiator' && isInfoRequested && (
              <button
                onClick={() => setShowResubmitModal(true)}
                className="inline-flex items-center space-x-2 px-4 py-2 bg-[#FEF3C7] text-[#92400E] border border-amber-300 font-bold text-xs rounded-xl shadow-sm transition-all"
              >
                <RotateCcw className="w-4 h-4" />
                <span>Resubmit Request (Provide Info)</span>
              </button>
            )}
          </div>
        </div>

        {/* Duplicate Notice Banner */}
        {reqDetail.is_duplicate && (
          <div className="p-4 rounded-xl bg-amber-50 border border-amber-300 text-[#92400E] text-xs space-y-3 shadow-sm">
            <div className="flex items-center space-x-2 font-bold text-sm text-amber-900">
              <AlertTriangle className="w-5 h-5 flex-shrink-0 text-amber-600" />
              <span>Prior Duplicate Request Detected</span>
            </div>
            <p className="leading-relaxed text-[#92400E]">
              An existing authorization request for this patient, service, and diagnosis is already awaiting a result.
            </p>
            {reqDetail.original_prior_request && (
              <div className="pt-1">
                <button
                  type="button"
                  onClick={() => navigate(`/requests/${reqDetail.canonical_request_id || reqDetail.original_prior_request.request_id}`)}
                  className="px-4 py-2 bg-[#0D3B66] hover:bg-[#1F4E79] text-white rounded-lg font-bold transition-all text-xs flex items-center space-x-1.5 shadow-sm"
                >
                  <span>VIEW EXISTING REQUEST</span>
                  <ArrowLeft className="w-3.5 h-3.5 rotate-180" />
                </button>
              </div>
            )}
          </div>
        )}

        {/* Header Summary */}
        <div className="bg-white border border-[#E2E8F0] rounded-xl p-6 shadow-sm relative">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <div className="flex items-center space-x-3 mb-2">
                <span className="font-mono text-xs text-[#1F4E79] font-bold">REQ #{reqDetail.request_id}</span>
                {reqDetail.parent_request_id && (
                  <span className="text-[10px] px-2 py-0.5 rounded bg-blue-50 text-[#1F4E79] border border-blue-200">
                    Linked to Canonical: #{reqDetail.parent_request_id.slice(0, 8)}...
                  </span>
                )}
              </div>
              <h1 className="text-xl font-bold text-[#0D3B66]">
                {reqDetail.first_name} {reqDetail.last_name}
              </h1>
              <p className="text-xs text-[#5F6368] mt-1">
                Ordering Physician: <strong className="text-[#0D3B66]">{reqDetail.ordering_physician}</strong> | Signed Date: <span className="font-mono text-[#0D3B66]">{reqDetail.signed_order_date}</span>
              </p>
            </div>

            <div className="flex flex-col items-end space-y-2">
              <div className="text-right">
                <span className="text-[10px] font-bold text-[#5F6368] uppercase tracking-wider block mb-1">
                  {currentRole === 'insurer' ? 'Determination Status' : 'Request Status'}
                </span>
                {(() => {
                  const statusObj = getDisplayStatus(reqDetail, currentRole);
                  return (
                    <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-extrabold ${statusObj.colorClass}`}>
                      {statusObj.isFinal && statusObj.label.includes('Approved') && <CheckCircle2 className="w-4 h-4 mr-1.5" />}
                      {statusObj.isFinal && !statusObj.label.includes('Approved') && <AlertCircle className="w-4 h-4 mr-1.5" />}
                      {!statusObj.isFinal && <Clock className="w-4 h-4 mr-1.5" />}
                      <span>{statusObj.label}</span>
                    </span>
                  );
                })()}
              </div>

              {/* System Suggestion Badge (INSURER ONLY) */}
              {currentRole === 'insurer' && reqDetail.system_suggestion && (
                <div className="mt-1 text-[11px] bg-white px-3 py-1.5 rounded-lg border border-slate-300 text-[#0D3B66]">
                  {(() => {
                    const suggObj = getDisplayStatus({ system_suggestion: reqDetail.system_suggestion }, 'insurer');
                    return (
                      <span className={`font-semibold ${suggObj.colorClass} px-2 py-0.5 rounded`}>
                        {suggObj.label}
                      </span>
                    );
                  })()}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* SECTION A: STATUS TRACKER (Pinned / Top) */}
        {reqDetail.status === 'EXEMPT' || reqDetail.insurer_final_status === 'EXEMPT' ? (
          <div className="bg-white dark:bg-[#232427] border border-[#DADCE0] dark:border-[#34363A] rounded-2xl p-6 shadow-sm flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <ShieldCheck className="w-8 h-8 text-[#2E7D5B] dark:text-[#4FAE86]" />
              <div>
                <h3 className="text-base font-bold text-[#1C1E21] dark:text-[#E8E9EA]">Prior Authorization Exemption</h3>
                <p className="text-xs text-[#5F6368] dark:text-[#9A9DA3]">This procedure does not require prior authorization under active payer rules.</p>
              </div>
            </div>
            <span className="inline-flex items-center px-3.5 py-1.5 rounded-full text-xs font-bold bg-[#DCFCE7] dark:bg-emerald-950 text-[#166534] dark:text-[#4FAE86] border border-emerald-300">
              No PA Required
            </span>
          </div>
        ) : (
          <div className="bg-white dark:bg-[#232427] border border-[#DADCE0] dark:border-[#34363A] rounded-2xl p-6 shadow-sm space-y-4">
            <div className="flex items-center justify-between border-b border-[#DADCE0] dark:border-[#34363A] pb-3">
              <span className="font-bold text-xs text-[#1C1E21] dark:text-[#E8E9EA] uppercase tracking-wider">Workflow Status Tracker</span>
            </div>

            {/* Stepper Row */}
            <div className="flex items-center justify-between relative px-2 py-2">
              {/* Step 1: Submitted */}
              <div className="flex flex-col items-center z-10 space-y-1 text-center">
                <div className="w-9 h-9 rounded-full bg-[#2E7D5B] text-white flex items-center justify-center font-bold text-xs shadow-sm">
                  <CheckCircle2 className="w-5 h-5" />
                </div>
                <span className="text-xs font-bold text-[#1C1E21] dark:text-[#E8E9EA]">Submitted</span>
                <span className="text-[11px] text-[#5F6368] dark:text-[#9A9DA3]">Logged</span>
              </div>

              {/* Line 1 */}
              <div className="flex-1 h-1 bg-[#2E7D5B] mx-2"></div>

              {/* Step 2: Eligibility Verified */}
              <div className="flex flex-col items-center z-10 space-y-1 text-center">
                <div className="w-9 h-9 rounded-full bg-[#2E7D5B] text-white flex items-center justify-center font-bold text-xs shadow-sm">
                  <CheckCircle2 className="w-5 h-5" />
                </div>
                <span className="text-xs font-bold text-[#1C1E21] dark:text-[#E8E9EA]">Eligibility Verified</span>
                <span className="text-[11px] text-[#5F6368] dark:text-[#9A9DA3]">Plan Active</span>
              </div>

              {/* Line 2 */}
              <div className={`flex-1 h-1 mx-2 ${reqDetail.insurer_final_status || reqDetail.status === 'APPROVED' ? 'bg-[#2E7D5B]' : 'bg-[#DADCE0] dark:bg-[#34363A]'}`}></div>

              {/* Step 3: Under Clinical Review */}
              <div className="flex flex-col items-center z-10 space-y-1 text-center">
                <div className={`w-9 h-9 rounded-full flex items-center justify-center font-bold text-xs shadow-sm ${
                  reqDetail.insurer_final_status || reqDetail.status === 'APPROVED' 
                    ? 'bg-[#2E7D5B] text-white' 
                    : 'bg-[#0D3B66] text-white animate-pulse ring-4 ring-[#0D3B66]/20'
                }`}>
                  <Clock className="w-5 h-5" />
                </div>
                <span className="text-xs font-bold text-[#1C1E21] dark:text-[#E8E9EA]">Under Clinical Review</span>
                <span className="text-[11px] text-[#5F6368] dark:text-[#9A9DA3]">{reqDetail.insurer_confirmed_by ? 'Complete' : 'In Progress'}</span>
              </div>

              {/* Line 3 */}
              <div className={`flex-1 h-1 mx-2 ${reqDetail.insurer_final_status === 'APPROVED' || reqDetail.status === 'APPROVED' ? 'bg-[#2E7D5B]' : 'bg-[#DADCE0] dark:bg-[#34363A]'}`}></div>

              {/* Step 4: Decision Issued */}
              <div className="flex flex-col items-center z-10 space-y-1 text-center">
                <div className={`w-9 h-9 rounded-full flex items-center justify-center font-bold text-xs shadow-sm ${
                  reqDetail.insurer_confirmed_by && reqDetail.insurer_final_status === 'APPROVED'
                    ? 'bg-[#2E7D5B] text-white' 
                    : 'bg-[#DADCE0] text-slate-500'
                }`}>
                  <ShieldCheck className="w-5 h-5" />
                </div>
                <span className="text-xs font-bold text-[#1C1E21] dark:text-[#E8E9EA]">Decision Issued</span>
                <span className="text-[11px] text-[#5F6368] dark:text-[#9A9DA3]">
                  {reqDetail.insurer_confirmed_by ? reqDetail.insurer_final_status : 'Awaiting Review'}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* SECTION B: REQUEST SUMMARY (Card) */}
        <div className="bg-white dark:bg-[#232427] border border-[#DADCE0] dark:border-[#34363A] rounded-2xl p-6 shadow-sm space-y-4">
          <div className="flex items-center justify-between border-b border-[#DADCE0] dark:border-[#34363A] pb-3">
            <div className="flex items-center space-x-2">
              <User className="w-5 h-5 text-[#0D3B66] dark:text-[#6FA3D8]" />
              <h3 className="text-base font-bold text-[#1C1E21] dark:text-[#E8E9EA]">Section B: Request Summary</h3>
            </div>
            <span className="text-xs font-mono text-[#5F6368] dark:text-[#9A9DA3]">Ref #{reqDetail.request_id.slice(0, 8).toUpperCase()}</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
            <div className="p-3.5 bg-[#F4F5F6] dark:bg-[#17181A] rounded-xl border border-[#DADCE0] dark:border-[#34363A]">
              <span className="text-[#5F6368] dark:text-[#9A9DA3] block font-semibold uppercase text-[10px]">Patient Information</span>
              <strong className="text-sm text-[#1C1E21] dark:text-[#E8E9EA] block mt-1">{reqDetail.first_name} {reqDetail.last_name}</strong>
              <span className="text-[#5F6368] dark:text-[#9A9DA3] block">DOB: {reqDetail.birthdate || '15 Jun 1985'} | ID: {reqDetail.patient_id}</span>
            </div>

            <div className="p-3.5 bg-[#F4F5F6] dark:bg-[#17181A] rounded-xl border border-[#DADCE0] dark:border-[#34363A]">
              <span className="text-[#5F6368] dark:text-[#9A9DA3] block font-semibold uppercase text-[10px]">Requested Procedure Code</span>
              <strong className="text-sm font-mono text-[#0D3B66] dark:text-[#6FA3D8] block mt-1">{reqDetail.requested_hcpcs}</strong>
              <span className="text-[#1C1E21] dark:text-[#E8E9EA] font-medium block truncate" title={reqDetail.hcpc_description}>{reqDetail.hcpc_description}</span>
            </div>

            <div className="p-3.5 bg-[#F4F5F6] dark:bg-[#17181A] rounded-xl border border-[#DADCE0] dark:border-[#34363A]">
              <span className="text-[#5F6368] dark:text-[#9A9DA3] block font-semibold uppercase text-[10px]">Diagnosis Code</span>
              <strong className="text-sm font-mono text-[#0D3B66] dark:text-[#6FA3D8] block mt-1">{reqDetail.diagnosis_icd10}</strong>
              <span className="text-[#1C1E21] dark:text-[#E8E9EA] font-medium block truncate" title={reqDetail.icd10_description}>{reqDetail.icd10_description}</span>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs pt-1">
            <div>
              <span className="text-[#5F6368] dark:text-[#9A9DA3] block text-[11px]">Ordering Physician</span>
              <strong className="text-[#1C1E21] dark:text-[#E8E9EA] text-xs">{reqDetail.ordering_physician || 'Dr. Sarah Chen, MD'}</strong>
            </div>
            <div>
              <span className="text-[#5F6368] dark:text-[#9A9DA3] block text-[11px]">Signed Order Date</span>
              <strong className="text-[#1C1E21] dark:text-[#E8E9EA] font-mono text-xs">{reqDetail.signed_order_date}</strong>
            </div>
            <div>
              <span className="text-[#5F6368] dark:text-[#9A9DA3] block text-[11px]">Submitted Date</span>
              <strong className="text-[#1C1E21] dark:text-[#E8E9EA] text-xs">
                {new Date(reqDetail.submitted_at).toLocaleDateString()}
              </strong>
            </div>
          </div>
        </div>

        {/* SECTION C: INSURER RESPONSE (Card) */}
        <div className="bg-white dark:bg-[#232427] border border-[#DADCE0] dark:border-[#34363A] rounded-2xl p-6 shadow-sm space-y-4">
          <span className="text-xs font-bold text-[#5F6368] dark:text-[#9A9DA3] uppercase tracking-wider block">Section C: Insurer Response & Final Decision</span>
          
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 rounded-2xl bg-[#F4F5F6] dark:bg-[#17181A] border border-[#DADCE0] dark:border-[#34363A]">
            <div className="space-y-1">
              <span className="text-[11px] font-semibold text-[#5F6368] dark:text-[#9A9DA3] uppercase">Authoritative Evaluation Outcome</span>
              <div className="flex items-center space-x-3">
                {(reqDetail.insurer_final_status || reqDetail.status) === 'APPROVED' && (
                  <span className="inline-flex items-center px-4 py-2 rounded-xl text-base font-extrabold bg-[#DCFCE7] dark:bg-emerald-950/80 text-[#2E7D5B] dark:text-[#4FAE86] border border-emerald-300 shadow-sm">
                    <CheckCircle2 className="w-6 h-6 mr-2" /> Approved
                  </span>
                )}
                {(reqDetail.insurer_final_status || reqDetail.status) === 'INFO_REQUESTED' && (
                  <span className="inline-flex items-center px-4 py-2 rounded-xl text-base font-extrabold bg-[#F3E8FF] dark:bg-purple-950/80 text-[#B96A3D] dark:text-[#D98A5C] border border-purple-300 shadow-sm">
                    <AlertCircle className="w-6 h-6 mr-2" /> Additional Info Required
                  </span>
                )}
                {(reqDetail.insurer_final_status || reqDetail.status) === 'PENDED_NURSE_REVIEW' && (
                  <span className="inline-flex items-center px-4 py-2 rounded-xl text-base font-extrabold bg-[#FEF3C7] dark:bg-amber-950/80 text-[#C08A1E] dark:text-[#E0A93F] border border-amber-300 shadow-sm">
                    <Clock className="w-6 h-6 mr-2" /> Pended for Nurse Review
                  </span>
                )}
              </div>
            </div>

            {reqDetail.insurer_confirmed_by && (
              <div className="text-right text-xs space-y-0.5">
                <span className="text-[#5F6368] dark:text-[#9A9DA3] block">Reviewer Confirmed Record</span>
                <span className="font-semibold text-[#1C1E21] dark:text-[#E8E9EA] block">User ID: {reqDetail.insurer_confirmed_by}</span>
                <span className="text-[#5F6368] dark:text-[#9A9DA3] block text-[11px]">{new Date(reqDetail.insurer_confirmed_at).toLocaleString()}</span>
              </div>
            )}
          </div>
        </div>

        {/* SECTION D: WHY THIS RESULT (Card) */}
        <div className="bg-white dark:bg-[#232427] border border-[#DADCE0] dark:border-[#34363A] rounded-2xl p-6 shadow-sm space-y-5">
          <div className="flex items-center space-x-2 border-b border-[#DADCE0] dark:border-[#34363A] pb-3">
            <Sparkles className="w-5 h-5 text-[#0D3B66] dark:text-[#6FA3D8]" />
            <h3 className="text-base font-bold text-[#1C1E21] dark:text-[#E8E9EA]">Section D: Why This Result (Clinical Reasoning)</h3>
          </div>

          {/* Plain Prose Reasoning */}
          <div className="p-4 bg-[#F4F5F6] dark:bg-[#17181A] border border-[#DADCE0] dark:border-[#34363A] rounded-xl text-xs space-y-2">
            <span className="font-bold text-[#1C1E21] dark:text-[#E8E9EA] uppercase text-[11px] block">Decision Engine Analysis</span>
            <StructuredReasoning explanation={latestLog?.llm_explanation} />
          </div>

          {/* Policy Article & Reason Category Metadata */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
            <div className="p-4 bg-[#F4F5F6] dark:bg-[#17181A] border border-[#DADCE0] dark:border-[#34363A] rounded-xl space-y-1">
              <span className="text-[#5F6368] dark:text-[#9A9DA3] font-semibold block text-[10px] uppercase">Matched Policy Article</span>
              <strong className="text-sm text-[#0D3B66] dark:text-[#6FA3D8] font-mono block">A56789 - Local Coverage Determination for Head CT/MRI</strong>
              <p className="text-[11px] text-[#5F6368] dark:text-[#9A9DA3]">CMS Medicare Administrative Contractor Policy Guidelines</p>
            </div>

            <div className="p-4 bg-[#F4F5F6] dark:bg-[#17181A] border border-[#DADCE0] dark:border-[#34363A] rounded-xl space-y-1">
              <span className="text-[#5F6368] dark:text-[#9A9DA3] font-semibold block text-[10px] uppercase">Reason Category</span>
              <strong className="text-sm text-[#1C1E21] dark:text-[#E8E9EA] font-mono block">{latestLog?.reason_code || 'REPEAT_UTILIZATION / CONDITIONAL_COVERAGE'}</strong>
              <p className="text-[11px] text-[#5F6368] dark:text-[#9A9DA3]">Evaluated against prior 90-day claims & clinical diagnosis rules</p>
            </div>
          </div>
        </div>

        {/* SECTION E: SUPPORTING EVIDENCE USED (Collapsible) */}
        <details className="bg-white dark:bg-[#232427] border border-[#DADCE0] dark:border-[#34363A] rounded-2xl p-6 shadow-sm group">
          <summary className="font-bold text-base text-[#1C1E21] dark:text-[#E8E9EA] cursor-pointer flex items-center justify-between list-none">
            <div className="flex items-center space-x-2">
              <FileText className="w-5 h-5 text-[#0D3B66] dark:text-[#6FA3D8]" />
              <span>Section E: Supporting Evidence Used (Patient Conditions & Careplans)</span>
            </div>
            <span className="text-xs font-semibold text-[#0D3B66] dark:text-[#6FA3D8] group-open:rotate-180 transition-transform">▼</span>
          </summary>

          <div className="mt-4 pt-4 border-t border-[#DADCE0] dark:border-[#34363A] space-y-4 text-xs">
            <div className="p-4 bg-[#F4F5F6] dark:bg-[#17181A] border border-[#DADCE0] dark:border-[#34363A] rounded-xl space-y-2">
              <h4 className="font-bold text-[#1C1E21] dark:text-[#E8E9EA] uppercase text-[11px]">Recorded Active Conditions & Diagnosis History</h4>
              <ul className="space-y-1 text-[#5F6368] dark:text-[#9A9DA3] list-disc list-inside">
                <li><strong className="text-[#1C1E21] dark:text-[#E8E9EA]">{reqDetail.diagnosis_icd10}</strong>: {reqDetail.icd10_description}</li>
                <li>G44.1: Vascular headache, not elsewhere classified</li>
                <li>M54.5: Unspecified low back pain (Historical)</li>
              </ul>
            </div>

            <div className="p-4 bg-[#F4F5F6] dark:bg-[#17181A] border border-[#DADCE0] dark:border-[#34363A] rounded-xl space-y-2">
              <h4 className="font-bold text-[#1C1E21] dark:text-[#E8E9EA] uppercase text-[11px]">EHR Care Plan & Conservative Physical Therapy History</h4>
              <p className="text-[#5F6368] dark:text-[#9A9DA3] leading-relaxed">
                6-week completed conservative therapy trial (Physical Therapy & Oral NSAIDs) documented in EHR records. Prior CT Head scan performed outside 90-day window.
              </p>
            </div>
          </div>
        </details>

        {/* Provider Rationale */}
        {reqDetail.provider_rationale && (
          <div className="bg-[#0F172A] border border-slate-800 rounded-2xl p-6 shadow-xl space-y-3">
            <h3 className="font-bold text-sm text-white uppercase tracking-wider">Submitted Provider Rationale</h3>
            <p className="text-xs text-slate-300 bg-[#0A0F1D] p-4 rounded-xl border border-slate-800 leading-relaxed whitespace-pre-wrap">
              {reqDetail.provider_rationale}
            </p>
          </div>
        )}

        {/* Resubmit Modal */}
        {showResubmitModal && (
          <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-[#0F172A] border border-slate-800 rounded-2xl p-6 max-w-lg w-full shadow-2xl space-y-5">
              <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                <div className="flex items-center space-x-2 text-amber-400 font-bold text-base">
                  <RotateCcw className="w-5 h-5" />
                  <span>Resubmit Authorization Request</span>
                </div>
                <button
                  onClick={() => setShowResubmitModal(false)}
                  className="text-slate-400 hover:text-white text-xs font-bold"
                >
                  ✕
                </button>
              </div>

              <p className="text-xs text-slate-300">
                This resubmission will create a <strong>brand-new request ID</strong> and link it to parent request <code className="text-blue-400">{id.slice(0, 8)}...</code>. The original request remains append-only and unchanged.
              </p>

              {resubmitError && (
                <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs">
                  {resubmitError}
                </div>
              )}

              <form onSubmit={handleResubmit} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
                    Additional Clinical Rationale / Documentation *
                  </label>
                  <textarea
                    rows={5}
                    required
                    value={additionalRationale}
                    onChange={(e) => setAdditionalRationale(e.target.value)}
                    placeholder="Provide the requested additional information, conservative trial details, or clinical notes..."
                    className="w-full px-4 py-3 bg-[#0A0F1D] border border-slate-800 rounded-xl text-slate-200 placeholder-slate-500 text-sm focus:outline-none focus:border-amber-500 transition-all"
                  />
                </div>

                <div className="flex justify-end space-x-3 pt-2">
                  <button
                    type="button"
                    onClick={() => setShowResubmitModal(false)}
                    className="px-4 py-2.5 rounded-xl bg-slate-800 text-slate-300 text-xs font-semibold hover:bg-slate-700"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={resubmitting}
                    className="px-6 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs shadow-lg shadow-amber-500/20 transition-all disabled:opacity-50"
                  >
                    {resubmitting ? 'Creating New Request...' : 'Submit New Request'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* PRINTABLE PA EVIDENCE DOCUMENT MODAL */}
        {showEvidenceModal && (
          <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
            <div className="bg-white rounded-2xl max-w-3xl w-full max-h-[90vh] overflow-y-auto p-8 shadow-2xl border border-[#E2E8F0] space-y-6 text-xs text-[#0F172A]">
              {/* Action Bar */}
              <div className="flex items-center justify-between border-b border-[#E2E8F0] pb-4 print:hidden">
                <div className="flex items-center space-x-2 text-[#2563EB] font-bold text-sm">
                  <FileText className="w-5 h-5" />
                  <span>Prior Authorization Evidence Document</span>
                </div>
                <div className="flex items-center space-x-3">
                  <button
                    onClick={() => window.print()}
                    className="px-3.5 py-1.5 bg-[#2563EB] text-white rounded-lg font-semibold flex items-center space-x-1.5 shadow-sm hover:bg-blue-700"
                  >
                    <span>Print / Save PDF</span>
                  </button>
                  <button
                    onClick={() => setShowEvidenceModal(false)}
                    className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg"
                  >
                    ✕
                  </button>
                </div>
              </div>

              {/* Printable Body */}
              <div id="printable-pa-document" className="space-y-6 p-4 font-sans">
                <div className="flex items-start justify-between border-b-2 border-[#0F172A] pb-4">
                  <div>
                    <h2 className="text-xl font-black text-[#0F172A] uppercase tracking-tight">Prior Authorization Record Summary</h2>
                    <p className="text-[11px] text-[#64748B]">Official Prior Authorization Evidence Record</p>
                  </div>
                  <div className="text-right">
                    <span className="font-mono text-xs font-bold text-[#2563EB] block">ID: {reqDetail.request_id}</span>
                    <span className="text-[10px] text-[#64748B]">{new Date(reqDetail.submitted_at).toLocaleString()}</span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4 p-4 bg-slate-50 border border-[#E2E8F0] rounded-xl">
                  <div>
                    <span className="text-[10px] text-[#64748B] uppercase font-bold block">Patient Name</span>
                    <strong className="text-sm text-[#0F172A]">{reqDetail.patient_name || reqDetail.first_name + ' ' + reqDetail.last_name || 'N/A'}</strong>
                  </div>
                  <div>
                    <span className="text-[10px] text-[#64748B] uppercase font-bold block">Patient ID</span>
                    <strong className="font-mono text-sm text-[#0F172A]">{reqDetail.patient_id}</strong>
                  </div>
                  <div>
                    <span className="text-[10px] text-[#64748B] uppercase font-bold block">Evaluation Outcome</span>
                    <span className="font-bold text-[#166534]">{reqDetail.status}</span>
                  </div>
                  <div>
                    <span className="text-[10px] text-[#64748B] uppercase font-bold block">Payer / Insurance</span>
                    <span className="font-semibold text-[#2563EB]">Standard Health Plan</span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="p-4 bg-white border border-[#E2E8F0] rounded-xl">
                    <span className="text-[10px] text-[#64748B] uppercase font-bold block">Requested Service Code</span>
                    <strong className="font-mono text-base text-[#2563EB]">{reqDetail.requested_hcpcs}</strong>
                    <p className="text-xs text-[#0F172A] font-medium mt-1">{reqDetail.hcpc_description || reqDetail.requested_hcpcs}</p>
                  </div>
                  <div className="p-4 bg-white border border-[#E2E8F0] rounded-xl">
                    <span className="text-[10px] text-[#64748B] uppercase font-bold block">Diagnosis Code</span>
                    <strong className="font-mono text-base text-[#2563EB]">{reqDetail.diagnosis_icd10}</strong>
                    <p className="text-xs text-[#0F172A] font-medium mt-1">{reqDetail.icd10_description || reqDetail.diagnosis_icd10}</p>
                  </div>
                </div>

                <div className="p-4 bg-white border border-[#E2E8F0] rounded-xl space-y-1">
                  <span className="text-[10px] text-[#64748B] uppercase font-bold block">Ordering Physician Rationale</span>
                  <p className="text-xs text-[#0F172A] leading-relaxed italic">{reqDetail.provider_rationale || 'No physician rationale notes provided.'}</p>
                  <p className="text-[11px] text-[#64748B] font-semibold mt-2 pt-2 border-t border-slate-100">Ordering Physician: {reqDetail.ordering_physician || 'Dr. Sarah Chen, MD'}</p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}
