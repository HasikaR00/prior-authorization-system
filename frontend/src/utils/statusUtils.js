/**
 * Shared utility function for rendering prior authorization request status.
 * Provides user-friendly, professional healthcare terminology without AI tech jargon.
 * 
 * @param {Object} request - The request object (containing display_status, insurer_final_status, system_suggestion)
 * @param {string} viewerRole - 'initiator' | 'insurer'
 * @returns {Object} { label: string, colorClass: string, variant: 'solid' | 'outline' }
 */
export function getDisplayStatus(request, viewerRole = 'initiator') {
  if (!request) {
    return {
      label: 'Awaiting Reviewer Action',
      colorClass: 'bg-amber-50 text-[#92400E] border border-amber-200',
      variant: 'solid',
      isFinal: false
    };
  }

  // 1. INITIATOR SIDE: Reflects final decision or Awaiting Insurer Review
  if (viewerRole === 'initiator') {
    const isConfirmed = !!request.insurer_confirmed_by;
    const status = isConfirmed ? (request.insurer_final_status || request.display_status) : (request.display_status === 'AWAITING_REVIEW' ? 'AWAITING_REVIEW' : request.display_status);
    
    if (!isConfirmed || !status || status === 'AWAITING_REVIEW') {
      return {
        label: 'Awaiting Reviewer Action',
        colorClass: 'bg-amber-50 text-[#92400E] border border-amber-200',
        variant: 'solid',
        isFinal: false
      };
    }

    switch (status) {
      case 'APPROVED':
        return {
          label: 'APPROVED',
          colorClass: 'bg-emerald-50 text-[#166534] border border-emerald-200',
          variant: 'solid',
          isFinal: true
        };
      case 'DENIED':
        return {
          label: 'DENIED',
          colorClass: 'bg-red-50 text-[#991B1B] border border-red-200',
          variant: 'solid',
          isFinal: true
        };
      case 'PENDED_NURSE_REVIEW':
        return {
          label: 'PEND FOR REVIEW',
          colorClass: 'bg-amber-50 text-[#92400E] border border-amber-200',
          variant: 'solid',
          isFinal: true
        };
      case 'INFO_REQUESTED':
        return {
          label: 'NEED MORE INFORMATION',
          colorClass: 'bg-purple-50 text-[#6B21A8] border border-purple-200',
          variant: 'solid',
          isFinal: true
        };
      default:
        return {
          label: status,
          colorClass: 'bg-blue-50 text-[#0D3B66] border border-blue-200',
          variant: 'solid',
          isFinal: true
        };
    }
  }

  // 2. INSURER SIDE: Final status or recommendation
  const finalStatus = request.insurer_final_status || (request.insurer_confirmed_by ? request.display_status : null);

  if (finalStatus && finalStatus !== 'AWAITING_REVIEW') {
    switch (finalStatus) {
      case 'APPROVED':
        return {
          label: 'APPROVED',
          colorClass: 'bg-emerald-100 text-[#166534] border border-emerald-300 font-bold',
          variant: 'solid',
          isFinal: true
        };
      case 'DENIED':
        return {
          label: 'DENIED',
          colorClass: 'bg-red-100 text-[#991B1B] border border-red-300 font-bold',
          variant: 'solid',
          isFinal: true
        };
      case 'PENDED_NURSE_REVIEW':
        return {
          label: 'PEND FOR REVIEW',
          colorClass: 'bg-amber-100 text-[#92400E] border border-amber-300 font-bold',
          variant: 'solid',
          isFinal: true
        };
      case 'INFO_REQUESTED':
        return {
          label: 'NEED MORE INFORMATION',
          colorClass: 'bg-purple-100 text-[#6B21A8] border border-purple-300 font-bold',
          variant: 'solid',
          isFinal: true
        };
      default:
        return {
          label: finalStatus,
          colorClass: 'bg-blue-50 text-[#0D3B66] border border-blue-200',
          variant: 'solid',
          isFinal: true
        };
    }
  }

  // Recommended Action formatting (Outlined badge)
  const suggestion = request.system_suggestion || request.status;
  switch (suggestion) {
    case 'APPROVED':
      return {
        label: 'Recommended Action: APPROVE',
        colorClass: 'bg-emerald-50 text-[#166534] border border-emerald-300 font-semibold',
        variant: 'outline',
        isFinal: false
      };
    case 'PENDED_NURSE_REVIEW':
      return {
        label: 'Recommended Action: PEND FOR REVIEW',
        colorClass: 'bg-amber-50 text-[#92400E] border border-amber-300 font-semibold',
        variant: 'outline',
        isFinal: false
      };
    case 'INFO_REQUESTED':
      return {
        label: 'Recommended Action: NEED MORE INFORMATION',
        colorClass: 'bg-purple-50 text-[#6B21A8] border border-purple-300 font-semibold',
        variant: 'outline',
        isFinal: false
      };
    default:
      return {
        label: 'Recommended Action: PEND FOR REVIEW',
        colorClass: 'bg-amber-50 text-[#92400E] border border-amber-300 font-semibold',
        variant: 'outline',
        isFinal: false
      };
  }
}
