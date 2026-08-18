import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import Layout from '../components/Layout';
import { patientAPI, requestAPI, codeAPI } from '../api';

import {
  Search,
  User,
  Check,
  AlertCircle,
  Calendar,
  FileCheck,
  Stethoscope,
  ArrowRight,
  ArrowLeft,
  ShieldCheck,
  Building,
  Info,
  Save,
  FileText,
  Printer,
  Download,
  UploadCloud,
  X,
} from 'lucide-react';

const WIZARD_STEPS = [
  { id: 1, name: 'Patient & Insurance', icon: User },
  { id: 2, name: 'Requested Service', icon: FileCheck },
  { id: 3, name: 'Diagnosis Code', icon: Stethoscope },
  { id: 4, name: 'Ordering Physician', icon: Building },
  { id: 5, name: 'Clinical Rationale', icon: Info },
  { id: 6, name: 'Prior Records', icon: Calendar },
  { id: 7, name: 'Review & Submit', icon: ShieldCheck },
];

export default function NewRequest() {
  const navigate = useNavigate();

  const [currentStep, setCurrentStep] = useState(1);

  // ============================================================
  // PDF EXTRACTION STATE
  // ============================================================

  const [inputMode, setInputMode] = useState('manual');
  const [extractingPdf, setExtractingPdf] = useState(false);
  const [pdfSuccessMessage, setPdfSuccessMessage] = useState('');
  const [pdfErrorMessage, setPdfErrorMessage] = useState('');
  const [pdfExtractionMeta, setPdfExtractionMeta] = useState(null);


  // ============================================================
  // PATIENT
  // ============================================================

  const [patientIdInput, setPatientIdInput] = useState('');
  const [patientData, setPatientData] = useState(null);
  const [patientError, setPatientError] = useState('');
  const [loadingPatient, setLoadingPatient] = useState(false);

  // ============================================================
  // REQUEST FORM
  // ============================================================

  const [requestedHcpcs, setRequestedHcpcs] = useState('');
  const [diagnosisIcd10, setDiagnosisIcd10] = useState('');

  const [orderingPhysician, setOrderingPhysician] = useState('');
  const [signedOrderDate, setSignedOrderDate] = useState('');
  const [providerRationale, setProviderRationale] = useState('');
  const [encounterClass, setEncounterClass] = useState('ambulatory');

  // ============================================================
  // CUSTOM CODE INPUT
  // ============================================================

  const [customHcpcs, setCustomHcpcs] = useState('');
  const [customIcd10, setCustomIcd10] = useState('');

  const [isOtherHcpcs, setIsOtherHcpcs] = useState(false);
  const [isOtherIcd10, setIsOtherIcd10] = useState(false);

  // ============================================================
  // KB CODE LISTS
  // ============================================================

  const [hcpcsList, setHcpcsList] = useState([]);
  const [icd10List, setIcd10List] = useState([]);

  const [hcpcsSearch, setHcpcsSearch] = useState('');
  const [icd10Search, setIcd10Search] = useState('');

  const [loadingHcpcs, setLoadingHcpcs] = useState(false);
  const [loadingIcd10, setLoadingIcd10] = useState(false);

  // ============================================================
  // SUBMISSION
  // ============================================================

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

  // ============================================================
  // DRAFT / MODAL
  // ============================================================

  const [draftSavedToast, setDraftSavedToast] = useState(false);
  const [showEvidenceModal, setShowEvidenceModal] = useState(false);

  // ============================================================
  // INITIAL DATE
  // ============================================================

  useEffect(() => {
    if (!signedOrderDate) {
      setSignedOrderDate(new Date().toISOString().slice(0, 10));
    }
  }, [signedOrderDate]);

  // ============================================================
  // LOAD SAVED DRAFT
  // ============================================================

  useEffect(() => {
    const saved = localStorage.getItem('pa_request_draft');

    if (!saved) return;

    try {
      const parsed = JSON.parse(saved);

      if (parsed.patientData) {
        setPatientData(parsed.patientData);
      }

      if (parsed.patientIdInput) {
        setPatientIdInput(parsed.patientIdInput);
      }

      if (parsed.requestedHcpcs) {
        setRequestedHcpcs(parsed.requestedHcpcs);
      }

      if (parsed.diagnosisIcd10) {
        setDiagnosisIcd10(parsed.diagnosisIcd10);
      }

      if (parsed.orderingPhysician) {
        setOrderingPhysician(parsed.orderingPhysician);
      }

      if (parsed.signedOrderDate) {
        setSignedOrderDate(parsed.signedOrderDate);
      }

      if (parsed.providerRationale) {
        setProviderRationale(parsed.providerRationale);
      }

      if (parsed.encounterClass) {
        setEncounterClass(parsed.encounterClass);
      }

      if (parsed.customHcpcs) {
        setCustomHcpcs(parsed.customHcpcs);
      }

      if (parsed.customIcd10) {
        setCustomIcd10(parsed.customIcd10);
      }

      if (typeof parsed.isOtherHcpcs === 'boolean') {
        setIsOtherHcpcs(parsed.isOtherHcpcs);
      }

      if (typeof parsed.isOtherIcd10 === 'boolean') {
        setIsOtherIcd10(parsed.isOtherIcd10);
      }

      if (parsed.currentStep) {
        setCurrentStep(Math.min(7, Math.max(1, parsed.currentStep)));
      }
    } catch (error) {
      console.error('Failed to parse saved PA draft:', error);
    }
  }, []);

  // ============================================================
  // FETCH HCPCS
  // ============================================================

  useEffect(() => {
    fetchHcpcs(hcpcsSearch);
  }, [hcpcsSearch]);

  const fetchHcpcs = async (search = '') => {
    setLoadingHcpcs(true);

    try {
      const res = await codeAPI.getHcpcs(search, 5000);

      const incoming = Array.isArray(res.data) ? res.data : [];

      // Deduplicate by HCPCS code
      const unique = Array.from(
        new Map(
          incoming
            .filter((item) => item?.hcpc_code)
            .map((item) => [
              String(item.hcpc_code).trim().toUpperCase(),
              item,
            ])
        ).values()
      );

      setHcpcsList(unique);
    } catch (err) {
      console.error('Failed to load HCPCS codes from KB:', err);
      setHcpcsList([]);
    } finally {
      setLoadingHcpcs(false);
    }
  };

  // ============================================================
  // FETCH ICD-10
  // ============================================================

  useEffect(() => {
    if (!requestedHcpcs || isOtherHcpcs) {
      setIcd10List([]);
      return;
    }

    fetchIcd10(icd10Search, requestedHcpcs);
  }, [icd10Search, requestedHcpcs, isOtherHcpcs]);

  const fetchIcd10 = async (search = '', hcpcsCode = '') => {
    if (!hcpcsCode) return;

    setLoadingIcd10(true);

    try {
      const res = await codeAPI.getIcd10(search, hcpcsCode, 5000);

      const incoming = Array.isArray(res.data) ? res.data : [];

      // Deduplicate by ICD-10 code
      const unique = Array.from(
        new Map(
          incoming
            .filter((item) => item?.icd10_code)
            .map((item) => [
              String(item.icd10_code).trim().toUpperCase(),
              item,
            ])
        ).values()
      );

      setIcd10List(unique);
    } catch (err) {
      console.error('Failed to load ICD-10 codes from KB:', err);
      setIcd10List([]);
    } finally {
      setLoadingIcd10(false);
    }
  };

  // ============================================================
  // PATIENT SEARCH
  // ============================================================

  const handlePatientSearch = async (e, overrideId = null) => {
    if (e) e.preventDefault();

    const patientId = (overrideId || patientIdInput || '').trim();

    if (!patientId) {
      setPatientError('Please enter a Patient ID.');
      return;
    }

    setPatientError('');
    setLoadingPatient(true);
    setPatientData(null);

    try {
      const res = await patientAPI.getPatient(patientId);

      if (!res.data) {
        throw new Error('Patient record not found.');
      }

      setPatientData(res.data);
    } catch (err) {
      setPatientError(
        err.response?.data?.detail ||
        'Patient record not found. Please verify the Patient ID.'
      );
    } finally {
      setLoadingPatient(false);
    }
  };

  // ============================================================
  // PDF EXTRACTION HANDLER
  // ============================================================

  const handlePdfUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith('.pdf') && file.type !== 'application/pdf') {
      setPdfErrorMessage('Only PDF documents (.pdf) are supported for extraction.');
      return;
    }

    setPdfErrorMessage('');
    setPdfSuccessMessage('');
    setExtractingPdf(true);
    setPdfExtractionMeta(null);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const res = await requestAPI.extractPdf(formData);
      const data = res.data;

      if (!data.success) {
        setPdfErrorMessage(
          data.error ||
          "We couldn't extract information from this document. Please enter the information manually."
        );
        return;
      }

      const fields = data.fields || {};

      // 1. Patient ID
      if (fields.patient_id) {
        setPatientIdInput(fields.patient_id);
        handlePatientSearch(null, fields.patient_id);
      }

      // 2. Requested HCPCS
      if (fields.requested_hcpcs) {
        const code = fields.requested_hcpcs.trim().toUpperCase();
        setRequestedHcpcs(code);
        setHcpcsSearch(code);
      }

      // 3. Diagnosis ICD-10
      if (fields.diagnosis_icd10) {
        const code = fields.diagnosis_icd10.trim().toUpperCase();
        setDiagnosisIcd10(code);
        setIcd10Search(code);
      }

      // 4. Ordering Physician
      if (fields.ordering_provider) {
        setOrderingPhysician(fields.ordering_provider);
      }

      // 5. Signed Order Date
      if (fields.signed_order_date) {
        setSignedOrderDate(fields.signed_order_date);
      }

      // 6. Provider Rationale
      if (fields.clinical_rationale || fields.provider_rationale) {
        setProviderRationale(
          fields.clinical_rationale || fields.provider_rationale
        );
      }

      setPdfExtractionMeta({
        method: data.extraction_method || 'TEXT',
        ocr_used: data.ocr_used || false,
        extracted: data.fields_extracted || [],
        missing: data.fields_missing || [],
      });

      setPdfSuccessMessage(
        'Information extracted from your document. Please review the details before submitting.'
      );
    } catch (err) {
      console.error('PDF extraction failed:', err);
      setPdfErrorMessage(
        err.response?.data?.detail ||
        "We couldn't extract information from this document. Please enter the information manually."
      );
    } finally {
      setExtractingPdf(false);
    }
  };


  // ============================================================
  // CODE CHANGE HANDLERS
  // ============================================================

  const handleHcpcsChange = (value) => {
    if (value === 'OTHER') {
      setIsOtherHcpcs(true);
      setRequestedHcpcs('');

      // ICD-10 belongs to the selected HCPCS.
      // Clear it when switching to custom HCPCS.
      setDiagnosisIcd10('');
      setIsOtherIcd10(false);
      setCustomIcd10('');
      setIcd10List([]);

      return;
    }

    setIsOtherHcpcs(false);
    setCustomHcpcs('');

    const normalized = value.trim().toUpperCase();

    setRequestedHcpcs(normalized);

    // IMPORTANT:
    // ICD-10 selection must be refreshed for the newly selected HCPCS.
    setDiagnosisIcd10('');
    setIsOtherIcd10(false);
    setCustomIcd10('');
    setIcd10Search('');
    setIcd10List([]);
  };

  const handleIcd10Change = (value) => {
    if (value === 'OTHER') {
      setIsOtherIcd10(true);
      setDiagnosisIcd10('');
      return;
    }

    setIsOtherIcd10(false);
    setCustomIcd10('');

    setDiagnosisIcd10(value.trim().toUpperCase());
  };

  // ============================================================
  // FINAL VALUES
  // ============================================================

  const finalHcpcs = useMemo(() => {
    if (isOtherHcpcs) {
      return customHcpcs.trim().toUpperCase();
    }

    return requestedHcpcs.trim().toUpperCase();
  }, [isOtherHcpcs, customHcpcs, requestedHcpcs]);

  const finalIcd10 = useMemo(() => {
    if (isOtherIcd10) {
      return customIcd10.trim().toUpperCase();
    }

    return diagnosisIcd10.trim().toUpperCase();
  }, [isOtherIcd10, customIcd10, diagnosisIcd10]);

  // ============================================================
  // SELECTED KB OBJECTS
  // ============================================================

  const selectedHcpcsObj = useMemo(() => {
    if (!requestedHcpcs) return null;

    return (
      hcpcsList.find(
        (item) =>
          String(item?.hcpc_code || '').trim().toUpperCase() ===
          requestedHcpcs
      ) || null
    );
  }, [hcpcsList, requestedHcpcs]);

  const selectedIcd10Obj = useMemo(() => {
    if (!diagnosisIcd10) return null;

    return (
      icd10List.find(
        (item) =>
          String(item?.icd10_code || '').trim().toUpperCase() ===
          diagnosisIcd10
      ) || null
    );
  }, [icd10List, diagnosisIcd10]);

  // ============================================================
  // SAVE DRAFT
  // ============================================================

  const saveDraft = () => {
    const draftData = {
      patientData,
      patientIdInput,
      requestedHcpcs,
      diagnosisIcd10,
      orderingPhysician,
      signedOrderDate,
      providerRationale,
      encounterClass,
      customHcpcs,
      customIcd10,
      isOtherHcpcs,
      isOtherIcd10,
      currentStep,
      savedAt: new Date().toISOString(),
    };

    localStorage.setItem(
      'pa_request_draft',
      JSON.stringify(draftData)
    );

    setDraftSavedToast(true);

    setTimeout(() => {
      setDraftSavedToast(false);
    }, 3000);
  };

  // ============================================================
  // STEP VALIDATION
  // ============================================================

  const validateCurrentStep = () => {
    setSubmitError('');

    if (currentStep === 1) {
      if (!patientData) {
        setPatientError(
          'Please look up and select a valid patient before continuing.'
        );

        return false;
      }

      return true;
    }

    if (currentStep === 2) {
      if (!finalHcpcs || finalHcpcs.length < 3) {
        setSubmitError(
          'Please select or enter a valid requested HCPCS/CPT code.'
        );

        return false;
      }

      return true;
    }

    if (currentStep === 3) {
      if (!finalIcd10 || finalIcd10.length < 3) {
        setSubmitError(
          'Please select or enter a valid diagnosis ICD-10 code.'
        );

        return false;
      }

      return true;
    }

    if (currentStep === 4) {
      if (!orderingPhysician.trim()) {
        setSubmitError('Ordering physician is required.');
        return false;
      }

      if (!signedOrderDate) {
        setSubmitError('Signed order date is required.');
        return false;
      }

      return true;
    }

    if (currentStep === 5) {
      if (!providerRationale.trim()) {
        setSubmitError(
          'Please provide the clinical rationale before continuing.'
        );

        return false;
      }

      return true;
    }

    if (currentStep === 6) {
      if (!patientData) {
        setSubmitError(
          'Patient information is required before reviewing prior records.'
        );

        return false;
      }

      return true;
    }

    return true;
  };

  // ============================================================
  // NEXT STEP
  // ============================================================

  const handleNextStep = () => {
    if (!validateCurrentStep()) {
      return;
    }

    setSubmitError('');

    setCurrentStep((prev) => Math.min(7, prev + 1));
  };

  // ============================================================
  // SUBMIT
  // ============================================================

  const handleSubmit = async () => {
    if (!patientData) {
      setSubmitError(
        'Please complete Step 1 (Patient Lookup) first.'
      );
      return;
    }

    if (!finalHcpcs || finalHcpcs.length < 3) {
      setSubmitError(
        'Please enter a valid requested procedure / HCPCS code.'
      );
      return;
    }

    if (!finalIcd10 || finalIcd10.length < 3) {
      setSubmitError(
        'Please enter a valid diagnosis / ICD-10 code.'
      );
      return;
    }

    if (!orderingPhysician.trim()) {
      setSubmitError('Ordering physician is required.');
      return;
    }

    if (!signedOrderDate) {
      setSubmitError('Signed order date is required.');
      return;
    }

    if (!providerRationale.trim()) {
      setSubmitError('Clinical rationale is required.');
      return;
    }

    setSubmitError('');
    setSubmitting(true);

    try {
      const payload = {
        patient_id: patientData.patient_id,
        requested_hcpcs: finalHcpcs,
        diagnosis_icd10: finalIcd10,
        ordering_physician: orderingPhysician.trim(),
        signed_order_date: signedOrderDate,
        provider_rationale: providerRationale.trim(),
        encounter_class: encounterClass,
      };

      const res = await requestAPI.create(payload);

      localStorage.removeItem('pa_request_draft');

      navigate('/submitted', {
        state: {
          request_id: res.data.request_id,
          patient_name:
            patientData.full_name ||
            `${patientData.first_name || ''} ${patientData.last_name || ''
              }`.trim(),
          service: `${finalHcpcs} - ${finalIcd10}`,
          submitted_at:
            res.data.submitted_at ||
            new Date().toISOString(),
          status: res.data.status || 'Submitted',
          decision: res.data.decision,
          reason: res.data.reason,
          requires_human_review:
            res.data.requires_human_review,
          reasoning: res.data.reasoning,
        },
      });
    } catch (err) {
      setSubmitError(
        err.response?.data?.detail ||
        'Failed to submit PA request.'
      );
    } finally {
      setSubmitting(false);
    }
  };

  // ============================================================
  // PATIENT DISPLAY HELPERS
  // ============================================================

  const patientFullName =
    patientData?.full_name ||
    `${patientData?.first_name || ''} ${patientData?.last_name || ''
      }`.trim() ||
    'Not available';

  const patientGender =
    patientData?.gender === 'F'
      ? 'Female'
      : patientData?.gender === 'M'
        ? 'Male'
        : patientData?.gender || 'Not available';

  const activePlan = patientData?.current_active_plan || null;

  // ============================================================
  // PRIOR UTILIZATION
  // ============================================================

  const priorUtilization =
    patientData?.prior_utilization_summary || [];

  const matchingPriorUtilization = priorUtilization.filter(
    (item) =>
      String(item?.resolved_hcpc_code || '')
        .trim()
        .toUpperCase() === finalHcpcs
  );

  const hasPriorUtilization =
    matchingPriorUtilization.length > 0;

  const lastPriorDate = hasPriorUtilization
    ? matchingPriorUtilization[0]?.proc_date
    : null;

  // ============================================================
  // RENDER
  // ============================================================

  return (
    <Layout role="initiator">
      <div className="max-w-5xl mx-auto space-y-8 font-sans">

        {/* ======================================================
            HEADER
        ====================================================== */}

        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-extrabold text-[#0F172A] dark:text-white tracking-tight">
              New Prior Authorization Wizard
            </h1>

            <p className="text-sm text-[#64748B] dark:text-slate-400 mt-1">
              Complete multi-step clinical documentation to submit
              authorization request.
            </p>
          </div>

          <button
            onClick={saveDraft}
            className="inline-flex items-center space-x-2 px-4 py-2.5 rounded-xl border border-[#E2E8F0] dark:border-slate-700 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 text-[#0F172A] dark:text-white text-xs font-semibold shadow-sm transition-all"
          >
            <Save className="w-4 h-4 text-[#2563EB]" />
            <span>Save Progress Draft</span>
          </button>
        </div>

        {/* ======================================================
            DRAFT TOAST
        ====================================================== */}

        {draftSavedToast && (
          <div className="p-3 bg-[#DCFCE7] border border-emerald-300 text-[#166534] text-xs rounded-xl flex items-center space-x-2 font-medium shadow-sm">
            <Check className="w-4 h-4" />
            <span>
              Progress saved to local draft! You can return anytime.
            </span>
          </div>
        )}

        {/* ======================================================
            STEPPER
        ====================================================== */}

        <div className="bg-white dark:bg-slate-800 border border-[#E2E8F0] dark:border-slate-700 rounded-2xl p-4 shadow-sm">
          <div className="flex items-center justify-between overflow-x-auto py-2 px-1">
            {WIZARD_STEPS.map((step, idx) => {
              const isCompleted = currentStep > step.id;
              const isCurrent = currentStep === step.id;

              const canOpen =
                step.id === 1 ||
                step.id < currentStep ||
                patientData;

              return (
                <div
                  key={step.id}
                  className="flex items-center flex-1 min-w-[110px] space-x-2"
                >
                  <button
                    type="button"
                    disabled={!canOpen}
                    onClick={() => {
                      if (canOpen) {
                        setSubmitError('');
                        setCurrentStep(step.id);
                      }
                    }}
                    className={`flex items-center space-x-2 text-xs font-semibold transition-all ${isCurrent
                        ? 'text-[#2563EB]'
                        : isCompleted
                          ? 'text-[#166534]'
                          : 'text-[#64748B]'
                      } ${!canOpen
                        ? 'cursor-not-allowed opacity-60'
                        : ''
                      }`}
                  >
                    <div
                      className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs transition-all ${isCurrent
                          ? 'bg-[#2563EB] text-white ring-4 ring-blue-100 shadow-sm'
                          : isCompleted
                            ? 'bg-[#DCFCE7] text-[#166534] border border-emerald-300'
                            : 'bg-slate-100 dark:bg-slate-700 text-[#64748B] dark:text-slate-300 border border-slate-200 dark:border-slate-600'
                        }`}
                    >
                      {isCompleted ? (
                        <Check className="w-4 h-4" />
                      ) : (
                        step.id
                      )}
                    </div>

                    <span className="hidden md:inline truncate">
                      {step.name}
                    </span>
                  </button>

                  {idx < WIZARD_STEPS.length - 1 && (
                    <div
                      className={`h-0.5 flex-1 mx-2 rounded ${isCompleted
                          ? 'bg-emerald-400'
                          : 'bg-slate-200 dark:bg-slate-700'
                        }`}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* ======================================================
            STEP CONTENT
        ====================================================== */}

        <div className="bg-white dark:bg-slate-800 border border-[#E2E8F0] dark:border-slate-700 rounded-2xl p-6 shadow-sm min-h-[380px]">

          {/* ====================================================
              STEP 1
          ==================================================== */}

          {currentStep === 1 && (
            <div className="space-y-6">

              <div className="flex items-center justify-between space-x-3 pb-4 border-b border-[#E2E8F0] dark:border-slate-700">
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-950/40 border border-blue-100 dark:border-blue-900 text-[#2563EB] flex items-center justify-center">
                    <User className="w-5 h-5" />
                  </div>

                  <div>
                    <h3 className="font-bold text-base text-[#0F172A] dark:text-white">
                      Step 1: Patient Information & Coverage
                    </h3>

                    <p className="text-xs text-[#64748B] dark:text-slate-400">
                      Enter details manually or upload a clinical PDF document to automatically fill form fields.
                    </p>
                  </div>
                </div>

                {/* MODE TOGGLE BUTTONS */}
                <div className="inline-flex rounded-xl bg-slate-100 dark:bg-slate-700/60 p-1 space-x-1 border border-slate-200 dark:border-slate-600">
                  <button
                    type="button"
                    onClick={() => setInputMode('manual')}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                      inputMode === 'manual'
                        ? 'bg-white dark:bg-slate-800 text-[#0F172A] dark:text-white shadow-sm'
                        : 'text-[#64748B] dark:text-slate-400 hover:text-slate-900'
                    }`}
                  >
                    Enter Manually
                  </button>
                  <button
                    type="button"
                    onClick={() => setInputMode('pdf')}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                      inputMode === 'pdf'
                        ? 'bg-[#2563EB] text-white shadow-sm'
                        : 'text-[#64748B] dark:text-slate-400 hover:text-slate-900'
                    }`}
                  >
                    Upload PA Document
                  </button>
                </div>
              </div>

              {/* PDF UPLOAD CONTAINER */}
              {inputMode === 'pdf' && (
                <div className="bg-slate-50 dark:bg-slate-900/40 border border-slate-200 dark:border-slate-700 rounded-2xl p-5 space-y-4">
                  <div className="border-2 border-dashed border-blue-200 dark:border-blue-900/60 bg-blue-50/50 dark:bg-blue-950/20 rounded-xl p-6 text-center space-y-3">
                    <UploadCloud className="w-9 h-9 text-[#2563EB] mx-auto" />
                    <div>
                      <h4 className="text-sm font-bold text-slate-800 dark:text-slate-200">Upload Prior Authorization Document (PDF)</h4>
                      <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 max-w-lg mx-auto">
                        Upload a text-based or scanned clinical PDF order to automatically extract patient details, requested procedure, diagnosis code, provider, and rationale.
                      </p>
                    </div>

                    <div className="pt-2">
                      <label className="inline-flex items-center justify-center space-x-2 px-5 py-2.5 bg-[#2563EB] hover:bg-blue-700 text-white text-xs font-semibold rounded-xl cursor-pointer transition-all shadow-sm">
                        <FileText className="w-4 h-4" />
                        <span>{extractingPdf ? 'Extracting information...' : 'Choose PDF Document'}</span>
                        <input
                          type="file"
                          accept=".pdf,application/pdf"
                          disabled={extractingPdf}
                          onChange={handlePdfUpload}
                          className="hidden"
                        />
                      </label>
                    </div>
                  </div>

                  {pdfSuccessMessage && (
                    <div className="p-4 bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/50 rounded-xl text-emerald-800 dark:text-emerald-300 text-xs space-y-1 shadow-sm">
                      <div className="flex items-center space-x-2 font-semibold">
                        <Check className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                        <span>{pdfSuccessMessage}</span>
                      </div>
                      {pdfExtractionMeta && (
                        <p className="text-[11px] text-emerald-700 dark:text-emerald-400 pl-6">
                          Method: <span className="font-mono font-bold">{pdfExtractionMeta.method}</span> {pdfExtractionMeta.ocr_used ? '(Tesseract OCR fallback applied)' : ''} | Extracted: {pdfExtractionMeta.extracted.join(', ')}
                        </p>
                      )}
                    </div>
                  )}

                  {pdfErrorMessage && (
                    <div className="p-4 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800/50 rounded-xl text-red-800 dark:text-red-300 text-xs flex items-center space-x-2 shadow-sm">
                      <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0" />
                      <span>{pdfErrorMessage}</span>
                    </div>
                  )}
                </div>
              )}


              <form
                onSubmit={handlePatientSearch}
                className="flex flex-col sm:flex-row gap-3"
              >
                <div className="relative flex-1">
                  <Search className="w-5 h-5 absolute left-4 top-3.5 text-slate-400" />

                  <input
                    type="text"
                    value={patientIdInput}
                    onChange={(e) =>
                      setPatientIdInput(e.target.value)
                    }
                    placeholder="Enter Patient UUID (e.g. 1a2b3c4d-...)"
                    className="w-full pl-12 pr-4 py-3 bg-white dark:bg-slate-900 border border-[#E2E8F0] dark:border-slate-700 rounded-xl text-[#0F172A] dark:text-white placeholder-slate-400 text-sm focus:outline-none focus:border-[#2563EB] transition-all font-mono"
                  />
                </div>

                <button
                  type="submit"
                  disabled={loadingPatient}
                  className="px-6 py-3 bg-[#2563EB] hover:bg-blue-700 text-white font-semibold rounded-xl text-sm transition-all shadow-sm disabled:opacity-50"
                >
                  {loadingPatient
                    ? 'Searching...'
                    : 'Search Patient'}
                </button>
              </form>

              {patientError && (
                <div className="p-4 rounded-xl bg-[#FEE2E2] border border-red-200 text-[#991B1B] text-xs flex items-center space-x-2">
                  <AlertCircle className="w-4 h-4 flex-shrink-0" />
                  <span>{patientError}</span>
                </div>
              )}

              {patientData && (
                <div className="bg-[#EDF1F5] dark:bg-slate-900/60 border border-[#E2E5E9] dark:border-slate-700 rounded-2xl p-6 space-y-6">

                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-[#E2E5E9] dark:border-slate-700 pb-3">
                    <div className="inline-flex items-center space-x-1.5 text-[13px] font-semibold text-[#2E7D5B] bg-[#2E7D5B]/15 px-3 py-1 rounded-full border border-[#2E7D5B]/30">
                      <Check className="w-4 h-4" />
                      <span>Verified Patient Record</span>
                    </div>

                    <span className="text-[13px] text-[#6B7280] dark:text-slate-400">
                      PII Protection Active
                    </span>
                  </div>

                  {/* IDENTITY */}

                  <div className="space-y-3">
                    <h4 className="text-[13px] font-bold text-[#14477A] dark:text-blue-300 uppercase tracking-wider">
                      Identity Overview
                    </h4>

                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-[15px]">

                      <div className="bg-white dark:bg-slate-800 p-3 rounded-xl border border-[#E2E5E9] dark:border-slate-700">
                        <span className="text-[13px] font-semibold text-[#6B7280] block">
                          First Name
                        </span>
                        <strong className="text-[#1F2937] dark:text-white">
                          {patientData.first_name || 'Not available'}
                        </strong>
                      </div>

                      <div className="bg-white dark:bg-slate-800 p-3 rounded-xl border border-[#E2E5E9] dark:border-slate-700">
                        <span className="text-[13px] font-semibold text-[#6B7280] block">
                          Last Name
                        </span>
                        <strong className="text-[#1F2937] dark:text-white">
                          {patientData.last_name || 'Not available'}
                        </strong>
                      </div>

                      <div className="bg-white dark:bg-slate-800 p-3 rounded-xl border border-[#E2E5E9] dark:border-slate-700">
                        <span className="text-[13px] font-semibold text-[#6B7280] block">
                          Date of Birth
                        </span>
                        <strong className="text-[#1F2937] dark:text-white">
                          {patientData.birthdate || 'Not available'}
                        </strong>
                      </div>

                      <div className="bg-white dark:bg-slate-800 p-3 rounded-xl border border-[#E2E5E9] dark:border-slate-700">
                        <span className="text-[13px] font-semibold text-[#6B7280] block">
                          Gender
                        </span>
                        <strong className="text-[#1F2937] dark:text-white">
                          {patientGender}
                        </strong>
                      </div>

                      <div className="bg-white dark:bg-slate-800 p-3 rounded-xl border border-[#E2E5E9] dark:border-slate-700">
                        <span className="text-[13px] font-semibold text-[#6B7280] block">
                          Marital Status
                        </span>
                        <strong className="text-[#1F2937] dark:text-white">
                          {patientData.marital_status || 'Not available'}
                        </strong>
                      </div>

                      <div className="bg-white dark:bg-slate-800 p-3 rounded-xl border border-[#E2E5E9] dark:border-slate-700">
                        <span className="text-[13px] font-semibold text-[#6B7280] block">
                          Race
                        </span>
                        <strong className="text-[#1F2937] dark:text-white">
                          {patientData.race || 'Not available'}
                        </strong>
                      </div>

                      <div className="bg-white dark:bg-slate-800 p-3 rounded-xl border border-[#E2E5E9] dark:border-slate-700">
                        <span className="text-[13px] font-semibold text-[#6B7280] block">
                          Ethnicity
                        </span>
                        <strong className="text-[#1F2937] dark:text-white">
                          {patientData.ethnicity || 'Not available'}
                        </strong>
                      </div>

                      <div className="bg-white dark:bg-slate-800 p-3 rounded-xl border border-[#E2E5E9] dark:border-slate-700">
                        <span className="text-[13px] font-semibold text-[#6B7280] block">
                          Birthplace
                        </span>
                        <strong className="text-[#1F2937] dark:text-white truncate block">
                          {patientData.birthplace || 'Not available'}
                        </strong>
                      </div>

                    </div>
                  </div>

                  {/* CONTACT */}

                  <div className="space-y-3 pt-2 border-t border-[#E2E5E9] dark:border-slate-700">
                    <h4 className="text-[13px] font-bold text-[#14477A] dark:text-blue-300 uppercase tracking-wider">
                      Contact & Location
                    </h4>

                    <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-[15px]">

                      <div className="col-span-2 bg-white dark:bg-slate-800 p-3 rounded-xl border border-[#E2E5E9] dark:border-slate-700">
                        <span className="text-[13px] font-semibold text-[#6B7280] block">
                          Street Address
                        </span>
                        <strong className="text-[#1F2937] dark:text-white">
                          {patientData.address || 'Not available'}
                        </strong>
                      </div>

                      <div className="bg-white dark:bg-slate-800 p-3 rounded-xl border border-[#E2E5E9] dark:border-slate-700">
                        <span className="text-[13px] font-semibold text-[#6B7280] block">
                          City
                        </span>
                        <strong className="text-[#1F2937] dark:text-white">
                          {patientData.city || 'Not available'}
                        </strong>
                      </div>

                      <div className="bg-white dark:bg-slate-800 p-3 rounded-xl border border-[#E2E5E9] dark:border-slate-700">
                        <span className="text-[13px] font-semibold text-[#6B7280] block">
                          State & County
                        </span>
                        <strong className="text-[#1F2937] dark:text-white">
                          {patientData.state || 'Not available'}
                          {patientData.county
                            ? ` (${patientData.county})`
                            : ''}
                        </strong>
                      </div>

                      <div className="bg-white dark:bg-slate-800 p-3 rounded-xl border border-[#E2E5E9] dark:border-slate-700">
                        <span className="text-[13px] font-semibold text-[#6B7280] block">
                          ZIP Code
                        </span>
                        <strong className="text-[#1F2937] dark:text-white font-mono">
                          {patientData.zip || 'Not available'}
                        </strong>
                      </div>

                    </div>
                  </div>

                  {/* COVERAGE */}

                  <div className="space-y-3 pt-2 border-t border-[#E2E5E9] dark:border-slate-700">
                    <h4 className="text-[13px] font-bold text-[#14477A] dark:text-blue-300 uppercase tracking-wider">
                      Historical Coverage & Expense Snapshot
                    </h4>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-[15px]">

                      <div className="bg-white dark:bg-slate-800 p-3 rounded-xl border border-[#E2E5E9] dark:border-slate-700">
                        <span className="text-[13px] font-semibold text-[#6B7280] block">
                          Active Payer & Member ID
                        </span>

                        <strong className="text-[#2E7D5B] font-bold block">
                          {activePlan
                            ? `${activePlan.payer_name || 'Not available'}${activePlan.member_id
                              ? ` (${activePlan.member_id})`
                              : ''
                            }`
                            : 'Not available'}
                        </strong>
                      </div>

                      <div className="bg-white dark:bg-slate-800 p-3 rounded-xl border border-[#E2E5E9] dark:border-slate-700">
                        <span className="text-[13px] font-semibold text-[#6B7280] block">
                          Lifetime Healthcare Expenses
                        </span>

                        <strong className="text-[#1F2937] dark:text-white font-mono">
                          {patientData.historical_healthcare_expenses != null
                            ? `$${Number(
                              patientData.historical_healthcare_expenses
                            ).toLocaleString('en-US', {
                              minimumFractionDigits: 2,
                            })}`
                            : 'Not available'}
                        </strong>
                      </div>

                      <div className="bg-white dark:bg-slate-800 p-3 rounded-xl border border-[#E2E5E9] dark:border-slate-700">
                        <span className="text-[13px] font-semibold text-[#6B7280] block">
                          Lifetime Healthcare Coverage
                        </span>

                        <strong className="text-[#2E7D5B] font-mono font-bold">
                          {patientData.historical_healthcare_coverage != null
                            ? `$${Number(
                              patientData.historical_healthcare_coverage
                            ).toLocaleString('en-US', {
                              minimumFractionDigits: 2,
                            })}`
                            : 'Not available'}
                        </strong>
                      </div>

                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ====================================================
              STEP 2
          ==================================================== */}

          {currentStep === 2 && (
            <div className="space-y-6">

              <div className="flex items-center space-x-3 pb-4 border-b border-[#E2E8F0] dark:border-slate-700">
                <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-950/40 border border-blue-100 dark:border-blue-900 text-[#2563EB] flex items-center justify-center">
                  <FileCheck className="w-5 h-5" />
                </div>

                <div>
                  <h3 className="font-bold text-base text-[#0F172A] dark:text-white">
                    Step 2: Requested Service (HCPCS/CPT)
                  </h3>

                  <p className="text-xs text-[#64748B] dark:text-slate-400">
                    Select requested procedure code or enter a custom
                    HCPCS code.
                  </p>
                </div>
              </div>

              <div>

                <label className="block text-xs font-semibold text-[#0F172A] dark:text-slate-200 uppercase tracking-wider mb-2">
                  Search HCPCS / CPT Code
                </label>

                <input
                  type="text"
                  placeholder="Filter by code or term (e.g. 70450, CT Head...)"
                  value={hcpcsSearch}
                  onChange={(e) =>
                    setHcpcsSearch(e.target.value)
                  }
                  className="w-full mb-3 px-4 py-2.5 bg-white dark:bg-slate-900 border border-[#E2E8F0] dark:border-slate-700 rounded-xl text-xs placeholder-slate-400 focus:outline-none focus:border-[#2563EB]"
                />

                <select
                  value={isOtherHcpcs ? 'OTHER' : requestedHcpcs}
                  onChange={(e) =>
                    handleHcpcsChange(e.target.value)
                  }
                  className="w-full px-4 py-3 bg-white dark:bg-slate-900 border border-[#E2E8F0] dark:border-slate-700 rounded-xl text-[#0F172A] dark:text-white text-sm focus:outline-none focus:border-[#2563EB] font-mono shadow-sm"
                >
                  <option value="">
                    -- Select HCPCS / CPT code --
                  </option>

                  {loadingHcpcs ? (
                    <option disabled>
                      Loading codes...
                    </option>
                  ) : (
                    <>
                      {hcpcsList.map((opt) => {
                        const code = String(
                          opt.hcpc_code
                        )
                          .trim()
                          .toUpperCase();

                        return (
                          <option
                            key={`hcpcs-${code}`}
                            value={code}
                          >
                            {code} -{' '}
                            {opt.simplified_description ||
                              opt.short_description ||
                              opt.long_description ||
                              'Description unavailable'}
                          </option>
                        );
                      })}

                      <option value="OTHER">
                        ➕ OTHER (Enter custom HCPCS/CPT code...)
                      </option>
                    </>
                  )}
                </select>

                {isOtherHcpcs && (
                  <div className="mt-3 p-4 bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-800 rounded-xl space-y-2">

                    <label className="block text-xs font-bold text-[#2563EB] dark:text-blue-300 uppercase">
                      Enter Custom HCPCS Code
                    </label>

                    <input
                      type="text"
                      value={customHcpcs}
                      onChange={(e) =>
                        setCustomHcpcs(
                          e.target.value.toUpperCase()
                        )
                      }
                      placeholder="e.g. C1776, 99214..."
                      className="w-full px-4 py-2.5 bg-white dark:bg-slate-900 border border-[#E2E8F0] dark:border-slate-700 rounded-lg text-sm font-mono text-[#0F172A] dark:text-white focus:outline-none focus:border-[#2563EB]"
                    />

                  </div>
                )}

                {!isOtherHcpcs && selectedHcpcsObj && (
                  <div className="mt-4 p-4 bg-slate-50 dark:bg-slate-900/60 border border-[#E2E8F0] dark:border-slate-700 rounded-xl text-xs space-y-1">

                    <span className="font-semibold text-[#64748B] dark:text-slate-400 block uppercase text-[10px]">
                      Plain Language Service Summary:
                    </span>

                    <p className="text-[#0F172A] dark:text-white font-medium text-sm">
                      {selectedHcpcsObj.simplified_description ||
                        selectedHcpcsObj.short_description ||
                        selectedHcpcsObj.long_description ||
                        'Description unavailable'}
                    </p>

                    {selectedHcpcsObj.long_description && (
                      <p className="text-[11px] text-[#64748B] dark:text-slate-400 italic mt-1">
                        Technical:{' '}
                        {selectedHcpcsObj.long_description}
                      </p>
                    )}

                  </div>
                )}

              </div>
            </div>
          )}

          {/* ====================================================
              STEP 3
          ==================================================== */}

          {currentStep === 3 && (
            <div className="space-y-6">

              <div className="flex items-center space-x-3 pb-4 border-b border-[#E2E8F0] dark:border-slate-700">
                <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-950/40 border border-blue-100 dark:border-blue-900 text-[#2563EB] flex items-center justify-center">
                  <Stethoscope className="w-5 h-5" />
                </div>

                <div>
                  <h3 className="font-bold text-base text-[#0F172A] dark:text-white">
                    Step 3: Diagnosis Code (ICD-10)
                  </h3>

                  <p className="text-xs text-[#64748B] dark:text-slate-400">
                    Select a diagnosis code covered for the selected
                    HCPCS service or enter a custom ICD-10 code.
                  </p>
                </div>
              </div>

              {!requestedHcpcs && !isOtherHcpcs ? (
                <div className="p-4 bg-[#FEF3C7] text-[#92400E] border border-amber-200 rounded-xl text-xs flex items-center space-x-2">
                  <AlertCircle className="w-4 h-4" />
                  <span>
                    Please select a requested HCPCS/CPT code in Step 2
                    first.
                  </span>
                </div>
              ) : (
                <div>

                  <label className="block text-xs font-semibold text-[#0F172A] dark:text-slate-200 uppercase tracking-wider mb-2">
                    Search Policy Covered ICD-10 Code
                  </label>

                  <input
                    type="text"
                    placeholder="Filter ICD-10 codes..."
                    value={icd10Search}
                    onChange={(e) =>
                      setIcd10Search(e.target.value)
                    }
                    disabled={isOtherHcpcs}
                    className="w-full mb-3 px-4 py-2.5 bg-white dark:bg-slate-900 border border-[#E2E8F0] dark:border-slate-700 rounded-xl text-xs placeholder-slate-400 focus:outline-none focus:border-[#2563EB] disabled:opacity-50"
                  />

                  <select
                    value={
                      isOtherIcd10 ? 'OTHER' : diagnosisIcd10
                    }
                    onChange={(e) =>
                      handleIcd10Change(e.target.value)
                    }
                    disabled={isOtherHcpcs}
                    className="w-full px-4 py-3 bg-white dark:bg-slate-900 border border-[#E2E8F0] dark:border-slate-700 rounded-xl text-[#0F172A] dark:text-white text-sm focus:outline-none focus:border-[#2563EB] font-mono shadow-sm disabled:opacity-50"
                  >
                    <option value="">
                      -- Select ICD-10 diagnosis --
                    </option>

                    {loadingIcd10 ? (
                      <option disabled>
                        Loading policy covered diagnosis codes...
                      </option>
                    ) : (
                      <>
                        {icd10List.map((opt) => {
                          const code = String(
                            opt.icd10_code
                          )
                            .trim()
                            .toUpperCase();

                          return (
                            <option
                              key={`icd10-${code}`}
                              value={code}
                            >
                              {code} -{' '}
                              {opt.simplified_description ||
                                opt.description ||
                                'Description unavailable'}
                            </option>
                          );
                        })}

                        <option value="OTHER">
                          ➕ OTHER (Enter custom ICD-10 code...)
                        </option>
                      </>
                    )}
                  </select>

                  {isOtherHcpcs && (
                    <div className="mt-3 p-4 bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-xs text-slate-600 dark:text-slate-300">
                      Custom HCPCS selected. Enter the diagnosis manually
                      below.
                    </div>
                  )}

                  {isOtherIcd10 && (
                    <div className="mt-3 p-4 bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-800 rounded-xl space-y-2">

                      <label className="block text-xs font-bold text-[#2563EB] dark:text-blue-300 uppercase">
                        Enter Custom ICD-10 Code
                      </label>

                      <input
                        type="text"
                        value={customIcd10}
                        onChange={(e) =>
                          setCustomIcd10(
                            e.target.value.toUpperCase()
                          )
                        }
                        placeholder="e.g. M54.5, R51.9..."
                        className="w-full px-4 py-2.5 bg-white dark:bg-slate-900 border border-[#E2E8F0] dark:border-slate-700 rounded-lg text-sm font-mono text-[#0F172A] dark:text-white focus:outline-none focus:border-[#2563EB]"
                      />

                    </div>
                  )}

                  {!isOtherIcd10 &&
                    !isOtherHcpcs &&
                    selectedIcd10Obj && (
                      <div className="mt-4 p-4 bg-slate-50 dark:bg-slate-900/60 border border-[#E2E8F0] dark:border-slate-700 rounded-xl text-xs space-y-1">

                        <span className="font-semibold text-[#64748B] dark:text-slate-400 block uppercase text-[10px]">
                          Plain Language Diagnosis Summary:
                        </span>

                        <p className="text-[#0F172A] dark:text-white font-medium text-sm">
                          {selectedIcd10Obj.simplified_description ||
                            selectedIcd10Obj.description ||
                            'Description unavailable'}
                        </p>

                        {selectedIcd10Obj.description && (
                          <p className="text-[11px] text-[#64748B] dark:text-slate-400 italic mt-1">
                            Technical:{' '}
                            {selectedIcd10Obj.description}
                          </p>
                        )}

                      </div>
                    )}

                </div>
              )}
            </div>
          )}

          {/* ====================================================
              STEP 4
          ==================================================== */}

          {currentStep === 4 && (
            <div className="space-y-6">

              <div className="flex items-center space-x-3 pb-4 border-b border-[#E2E8F0] dark:border-slate-700">
                <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-950/40 border border-blue-100 dark:border-blue-900 text-[#2563EB] flex items-center justify-center">
                  <Building className="w-5 h-5" />
                </div>

                <div>
                  <h3 className="font-bold text-base text-[#0F172A] dark:text-white">
                    Step 4: Ordering Physician & Order Date
                  </h3>

                  <p className="text-xs text-[#64748B] dark:text-slate-400">
                    Provide licensed ordering provider details and
                    signed order date.
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-xs">

                <div>
                  <label className="block text-xs font-semibold text-[#0F172A] dark:text-slate-200 uppercase tracking-wider mb-2">
                    Ordering Physician Name & Title *
                  </label>

                  <input
                    type="text"
                    value={orderingPhysician}
                    onChange={(e) =>
                      setOrderingPhysician(e.target.value)
                    }
                    placeholder="e.g. Dr. Sarah Chen, MD"
                    className="w-full px-4 py-3 bg-white dark:bg-slate-900 border border-[#E2E8F0] dark:border-slate-700 rounded-xl text-[#0F172A] dark:text-white text-sm focus:outline-none focus:border-[#2563EB]"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-[#0F172A] dark:text-slate-200 uppercase tracking-wider mb-2">
                    Signed Order Date *
                  </label>

                  <input
                    type="date"
                    value={signedOrderDate}
                    onChange={(e) =>
                      setSignedOrderDate(e.target.value)
                    }
                    className="w-full px-4 py-3 bg-white dark:bg-slate-900 border border-[#E2E8F0] dark:border-slate-700 rounded-xl text-[#0F172A] dark:text-white text-sm focus:outline-none focus:border-[#2563EB]"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-[#0F172A] dark:text-slate-200 uppercase tracking-wider mb-2">
                    Encounter Setting
                  </label>

                  <select
                    value={encounterClass}
                    onChange={(e) =>
                      setEncounterClass(e.target.value)
                    }
                    className="w-full px-4 py-3 bg-white dark:bg-slate-900 border border-[#E2E8F0] dark:border-slate-700 rounded-xl text-[#0F172A] dark:text-white text-sm focus:outline-none focus:border-[#2563EB]"
                  >
                    <option value="ambulatory">
                      Outpatient / Ambulatory
                    </option>

                    <option value="inpatient">
                      Inpatient Hospital
                    </option>

                    <option value="emergency">
                      Emergency Department
                    </option>
                  </select>
                </div>

              </div>
            </div>
          )}

          {/* ====================================================
              STEP 5
          ==================================================== */}

          {currentStep === 5 && (
            <div className="space-y-6">

              <div className="flex items-center space-x-3 pb-4 border-b border-[#E2E8F0] dark:border-slate-700">
                <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-950/40 border border-blue-100 dark:border-blue-900 text-[#2563EB] flex items-center justify-center">
                  <Info className="w-5 h-5" />
                </div>

                <div>
                  <h3 className="font-bold text-base text-[#0F172A] dark:text-white">
                    Step 5: Clinical Rationale & Provider Notes
                  </h3>

                  <p className="text-xs text-[#64748B] dark:text-slate-400">
                    Include clinical notes, symptoms duration, and
                    conservative treatments tried.
                  </p>
                </div>
              </div>

              <div>

                <label className="block text-xs font-bold text-[#14213D] dark:text-slate-200 uppercase tracking-wider mb-2">
                  Submitted Provider Clinical Rationale *
                </label>

                <textarea
                  rows={7}
                  value={providerRationale}
                  onChange={(e) =>
                    setProviderRationale(e.target.value)
                  }
                  placeholder="Describe medical necessity, symptoms duration, physical exam findings, prior conservative therapy..."
                  className="w-full p-4 bg-slate-50 dark:bg-slate-900 border border-[#E5E7EB] dark:border-slate-700 rounded-xl text-[#1F2937] dark:text-slate-100 placeholder-slate-400 text-sm focus:outline-none focus:border-[#2E6FF2] font-sans shadow-inner"
                />

                <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-2">
                  This information is submitted to the backend
                  evaluation engine as part of the clinical request.
                </p>

              </div>
            </div>
          )}

          {/* ====================================================
              STEP 6
          ==================================================== */}

          {currentStep === 6 && (
            <div className="space-y-6">

              <div className="flex items-center space-x-3 pb-4 border-b border-[#E2E5E9] dark:border-slate-700">
                <div className="w-10 h-10 rounded-xl bg-[#14477A]/10 border border-[#14477A]/20 text-[#14477A] dark:text-blue-300 flex items-center justify-center">
                  <Calendar className="w-5 h-5" />
                </div>

                <div>
                  <h3 className="font-bold text-base text-[#14477A] dark:text-white">
                    Step 6: Prior Utilization & Medical History
                  </h3>

                  <p className="text-xs text-[#6B7280] dark:text-slate-400">
                    Review historical services and clinical necessity
                    routing indicators.
                  </p>
                </div>
              </div>

              {patientData ? (
                <div className="p-6 bg-[#EDF1F5] dark:bg-slate-900/60 border border-[#E2E5E9] dark:border-slate-700 rounded-2xl space-y-5 text-sm">

                  {/* UTILIZATION SUMMARY */}

                  <div
                    className={`p-4 rounded-xl border flex items-start space-x-3 ${hasPriorUtilization
                        ? 'bg-[#C08A1E]/15 border-[#C08A1E]/40 text-[#C08A1E] dark:text-amber-300'
                        : 'bg-slate-100 dark:bg-slate-800 border-[#E2E5E9] dark:border-slate-700 text-[#6B7280] dark:text-slate-300'
                      }`}
                  >
                    <div className="mt-0.5 flex-shrink-0">
                      {hasPriorUtilization ? (
                        <AlertCircle className="w-5 h-5 text-[#C08A1E]" />
                      ) : (
                        <Check className="w-5 h-5 text-[#6B7280]" />
                      )}
                    </div>

                    <div className="space-y-1">
                      <strong className="font-bold text-[15px] block">
                        {finalHcpcs
                          ? hasPriorUtilization
                            ? `This service (${finalHcpcs}) was performed ${matchingPriorUtilization.length} time(s) in the available prior records, most recently on ${lastPriorDate || 'date unavailable'}.`
                            : `No record of service ${finalHcpcs} being performed for this patient in the available prior records.`
                          : 'Select a requested service to evaluate prior utilization.'}
                      </strong>
                    </div>
                  </div>

                  {/* PROCEDURE TABLE */}

                  <div className="space-y-2">

                    <h4 className="text-[13px] font-bold text-[#14477A] dark:text-blue-300 uppercase tracking-wider">
                      Historical Procedure Record
                    </h4>

                    {priorUtilization.length > 0 ? (
                      <div className="overflow-x-auto border border-[#E2E5E9] dark:border-slate-700 rounded-xl">

                        <table className="w-full text-left border-collapse text-xs">

                          <thead>
                            <tr className="bg-white dark:bg-slate-800 border-b border-[#E2E5E9] text-[#6B7280] uppercase font-semibold">
                              <th className="p-3">
                                Date Performed
                              </th>

                              <th className="p-3">
                                Description & Code
                              </th>

                              <th className="p-3">
                                Source
                              </th>
                            </tr>
                          </thead>

                          <tbody className="divide-y divide-[#E2E5E9] dark:divide-slate-800 bg-white dark:bg-slate-800/50">

                            {priorUtilization.map((proc, idx) => (
                              <tr
                                key={`prior-${proc?.resolved_hcpc_code || 'code'}-${proc?.proc_date || 'date'}-${idx}`}
                                className="hover:bg-slate-50 dark:hover:bg-slate-800"
                              >

                                <td className="p-3 font-mono font-medium text-[#1F2937] dark:text-slate-200">
                                  {proc?.proc_date ||
                                    'Date unavailable'}
                                </td>

                                <td className="p-3">
                                  <span className="font-bold text-[#14477A] dark:text-blue-300 font-mono">
                                    {proc?.resolved_hcpc_code ||
                                      'Unknown code'}
                                  </span>

                                  {' — '}

                                  {proc?.description ||
                                    'Description unavailable'}
                                </td>

                                <td className="p-3 text-[#6B7280] dark:text-slate-400">
                                  EHR System Log
                                </td>

                              </tr>
                            ))}

                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <p className="text-[#6B7280] dark:text-slate-400 italic text-xs">
                        No prior procedure records found in database.
                      </p>
                    )}

                  </div>

                  {/* WHY IT MATTERS */}

                  <div className="p-4 bg-white dark:bg-slate-800 border border-[#E2E5E9] dark:border-slate-700 rounded-xl text-xs text-[#6B7280] dark:text-slate-300 leading-relaxed">
                    <strong className="text-[#1F2937] dark:text-white block font-semibold mb-1">
                      Why Prior Utilization Matters:
                    </strong>

                    Payers review repeat requests for the same service
                    to assess medical necessity and determine whether
                    additional clinical review is appropriate.
                  </div>

                </div>
              ) : (
                <div className="p-4 bg-[#FEF3C7] text-[#92400E] border border-amber-200 rounded-xl text-xs">
                  Patient not looked up yet. Return to Step 1.
                </div>
              )}
            </div>
          )}

          {/* ====================================================
              STEP 7
          ==================================================== */}

          {currentStep === 7 && (
            <div className="space-y-6">

              <div className="flex items-center space-x-3 pb-4 border-b border-[#E2E8F0] dark:border-slate-700">
                <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-950/40 border border-blue-100 dark:border-blue-900 text-[#2563EB] flex items-center justify-center">
                  <ShieldCheck className="w-5 h-5" />
                </div>

                <div>
                  <h3 className="font-bold text-base text-[#0F172A] dark:text-white">
                    Step 7: Final Review & Submission
                  </h3>

                  <p className="text-xs text-[#64748B] dark:text-slate-400">
                    Review complete request parameters before sending
                    to evaluation engine.
                  </p>
                </div>
              </div>

              {submitError && (
                <div className="p-4 rounded-xl bg-[#FEE2E2] border border-red-200 text-[#991B1B] text-xs flex items-center space-x-2">
                  <AlertCircle className="w-4 h-4 flex-shrink-0" />
                  <span>{submitError}</span>
                </div>
              )}

              {/* FINAL VALIDATION SUMMARY */}

              {(!patientData ||
                !finalHcpcs ||
                !finalIcd10 ||
                !orderingPhysician.trim() ||
                !signedOrderDate ||
                !providerRationale.trim()) && (
                  <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-xs">
                    <div className="font-bold mb-2">
                      Please complete the following before submission:
                    </div>

                    <ul className="list-disc ml-5 space-y-1">
                      {!patientData && (
                        <li>Patient record</li>
                      )}

                      {!finalHcpcs && (
                        <li>Requested HCPCS/CPT code</li>
                      )}

                      {!finalIcd10 && (
                        <li>Diagnosis ICD-10 code</li>
                      )}

                      {!orderingPhysician.trim() && (
                        <li>Ordering physician</li>
                      )}

                      {!signedOrderDate && (
                        <li>Signed order date</li>
                      )}

                      {!providerRationale.trim() && (
                        <li>Clinical rationale</li>
                      )}
                    </ul>
                  </div>
                )}

              {/* REVIEW CARDS */}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">

                <div className="p-4 bg-[#EDF1F5] dark:bg-slate-900/60 border border-[#E2E5E9] dark:border-slate-700 rounded-xl space-y-1">
                  <span className="text-[#6B7280] dark:text-slate-400 block font-semibold uppercase text-[13px]">
                    Patient
                  </span>

                  <p className="text-[#1F2937] dark:text-white font-bold">
                    {patientData
                      ? patientFullName
                      : 'Not selected'}
                  </p>

                  {patientData?.patient_id && (
                    <p className="text-xs text-slate-500 font-mono">
                      ID: {patientData.patient_id}
                    </p>
                  )}
                </div>

                <div className="p-4 bg-[#EDF1F5] dark:bg-slate-900/60 border border-[#E2E5E9] dark:border-slate-700 rounded-xl space-y-1">
                  <span className="text-[#6B7280] dark:text-slate-400 block font-semibold uppercase text-[13px]">
                    Requested Procedure Code
                  </span>

                  <p className="text-[#14477A] dark:text-blue-300 font-bold font-mono">
                    {finalHcpcs || 'Not selected'}
                  </p>

                  <p className="text-xs text-[#6B7280] dark:text-slate-400">
                    {isOtherHcpcs
                      ? 'Custom Procedure Code'
                      : selectedHcpcsObj?.simplified_description ||
                      selectedHcpcsObj?.short_description ||
                      selectedHcpcsObj?.long_description ||
                      'No description available'}
                  </p>
                </div>

                <div className="p-4 bg-[#EDF1F5] dark:bg-slate-900/60 border border-[#E2E5E9] dark:border-slate-700 rounded-xl space-y-1">
                  <span className="text-[#6B7280] dark:text-slate-400 block font-semibold uppercase text-[13px]">
                    Diagnosis Code
                  </span>

                  <p className="text-[#14477A] dark:text-blue-300 font-bold font-mono">
                    {finalIcd10 || 'Not selected'}
                  </p>

                  <p className="text-xs text-[#6B7280] dark:text-slate-400">
                    {isOtherIcd10
                      ? 'Custom Diagnosis Code'
                      : selectedIcd10Obj?.simplified_description ||
                      selectedIcd10Obj?.description ||
                      'No description available'}
                  </p>
                </div>

                <div className="p-4 bg-[#EDF1F5] dark:bg-slate-900/60 border border-[#E2E5E9] dark:border-slate-700 rounded-xl space-y-1">
                  <span className="text-[#6B7280] dark:text-slate-400 block font-semibold uppercase text-[13px]">
                    Ordering Provider & Date
                  </span>

                  <p className="text-[#1F2937] dark:text-white font-bold">
                    {orderingPhysician || 'Not provided'}
                  </p>

                  <p className="text-xs text-[#6B7280] dark:text-slate-400 font-mono">
                    Date:{' '}
                    {signedOrderDate || 'Not provided'}
                    {' | '}
                    Setting: {encounterClass}
                  </p>
                </div>

              </div>

              {/* CLINICAL RATIONALE */}

              <div className="p-4 bg-slate-50 dark:bg-slate-900 border border-[#E2E5E9] dark:border-slate-700 rounded-xl">

                <span className="text-[#6B7280] dark:text-slate-400 block font-semibold uppercase text-[13px] mb-2">
                  Clinical Rationale
                </span>

                <p className="text-sm text-[#1F2937] dark:text-slate-200 whitespace-pre-wrap">
                  {providerRationale ||
                    'No clinical rationale provided.'}
                </p>

              </div>

              {/* EVIDENCE */}

              <div className="flex items-center space-x-3 pt-2">

                <button
                  type="button"
                  onClick={() => setShowEvidenceModal(true)}
                  className="inline-flex items-center space-x-2 px-4 py-2.5 rounded-xl border border-[#2563EB] text-[#2563EB] hover:bg-blue-50 dark:hover:bg-blue-950/30 font-semibold text-xs transition-all shadow-sm"
                >
                  <FileText className="w-4 h-4" />
                  <span>
                    View & Download Evidence Document
                  </span>
                </button>

              </div>
            </div>
          )}
        </div>

        {/* ======================================================
            NAVIGATION
        ====================================================== */}

        <div className="flex items-center justify-between pt-4 border-t border-[#E2E8F0] dark:border-slate-700 bg-white dark:bg-slate-800 p-4 rounded-b-xl sticky bottom-0 z-20 shadow-md">

          <button
            type="button"
            disabled={currentStep === 1}
            onClick={() => {
              setSubmitError('');
              setCurrentStep((prev) =>
                Math.max(1, prev - 1)
              );
            }}
            className="px-5 py-2.5 rounded-xl border border-[#CBD2D9] bg-white text-[#0D3B66] text-xs font-semibold disabled:opacity-40 hover:bg-slate-100 transition-all flex items-center space-x-1.5"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Previous Step</span>
          </button>

          {currentStep < 7 ? (
            <button
              type="button"
              onClick={handleNextStep}
              className="px-6 py-2.5 rounded-xl bg-[#0D3B66] hover:bg-[#1F4E79] text-white text-xs font-bold transition-all shadow-sm flex items-center space-x-1.5"
            >
              <span>Continue Step</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          ) : (
            <button
              type="button"
              disabled={
                submitting ||
                !patientData ||
                !finalHcpcs ||
                !finalIcd10 ||
                !orderingPhysician.trim() ||
                !signedOrderDate ||
                !providerRationale.trim()
              }
              onClick={handleSubmit}
              className="px-8 py-3 rounded-xl bg-[#0D3B66] hover:bg-[#1F4E79] text-white text-sm font-bold shadow-md transition-all flex items-center space-x-2 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <span>
                {submitting
                  ? 'Submitting PA Request...'
                  : 'Submit Request Now'}
              </span>

              <ArrowRight className="w-4 h-4" />
            </button>
          )}

        </div>

        {/* ======================================================
            EVIDENCE MODAL
        ====================================================== */}

        {showEvidenceModal && (
          <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">

            <div className="bg-[#F7F8FA] dark:bg-slate-900 rounded-2xl max-w-5xl w-full max-h-[92vh] overflow-y-auto shadow-2xl border border-[#E5E7EB] dark:border-slate-800 flex flex-col md:flex-row text-xs text-[#1F2937] dark:text-slate-100">

              {/* ==================================================
                  DOCUMENT BODY
              ================================================== */}

              <div
                id="printable-pa-document"
                className="flex-1 bg-white dark:bg-slate-800 p-8 space-y-6 border-r border-[#E5E7EB] dark:border-slate-700 shadow-sm font-sans"
              >

                {/* HEADER */}

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pb-4 border-b border-[#E5E7EB] dark:border-slate-700 text-[11px]">

                  <div>
                    <span className="text-[#6B7280] dark:text-slate-400 uppercase font-bold text-[10px] block">
                      Request Date
                    </span>

                    <strong className="text-[#14213D] dark:text-white font-mono text-sm">
                      {signedOrderDate || 'Not available'}
                    </strong>
                  </div>

                  <div>
                    <span className="text-[#6B7280] dark:text-slate-400 uppercase font-bold text-[10px] block">
                      Time
                    </span>

                    <strong className="text-[#14213D] dark:text-white font-mono text-sm">
                      {new Date().toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </strong>
                  </div>

                  <div>
                    <span className="text-[#6B7280] dark:text-slate-400 uppercase font-bold text-[10px] block">
                      Status
                    </span>

                    <strong className="text-[#2E6FF2] font-mono text-sm">
                      Draft
                    </strong>
                  </div>

                  <div>
                    <span className="text-[#6B7280] dark:text-slate-400 uppercase font-bold text-[10px] block">
                      Payer
                    </span>

                    <strong className="text-[#14213D] dark:text-white text-sm">
                      {activePlan?.payer_name ||
                        'Not available'}
                    </strong>
                  </div>

                </div>

                {/* ==================================================
                    1. PATIENT
                ================================================== */}

                <div className="space-y-3">

                  <h3 className="text-xs font-extrabold text-[#2E6FF2] uppercase tracking-wider">
                    1. PATIENT INFORMATION
                  </h3>

                  <div className="bg-slate-50 dark:bg-slate-900/60 rounded-xl divide-y divide-[#E5E7EB] dark:divide-slate-700 border border-[#E5E7EB] dark:border-slate-700 text-xs">

                    <div className="flex justify-between gap-4 p-3">
                      <span className="text-[#6B7280] dark:text-slate-400 font-medium">
                        Patient First & Last Name
                      </span>

                      <strong className="text-[#14213D] dark:text-white text-right">
                        {patientFullName}
                      </strong>
                    </div>

                    <div className="flex justify-between gap-4 p-3">
                      <span className="text-[#6B7280] dark:text-slate-400 font-medium">
                        Patient ID
                      </span>

                      <strong className="text-[#14213D] dark:text-white font-mono text-right">
                        {patientData?.patient_id ||
                          'Not available'}
                      </strong>
                    </div>

                    <div className="flex justify-between gap-4 p-3">
                      <span className="text-[#6B7280] dark:text-slate-400 font-medium">
                        Date of Birth (DOB)
                      </span>

                      <strong className="text-[#14213D] dark:text-white text-right">
                        {patientData?.birthdate ||
                          'Not available'}
                      </strong>
                    </div>

                    <div className="flex justify-between gap-4 p-3">
                      <span className="text-[#6B7280] dark:text-slate-400 font-medium">
                        Gender
                      </span>

                      <strong className="text-[#14213D] dark:text-white text-right">
                        {patientGender}
                      </strong>
                    </div>

                    <div className="flex justify-between gap-4 p-3">
                      <span className="text-[#6B7280] dark:text-slate-400 font-medium">
                        Phone Number
                      </span>

                      <strong className="text-[#14213D] dark:text-white text-right">
                        {patientData?.phone ||
                          'Not available'}
                      </strong>
                    </div>

                    <div className="flex justify-between gap-4 p-3">
                      <span className="text-[#6B7280] dark:text-slate-400 font-medium">
                        Address
                      </span>

                      <strong className="text-[#14213D] dark:text-white text-right">
                        {patientData?.address ||
                          'Not available'}
                      </strong>
                    </div>

                  </div>
                </div>

                {/* ==================================================
                    2. INSURANCE
                ================================================== */}

                <div className="space-y-3">

                  <h3 className="text-xs font-extrabold text-[#2E6FF2] uppercase tracking-wider">
                    2. INSURANCE INFORMATION
                  </h3>

                  <div className="bg-slate-50 dark:bg-slate-900/60 rounded-xl divide-y divide-[#E5E7EB] dark:divide-slate-700 border border-[#E5E7EB] dark:border-slate-700 text-xs">

                    <div className="flex justify-between gap-4 p-3">
                      <span className="text-[#6B7280] dark:text-slate-400 font-medium">
                        Insurance Provider
                      </span>

                      <strong className="text-[#14213D] dark:text-white text-right">
                        {activePlan?.payer_name ||
                          'Not available'}
                      </strong>
                    </div>

                    <div className="flex justify-between gap-4 p-3">
                      <span className="text-[#6B7280] dark:text-slate-400 font-medium">
                        Member ID
                      </span>

                      <strong className="text-[#14213D] dark:text-white font-mono text-right">
                        {activePlan?.member_id ||
                          'Not available'}
                      </strong>
                    </div>

                    <div className="flex justify-between gap-4 p-3">
                      <span className="text-[#6B7280] dark:text-slate-400 font-medium">
                        Coverage Status
                      </span>

                      <strong className="text-[#22C55E] font-bold text-right">
                        {activePlan
                          ? activePlan.status ||
                          'Active'
                          : 'Not available'}
                      </strong>
                    </div>

                  </div>
                </div>

                {/* ==================================================
                    3. SERVICE
                ================================================== */}

                <div className="space-y-3">

                  <h3 className="text-xs font-extrabold text-[#2E6FF2] uppercase tracking-wider">
                    3. REQUESTED SERVICE & DIAGNOSIS
                  </h3>

                  <div className="bg-slate-50 dark:bg-slate-900/60 rounded-xl divide-y divide-[#E5E7EB] dark:divide-slate-700 border border-[#E5E7EB] dark:border-slate-700 text-xs">

                    <div className="flex justify-between gap-4 p-3">
                      <span className="text-[#6B7280] dark:text-slate-400 font-medium">
                        Service / HCPCS Code
                      </span>

                      <strong className="text-[#2E6FF2] font-mono text-sm">
                        {finalHcpcs || 'Not selected'}
                      </strong>
                    </div>

                    <div className="flex justify-between gap-4 p-3">
                      <span className="text-[#6B7280] dark:text-slate-400 font-medium">
                        Diagnosis / ICD-10 Code
                      </span>

                      <strong className="text-[#2E6FF2] font-mono text-sm">
                        {finalIcd10 || 'Not selected'}
                      </strong>
                    </div>

                    <div className="flex justify-between gap-4 p-3">
                      <span className="text-[#6B7280] dark:text-slate-400 font-medium">
                        Ordering Physician
                      </span>

                      <strong className="text-[#14213D] dark:text-white text-right">
                        {orderingPhysician ||
                          'Not provided'}
                      </strong>
                    </div>

                    <div className="flex justify-between gap-4 p-3">
                      <span className="text-[#6B7280] dark:text-slate-400 font-medium">
                        Signed Order Date
                      </span>

                      <strong className="text-[#14213D] dark:text-white font-mono">
                        {signedOrderDate ||
                          'Not provided'}
                      </strong>
                    </div>

                    <div className="flex justify-between gap-4 p-3">
                      <span className="text-[#6B7280] dark:text-slate-400 font-medium">
                        Encounter Setting
                      </span>

                      <strong className="text-[#14213D] dark:text-white">
                        {encounterClass}
                      </strong>
                    </div>

                  </div>
                </div>

                {/* ==================================================
                    4. RATIONALE
                ================================================== */}

                <div className="space-y-3">

                  <h3 className="text-xs font-extrabold text-[#2E6FF2] uppercase tracking-wider">
                    4. CLINICAL RATIONALE
                  </h3>

                  <div className="bg-slate-50 dark:bg-slate-900/60 rounded-xl border border-[#E5E7EB] dark:border-slate-700 p-4">

                    <p className="text-xs leading-relaxed whitespace-pre-wrap text-[#14213D] dark:text-slate-200">
                      {providerRationale ||
                        'No clinical rationale provided.'}
                    </p>

                  </div>
                </div>

              </div>

              {/* ==================================================
                  SIDEBAR
              ================================================== */}

              <div className="w-full md:w-80 bg-[#F7F8FA] dark:bg-slate-900 p-6 space-y-6 flex flex-col justify-between">

                <div className="space-y-6">

                  <div>
                    <h2 className="text-lg font-black text-[#14213D] dark:text-white">
                      PA Document
                    </h2>

                    <p className="text-xs font-mono text-[#6B7280] dark:text-slate-400 mt-0.5">
                      New PA Request
                    </p>

                    <div className="mt-2 inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-[#2E6FF2]/10 text-[#2E6FF2] border border-[#2E6FF2]/30">
                      • Draft Preview
                    </div>
                  </div>

                  <div className="space-y-3">

                    <button
                      onClick={() => window.print()}
                      className="w-full py-3 bg-[#2E6FF2] hover:bg-blue-600 text-white rounded-xl font-bold text-xs shadow-md transition-all flex items-center justify-center space-x-2"
                    >
                      <Download className="w-4 h-4" />
                      <span>Download / Print PDF</span>
                    </button>

                    <button
                      onClick={() => window.print()}
                      className="w-full py-3 bg-white dark:bg-slate-800 border border-[#E5E7EB] dark:border-slate-700 text-[#14213D] dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-xl font-bold text-xs transition-all flex items-center justify-center space-x-2 shadow-sm"
                    >
                      <Printer className="w-4 h-4" />
                      <span>Print Document</span>
                    </button>

                    <button
                      onClick={() =>
                        setShowEvidenceModal(false)
                      }
                      className="w-full text-center py-2 text-xs font-semibold text-[#6B7280] hover:text-[#14213D] dark:hover:text-white"
                    >
                      <X className="w-4 h-4 inline mr-1" />
                      Close Preview
                    </button>

                  </div>

                  <div className="pt-4 border-t border-[#E5E7EB] dark:border-slate-800 space-y-2 text-[11px]">

                    <span className="font-bold text-[#14213D] dark:text-slate-200 block uppercase tracking-wider text-[10px]">
                      Document Details
                    </span>

                    <div className="flex justify-between text-[#6B7280] dark:text-slate-400">
                      <span>Format</span>
                      <strong className="text-[#14213D] dark:text-slate-200 font-mono">
                        Print / A4
                      </strong>
                    </div>

                    <div className="flex justify-between text-[#6B7280] dark:text-slate-400">
                      <span>Status</span>
                      <strong className="text-[#14213D] dark:text-slate-200 font-mono">
                        Draft
                      </strong>
                    </div>

                  </div>
                </div>

                <div className="p-4 bg-blue-50 dark:bg-blue-950/60 border border-blue-200 dark:border-blue-800 rounded-xl text-blue-800 dark:text-blue-300 text-xs space-y-1">

                  <strong className="font-bold block text-blue-900 dark:text-blue-200">
                    Ready for Submission
                  </strong>

                  <p className="text-[11px] leading-relaxed">
                    Review the request information before submitting it
                    to the backend PA evaluation engine.
                  </p>

                </div>

              </div>

            </div>
          </div>
        )}

      </div>
    </Layout>
  );
}