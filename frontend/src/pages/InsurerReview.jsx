import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Layout from '../components/Layout';
import { requestAPI, reviewAPI } from '../api';
import { getDisplayStatus } from '../utils/statusUtils';
import { 
  ShieldCheck, 
  CheckCircle2, 
  XCircle, 
  AlertCircle, 
  Clock, 
  ArrowLeft,
  FileText,
  AlertTriangle,
  Send,
  Lock,
  Sparkles
} from 'lucide-react';
import StructuredReasoning from '../components/StructuredReasoning';

export default function InsurerReview() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [reqDetail, setReqDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Action & override form state
  const [selectedAction, setSelectedAction] = useState('APPROVED'); // APPROVED, PENDED_NURSE_REVIEW, INFO_REQUESTED, DENIED
  const [overrideNote, setOverrideNote] = useState('');
  const [submittingAction, setSubmittingAction] = useState(false);
  const [actionError, setActionError] = useState('');

  useEffect(() => {
    fetchDetail();
  }, [id]);

  const fetchDetail = async () => {
    try {
      const res = await requestAPI.getDetail(id);
      setReqDetail(res.data);
      if (res.data.system_suggestion || res.data.status) {
        setSelectedAction(res.data.system_suggestion || res.data.status);
      }
    } catch (err) {
      setError('Failed to fetch request detail for review.');
    } finally {
      setLoading(false);
    }
  };

  const isOverride = reqDetail && selectedAction !== (reqDetail.system_suggestion || reqDetail.status);
  const isSubmitDisabled = isOverride && (!overrideNote || !overrideNote.trim());

  const handleConfirm = async (e) => {
    e.preventDefault();
    setActionError('');

    if (isOverride && (!overrideNote || !overrideNote.trim())) {
      setActionError('An override note is mandatory whenever changing the decision from the recommended action.');
      return;
    }

    setSubmittingAction(true);

    try {
      await reviewAPI.confirm(id, {
        final_status: selectedAction,
        note: overrideNote,
      });

      navigate('/queue');
    } catch (err) {
      setActionError(err.response?.data?.detail || 'Failed to submit reviewer action.');
    } finally {
      setSubmittingAction(false);
    }
  };

  if (loading) {
    return (
      <Layout role="insurer">
        <div className="text-center py-20 text-slate-500 text-sm">Loading request details...</div>
      </Layout>
    );
  }

  if (error || !reqDetail) {
    return (
      <Layout role="insurer">
        <div className="p-6 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm flex items-center space-x-2">
          <AlertCircle className="w-5 h-5" />
          <span>{error || 'Request detail not found.'}</span>
        </div>
      </Layout>
    );
  }

  const latestLog = reqDetail.decision_logs && reqDetail.decision_logs.length > 0 ? reqDetail.decision_logs[0] : null;
  const suggestionObj = getDisplayStatus({ system_suggestion: reqDetail.system_suggestion || reqDetail.status }, 'insurer');

  return (
    <Layout role="insurer">
      <div className="max-w-5xl mx-auto space-y-6 font-sans">
        {/* Top Navigation */}
        <button
          onClick={() => navigate('/queue')}
          className="inline-flex items-center space-x-2 px-3.5 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-[#0D3B66] text-xs font-semibold transition-colors border border-[#CBD2D9]"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Review Queue</span>
        </button>

        {/* Duplicate Request Notice */}
        {reqDetail.is_duplicate && (
          <div className="p-4 rounded-xl bg-amber-50 border border-amber-300 text-[#92400E] text-xs space-y-2 shadow-sm">
            <div className="flex items-center space-x-2 font-bold text-sm">
              <AlertTriangle className="w-5 h-5 flex-shrink-0 text-amber-600" />
              <span>Prior Duplicate Request Detected</span>
            </div>
            <p className="leading-relaxed">
              An unconfirmed authorization request for patient <strong className="font-mono">{reqDetail.patient_id.slice(0, 8)}...</strong> with code <strong className="font-mono">{reqDetail.requested_hcpcs}</strong> and diagnosis <strong className="font-mono">{reqDetail.diagnosis_icd10}</strong> is already in the queue.
            </p>
          </div>
        )}

        {/* SECTION 1: REQUEST DETAILS */}
        <div className="bg-white border border-[#E2E8F0] rounded-xl p-6 shadow-sm space-y-4">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-[#E2E8F0] pb-4">
            <div>
              <span className="text-xs text-[#3B7A99] font-bold uppercase tracking-wider block mb-1">
                Authorization Reference #{reqDetail.request_id.slice(0, 8).toUpperCase()}
              </span>
              <h1 className="text-xl font-bold text-[#0D3B66]">
                Patient: {reqDetail.first_name} {reqDetail.last_name}
              </h1>
              <p className="text-xs text-[#5F6368] mt-1">
                Ordering Physician: <strong className="text-[#0D3B66]">{reqDetail.ordering_physician}</strong> | Signed Date: <span className="font-mono">{reqDetail.signed_order_date}</span>
              </p>
            </div>

            <div className="bg-slate-50 border border-[#E2E8F0] p-3.5 rounded-xl text-right">
              <span className="text-[10px] font-bold text-[#5F6368] uppercase tracking-wider block mb-1">Authoritative Recommendation</span>
              <span className={`inline-flex items-center px-3 py-1 rounded-md text-xs font-bold ${suggestionObj.colorClass}`}>
                {suggestionObj.label}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-xs pt-2">
            <div>
              <span className="text-[#5F6368] block font-semibold uppercase text-[10px]">Patient Reference</span>
              <strong className="font-mono text-[#0D3B66]">{reqDetail.patient_id}</strong>
            </div>
            <div>
              <span className="text-[#5F6368] block font-semibold uppercase text-[10px]">Date of Birth / Gender</span>
              <span className="text-[#0D3B66] font-medium">{reqDetail.birthdate || 'N/A'} ({reqDetail.gender || 'U'})</span>
            </div>
            <div>
              <span className="text-[#5F6368] block font-semibold uppercase text-[10px]">State Jurisdiction</span>
              <span className="text-[#0D3B66] font-medium">{reqDetail.state || 'Massachusetts'}</span>
            </div>
            <div>
              <span className="text-[#5F6368] block font-semibold uppercase text-[10px]">Jurisdiction Status</span>
              <span className="inline-flex items-center px-2 py-0.5 rounded bg-emerald-50 text-emerald-800 border border-emerald-200 text-[11px] font-bold">
                Jurisdiction: MATCHED
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-3 border-t border-[#E2E8F0] text-xs">
            <div>
              <span className="text-[#5F6368] block font-semibold uppercase text-[10px]">Requested Service (HCPCS/CPT)</span>
              <strong className="font-mono text-[#1F4E79] text-sm block">{reqDetail.requested_hcpcs}</strong>
              <span className="text-xs text-[#334155] font-medium block mt-0.5">
                {reqDetail.hcpc_description || reqDetail.requested_hcpcs}
              </span>
            </div>
            <div>
              <span className="text-[#5F6368] block font-semibold uppercase text-[10px]">Diagnosis (ICD-10)</span>
              <strong className="font-mono text-[#1F4E79] text-sm block">{reqDetail.diagnosis_icd10}</strong>
              <span className="text-xs text-[#334155] font-medium block mt-0.5">
                {reqDetail.icd10_description || reqDetail.diagnosis_icd10}
              </span>
            </div>
          </div>

          {reqDetail.provider_rationale && (
            <div className="pt-3 border-t border-[#E2E8F0] text-xs">
              <span className="text-[#5F6368] font-bold uppercase text-[10px] block mb-1">Submitted Clinical Rationale</span>
              <div className="p-3 bg-slate-50 border border-[#E2E8F0] rounded-lg text-[#1E293B] leading-relaxed font-sans whitespace-pre-wrap">
                {reqDetail.provider_rationale}
              </div>
            </div>
          )}
        </div>

        {/* SECTION 2: AUTHORITATIVE RECOMMENDED ACTION & EXPLANATION */}
        <div className="bg-white border border-[#E2E8F0] rounded-xl p-6 shadow-sm space-y-4">
          <div className="flex items-center space-x-2 text-[#0D3B66] font-bold text-sm border-b border-[#E2E8F0] pb-3">
            <FileText className="w-4 h-4 text-[#1F4E79]" />
            <span>Recommended Action & Explanation</span>
          </div>

          <StructuredReasoning explanation={latestLog?.llm_explanation} />
        </div>

        {/* SECTION 3: REVIEW TRIAGE INFORMATION (SECONDARY ML SIGNAL) */}
        {reqDetail.ml_model_available && reqDetail.predicted_approval_prob !== null && reqDetail.predicted_approval_prob !== undefined && (
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-5 shadow-sm space-y-3">
            <div className="flex items-center justify-between border-b border-slate-200 pb-2">
              <div className="flex items-center space-x-2">
                <ShieldCheck className="w-4 h-4 text-[#3B7A99]" />
                <h3 className="text-xs font-bold text-[#0D3B66] uppercase tracking-wider">
                  REVIEW TRIAGE INFORMATION
                </h3>
              </div>
              {reqDetail.is_synthetic_model && (
                <span className="px-2 py-0.5 rounded bg-amber-50 text-amber-800 text-[10px] font-bold border border-amber-200 uppercase tracking-wider">
                  Demo / Synthetic Model
                </span>
              )}
            </div>
            
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <div className="text-xl font-bold text-[#0D3B66]">
                  ML Approval Likelihood: {Math.round(reqDetail.predicted_approval_prob * 100)}%
                </div>
                <p className="text-xs text-[#5F6368] mt-0.5">
                  Historical predictive likelihood estimate based on pre-adjudication features.
                </p>
              </div>
              <div className="text-xs text-[#5F6368] bg-white px-3 py-1.5 rounded-lg border border-[#CBD2D9] font-medium">
                Informational triage signal only
              </div>
            </div>
          </div>
        )}

        {/* SECTION 4: REVIEWER DETERMINATION ACTION FORM */}
        {reqDetail.insurer_confirmed_by ? (
          <div className="bg-white border border-[#E2E8F0] rounded-xl p-6 shadow-sm space-y-2">
            <div className="flex items-center space-x-2 text-[#0D3B66] font-bold text-sm">
              <CheckCircle2 className="w-5 h-5 text-[#2E7D5B]" />
              <span>Determination Record Finalized</span>
            </div>
            <p className="text-xs text-[#5F6368]">
              Final determination was completed by Reviewer <strong className="font-mono text-[#0D3B66]">{reqDetail.insurer_confirmed_by}</strong> on {new Date(reqDetail.insurer_confirmed_at).toLocaleString()}.
            </p>
          </div>
        ) : (
          <form onSubmit={handleConfirm} className="bg-white border border-[#E2E8F0] rounded-xl p-6 shadow-sm space-y-5">
            <div className="flex items-center justify-between border-b border-[#E2E8F0] pb-3">
              <div>
                <h3 className="font-bold text-sm text-[#0D3B66]">Reviewer Determination Form</h3>
                <p className="text-xs text-[#5F6368]">Select authorization action and provide mandatory notes for any override.</p>
              </div>

              {isOverride && (
                <span className="text-xs font-bold px-3 py-1 rounded bg-amber-50 text-[#92400E] border border-amber-200 flex items-center space-x-1">
                  <AlertTriangle className="w-3.5 h-3.5 mr-1 text-amber-600" />
                  <span>OVERRIDE SELECTION</span>
                </span>
              )}
            </div>

            {actionError && (
              <div className="p-3.5 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs flex items-center space-x-2">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                <span>{actionError}</span>
              </div>
            )}

            {/* Action Buttons */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <button
                type="button"
                onClick={() => setSelectedAction('APPROVED')}
                className={`p-3.5 rounded-xl border text-xs font-bold flex flex-col items-center justify-center space-y-1.5 transition-all ${
                  selectedAction === 'APPROVED'
                    ? 'bg-emerald-50 border-[#2E7D5B] text-[#166534] shadow-sm ring-1 ring-[#2E7D5B]'
                    : 'bg-slate-50 border-[#CBD2D9] text-[#5F6368] hover:bg-slate-100'
                }`}
              >
                <CheckCircle2 className="w-4 h-4" />
                <span>APPROVE</span>
              </button>

              <button
                type="button"
                onClick={() => setSelectedAction('PENDED_NURSE_REVIEW')}
                className={`p-3.5 rounded-xl border text-xs font-bold flex flex-col items-center justify-center space-y-1.5 transition-all ${
                  selectedAction === 'PENDED_NURSE_REVIEW'
                    ? 'bg-amber-50 border-[#C08A1E] text-[#92400E] shadow-sm ring-1 ring-[#C08A1E]'
                    : 'bg-slate-50 border-[#CBD2D9] text-[#5F6368] hover:bg-slate-100'
                }`}
              >
                <Clock className="w-4 h-4" />
                <span>PEND FOR REVIEW</span>
              </button>

              <button
                type="button"
                onClick={() => setSelectedAction('INFO_REQUESTED')}
                className={`p-3.5 rounded-xl border text-xs font-bold flex flex-col items-center justify-center space-y-1.5 transition-all ${
                  selectedAction === 'INFO_REQUESTED'
                    ? 'bg-purple-50 border-[#6B21A8] text-[#6B21A8] shadow-sm ring-1 ring-[#6B21A8]'
                    : 'bg-slate-50 border-[#CBD2D9] text-[#5F6368] hover:bg-slate-100'
                }`}
              >
                <AlertCircle className="w-4 h-4" />
                <span>NEED MORE INFORMATION</span>
              </button>
            </div>

            {/* Note Field */}
            <div>
              <label className="block text-xs font-bold text-[#0D3B66] uppercase tracking-wider mb-1.5">
                Reviewer Notes {isOverride ? <span className="text-[#92400E] font-bold">* (MANDATORY FOR OVERRIDE)</span> : '(Optional)'}
              </label>
              <textarea
                rows={3}
                value={overrideNote}
                onChange={(e) => setOverrideNote(e.target.value)}
                placeholder={isOverride ? 'Mandatory rationale for overriding recommended action...' : 'Optional reviewer notes...'}
                className={`w-full px-3.5 py-2.5 bg-white border rounded-xl text-[#1E293B] text-xs focus:outline-none transition-all ${
                  isOverride && (!overrideNote || !overrideNote.trim())
                    ? 'border-amber-400 focus:border-amber-500'
                    : 'border-[#CBD2D9] focus:border-[#1F4E79]'
                }`}
              />
              {isOverride && (!overrideNote || !overrideNote.trim()) && (
                <p className="text-[11px] text-amber-700 mt-1 font-semibold flex items-center">
                  <Lock className="w-3.5 h-3.5 mr-1 text-amber-600" /> Submit button is disabled until rationale note is provided.
                </p>
              )}
            </div>

            <div className="pt-3 border-t border-[#E2E8F0] flex justify-end">
              <button
                type="submit"
                disabled={submittingAction || isSubmitDisabled}
                className="px-6 py-2.5 bg-[#0D3B66] hover:bg-[#1F4E79] text-white font-bold text-xs rounded-xl shadow-sm transition-all flex items-center space-x-2 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Send className="w-3.5 h-3.5" />
                <span>{submittingAction ? 'Submitting Determination...' : 'Submit Determination'}</span>
              </button>
            </div>
          </form>
        )}
      </div>
    </Layout>
  );
}
