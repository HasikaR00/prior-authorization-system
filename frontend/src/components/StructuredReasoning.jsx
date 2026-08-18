import React from 'react';
import { 
  CheckCircle2, 
  AlertCircle, 
  Info, 
  FileCheck, 
  HelpCircle,
  Stethoscope,
  XCircle,
  Clock,
  ChevronRight,
  FileText
} from 'lucide-react';

const REASON_TYPE_MAP = {
  CRITERIA_MET: "Meets coverage criteria",
  CRITERIA_NOT_MET: "Does not meet coverage criteria",
  DOCUMENTATION_GAP: "Missing required clinical documentation",
  MISSING_CLINICAL_RATIONALE: "Missing required clinical documentation",
  NO_PATIENT_HISTORY: "Missing required clinical documentation",
  RULE_NOT_FOUND: "No active policy match found — manual review required",
  NO_ACTIVE_POLICY_MATCH: "No active policy match found — manual review required",
  REPEAT_UTILIZATION: "Similar service recently performed",
  NONCOVERED_DIAGNOSIS: "Diagnosis listed as non-covered",
  PA_NOT_REQUIRED: "Prior authorization not required"
};

function renderMarkdownText(text) {
  if (!text) return null;
  const parts = text.split(/(\*\*.*?\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i} className="font-bold text-[#0D3B66]">{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

export default function StructuredReasoning({ explanation }) {
  if (!explanation) {
    return (
      <div className="p-4 bg-white border border-[#E2E8F0] rounded-xl text-[#5F6368] text-xs italic shadow-sm">
        Recommendation evaluated based on active medical policy rules.
      </div>
    );
  }

  if (typeof explanation === 'string') {
    try {
      const parsed = JSON.parse(explanation);
      return <StructuredReasoning explanation={parsed} />;
    } catch (e) {
      return (
        <div className="p-4 bg-white border border-[#E2E8F0] rounded-xl text-[#1E293B] text-xs leading-relaxed font-sans whitespace-pre-wrap shadow-sm">
          {explanation}
        </div>
      );
    }
  }

  const plainSummary = explanation.plain_summary || explanation.decision_summary || explanation.summary || explanation.decision_explanation;
  const keyFindings = explanation.key_findings || [];
  const reasonCode = explanation._authoritative_reason || explanation.reason_type;
  const reasonLabel = REASON_TYPE_MAP[reasonCode] || reasonCode;
  const status = explanation._authoritative_status || explanation.status || "PENDED_NURSE_REVIEW";

  const policyEvidence = explanation.policy_evidence || [];
  const patientEvidence = explanation.patient_clinical_evidence || explanation.evidence_used || [];
  const missingInfo = explanation.missing_information || [];
  const reviewNote = explanation.human_review_note;

  const getStatusBannerStyle = (stat) => {
    switch (stat) {
      case 'APPROVED':
        return {
          bg: 'bg-emerald-50',
          border: 'border-emerald-200',
          text: 'text-[#166534]',
          icon: <CheckCircle2 className="w-5 h-5 text-[#166534]" />,
          label: 'Recommended Action: APPROVE'
        };
      case 'DENIED':
        return {
          bg: 'bg-red-50',
          border: 'border-red-200',
          text: 'text-[#991B1B]',
          icon: <XCircle className="w-5 h-5 text-[#991B1B]" />,
          label: 'Recommended Action: DENIED'
        };
      case 'INFO_REQUESTED':
        return {
          bg: 'bg-purple-50',
          border: 'border-purple-200',
          text: 'text-[#6B21A8]',
          icon: <AlertCircle className="w-5 h-5 text-[#6B21A8]" />,
          label: 'Recommended Action: NEED MORE INFORMATION'
        };
      default:
        return {
          bg: 'bg-amber-50',
          border: 'border-amber-200',
          text: 'text-[#92400E]',
          icon: <Clock className="w-5 h-5 text-[#92400E]" />,
          label: 'Recommended Action: PEND FOR REVIEW'
        };
    }
  };

  const banner = getStatusBannerStyle(status);

  return (
    <div className="space-y-4 font-sans text-xs">
      {/* 1. Recommended Action Banner */}
      <div className={`p-4 rounded-xl border ${banner.bg} ${banner.border} shadow-sm flex items-start justify-between`}>
        <div className="flex items-center space-x-3">
          {banner.icon}
          <div>
            <h4 className={`font-bold text-sm ${banner.text}`}>{banner.label}</h4>
            {reasonLabel && (
              <p className={`text-xs ${banner.text} opacity-90 font-medium mt-0.5`}>{reasonLabel}</p>
            )}
          </div>
        </div>
      </div>

      {/* 2. Plain Decision Reasoning Card */}
      {plainSummary && (
        <div className="p-4 rounded-xl bg-white border border-[#E2E8F0] text-[#1E293B] space-y-1.5 shadow-sm">
          <div className="flex items-center space-x-2 text-[#1F4E79] font-bold text-xs uppercase tracking-wider">
            <FileText className="w-4 h-4 text-[#1F4E79]" />
            <span>Explanation</span>
          </div>
          <p className="text-[#1E293B] text-xs leading-relaxed font-normal pt-1">
            {plainSummary}
          </p>
        </div>
      )}

      {/* 3. Key Findings */}
      {keyFindings.length > 0 && (
        <div className="p-4 rounded-xl bg-white border border-[#E2E8F0] space-y-2.5 shadow-sm">
          <h5 className="font-bold text-xs text-[#0D3B66] uppercase tracking-wider flex items-center space-x-1.5">
            <Info className="w-4 h-4 text-[#1F4E79]" />
            <span>Clinical Findings</span>
          </h5>
          <ul className="space-y-1.5 text-[#334155]">
            {keyFindings.map((finding, idx) => (
              <li key={idx} className="flex items-start space-x-2 leading-relaxed bg-slate-50 p-2 rounded-lg border border-slate-200">
                <ChevronRight className="w-3.5 h-3.5 text-[#1F4E79] flex-shrink-0 mt-0.5" />
                <span>{renderMarkdownText(finding)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 4. Policy & Clinical Evidence Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {policyEvidence.length > 0 && (
          <div className="p-4 bg-white border border-[#E2E8F0] rounded-xl space-y-2 shadow-sm">
            <div className="flex items-center space-x-2 text-[#166534] font-bold text-[11px] uppercase tracking-wider">
              <FileCheck className="w-4 h-4" />
              <span>Policy Coverage Criteria</span>
            </div>
            <ul className="space-y-1 text-[#334155]">
              {policyEvidence.map((item, idx) => (
                <li key={idx} className="leading-normal flex items-start space-x-1.5">
                  <span className="text-[#166534] font-bold">•</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {patientEvidence.length > 0 && (
          <div className="p-4 bg-white border border-[#E2E8F0] rounded-xl space-y-2 shadow-sm">
            <div className="flex items-center space-x-2 text-[#1F4E79] font-bold text-[11px] uppercase tracking-wider">
              <Stethoscope className="w-4 h-4" />
              <span>Clinical Evidence Evaluated</span>
            </div>
            <ul className="space-y-1 text-[#334155]">
              {patientEvidence.map((item, idx) => (
                <li key={idx} className="leading-normal flex items-start space-x-1.5">
                  <span className="text-[#1F4E79] font-bold">•</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* 5. Missing Information */}
      {missingInfo.length > 0 && (
        <div className="p-4 bg-purple-50/70 border border-purple-200 rounded-xl space-y-2 shadow-sm">
          <div className="flex items-center space-x-2 text-[#6B21A8] font-bold text-[11px] uppercase tracking-wider">
            <HelpCircle className="w-4 h-4" />
            <span>Required Documentation Gaps</span>
          </div>
          <ul className="space-y-1 text-[#6B21A8]">
            {missingInfo.map((item, idx) => (
              <li key={idx} className="leading-normal flex items-start space-x-1.5">
                <span className="font-bold">•</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 6. Reviewer Guidance Note */}
      {reviewNote && (
        <div className="p-4 bg-slate-50 border border-[#E2E8F0] rounded-xl text-[#1E293B] space-y-1 shadow-sm">
          <span className="text-[10px] font-semibold text-[#5F6368] uppercase block">Reviewer Guidance Note:</span>
          <p className="text-[#334155]">{reviewNote}</p>
        </div>
      )}
    </div>
  );
}
