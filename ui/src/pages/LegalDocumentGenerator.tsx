import React, { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, ArrowRight, FileStack, Sparkles } from 'lucide-react';
import { DocumentPreview, type GeneratedDocument } from '../components/DocumentPreview';
import {
  DynamicForm,
  defaultDocumentFormData,
  type DocumentFormData,
} from '../components/DynamicForm';
import { DocumentTypeSelector } from '../components/DocumentTypeSelector';
import { PlaceholderLoader } from '../components/PlaceholderLoader';
import { Stepper } from '../components/Stepper';
import { templates, type DocumentTypeId } from '../mock/documentTemplates';

interface LegalDocumentGeneratorProps {
  newSessionRequest?: number | null;
}

const steps = ['Select Type', 'Fill Details', 'Generate', 'Preview'];

const fillTemplate = (text: string, data: DocumentFormData) => {
  return text
    .replace(/\{partyA\}/g, data.partyAName || 'Party A')
    .replace(/\{partyB\}/g, data.partyBName || 'Party B')
    .replace(/\{address\}/g, data.address || 'the stated address')
    .replace(/\{date\}/g, data.effectiveDate || 'the effective date')
    .replace(/\{duration\}/g, data.duration || 'the agreed duration')
    .replace(/\{terms\}/g, data.terms || 'Standard terms and conditions will be inserted here.')
    .replace(/\{clauses\}/g, data.customClauses || 'No additional custom clauses were specified.');
};

const generateMockDocument = (documentType: DocumentTypeId, data: DocumentFormData): GeneratedDocument => {
  const template = templates[documentType];
  const intro = fillTemplate(
    `THIS ${template.title.toUpperCase()} is made on {date} at {address} BETWEEN {partyA} AND {partyB}. This draft records the working understanding of the parties for a duration of {duration}.`,
    data,
  );

  const sections = template.sections.map((section) => ({
    heading: section,
    body: fillTemplate(
      section === template.sections[0]
        ? `The parties agree that this ${template.shortLabel.toLowerCase()} arrangement will commence from {date} and remain in force for {duration}.`
        : section === template.sections[1]
          ? `{terms}`
          : section === template.sections[template.sections.length - 1]
            ? `{clauses}`
            : `The parties will perform their obligations in relation to ${section.toLowerCase()} in good faith, subject to the primary terms entered above and any operational details recorded at {address}.`,
      data,
    ),
  }));

  const closing = fillTemplate(
    `IN WITNESS WHEREOF, the parties affirm that this placeholder draft reflects their present understanding. Party A: {partyA}. Party B: {partyB}. Execution context: {address}.`,
    data,
  );

  const rawText = [
    `${template.title.toUpperCase()}`,
    '',
    intro,
    '',
    ...sections.flatMap((section, index) => [`${index + 1}. ${section.heading}`, section.body, '']),
    closing,
  ].join('\n');

  return {
    title: template.title,
    intro,
    sections,
    closing,
    rawText,
  };
};

export const LegalDocumentGenerator = ({ newSessionRequest }: LegalDocumentGeneratorProps) => {
  const [currentStep, setCurrentStep] = useState(1);
  const [selectedType, setSelectedType] = useState<DocumentTypeId | null>(null);
  const [formData, setFormData] = useState<DocumentFormData>(defaultDocumentFormData);
  const [isGenerating, setIsGenerating] = useState(false);
  const [document, setDocument] = useState<GeneratedDocument | null>(null);

  useEffect(() => {
    setCurrentStep(1);
    setSelectedType(null);
    setFormData(defaultDocumentFormData);
    setIsGenerating(false);
    setDocument(null);
  }, [newSessionRequest]);

  const selectedTemplate = useMemo(() => {
    return selectedType ? templates[selectedType] : null;
  }, [selectedType]);

  const canContinueFromDetails = Boolean(
    selectedType &&
      formData.partyAName.trim() &&
      formData.partyBName.trim() &&
      formData.effectiveDate.trim() &&
      formData.terms.trim(),
  );

  const updateField = (field: keyof DocumentFormData, nextValue: string) => {
    setFormData((prev) => ({
      ...prev,
      [field]: nextValue,
    }));
  };

  const goNext = () => {
    if (currentStep === 1 && selectedType) {
      setCurrentStep(2);
      return;
    }
    if (currentStep === 2 && canContinueFromDetails) {
      setCurrentStep(3);
      return;
    }
    if (currentStep === 3 && document) {
      setCurrentStep(4);
    }
  };

  const goBack = () => {
    setCurrentStep((prev) => Math.max(1, prev - 1));
  };

  const handleGenerate = () => {
    if (!selectedType) return;
    setIsGenerating(true);
    setDocument(null);

    window.setTimeout(() => {
      const mockDoc = generateMockDocument(selectedType, formData);
      setDocument(mockDoc);
      setIsGenerating(false);
      setCurrentStep(4);
    }, 1500);
  };

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <section className="overflow-hidden rounded-[32px] border border-sky-200/70 bg-[radial-gradient(circle_at_top_left,_rgba(186,230,253,0.55),_transparent_34%),linear-gradient(135deg,_rgba(255,255,255,0.98),_rgba(240,249,255,0.94)_40%,_rgba(236,253,245,0.96))] p-8 shadow-[0_28px_80px_rgba(14,116,144,0.12)] dark:border-sky-400/10 dark:bg-[radial-gradient(circle_at_top_left,_rgba(14,116,144,0.25),_transparent_34%),linear-gradient(135deg,_rgba(2,6,23,0.98),_rgba(10,37,64,0.94)_40%,_rgba(2,44,34,0.94))]">
          <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
            <div className="max-w-3xl">
              <div className="inline-flex items-center gap-2 rounded-full border border-sky-200/70 bg-white/70 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-sky-700 dark:border-sky-400/20 dark:bg-slate-950/50 dark:text-sky-300">
                <FileStack size={14} />
                Legal Document Generator
              </div>
              <h1 className="mt-5 text-4xl font-semibold tracking-tight text-slate-950 dark:text-slate-50 sm:text-5xl">
                Structured drafting for agreements, affidavits, and formal legal documents.
              </h1>
              <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-600 dark:text-slate-300 sm:text-base">
                This builder is intentionally separate from notices. It uses a calm, clause-oriented workflow to assemble mock legal drafts through frontend-only state and placeholder logic.
              </p>
            </div>

            <div className="rounded-[28px] border border-white/70 bg-white/70 p-5 backdrop-blur-xl dark:border-slate-800 dark:bg-slate-950/50">
              <div className="flex items-center gap-3">
                <div className="rounded-2xl bg-emerald-100 p-3 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300">
                  <Sparkles size={18} />
                </div>
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-emerald-700 dark:text-emerald-300">
                    Frontend only
                  </div>
                  <div className="mt-1 text-sm font-medium text-slate-800 dark:text-slate-100">
                    No backend calls, no notice flow reuse
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <Stepper steps={steps} currentStep={currentStep} />

        {currentStep === 1 ? (
          <section className="space-y-4">
            <div>
              <p className="section-kicker text-sky-700 dark:text-sky-300">Step 1</p>
              <h2 className="mt-1 text-3xl font-semibold text-slate-950 dark:text-slate-50">Select a document type</h2>
              <p className="mt-2 max-w-2xl text-sm leading-7 text-slate-600 dark:text-slate-300">
                Choose a drafting pattern. Each template shifts the tone, sections, and clause guidance for the document preview.
              </p>
            </div>
            <DocumentTypeSelector selectedType={selectedType} onSelect={setSelectedType} />
          </section>
        ) : null}

        {currentStep === 2 && selectedType ? (
          <section className="space-y-4">
            <div>
              <p className="section-kicker text-sky-700 dark:text-sky-300">Step 2</p>
              <h2 className="mt-1 text-3xl font-semibold text-slate-950 dark:text-slate-50">Fill structured details</h2>
              <p className="mt-2 max-w-2xl text-sm leading-7 text-slate-600 dark:text-slate-300">
                Provide drafting inputs for {selectedTemplate?.title}. This form stays entirely in frontend state and adapts to the selected template.
              </p>
            </div>
            <DynamicForm documentType={selectedType} value={formData} onChange={updateField} />
          </section>
        ) : null}

        {currentStep === 3 && selectedType ? (
          <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
            <div className="app-shell-panel p-6">
              <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-sky-700 dark:text-sky-300">
                Step 3
              </div>
              <h2 className="mt-2 text-3xl font-semibold text-slate-950 dark:text-slate-50">Generate document</h2>
              <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-600 dark:text-slate-300">
                Review your drafting inputs, then generate a placeholder document preview. This uses mock assembly logic with a timed loading state.
              </p>

              <div className="mt-6 grid gap-4 md:grid-cols-2">
                <div className="rounded-[24px] border border-slate-200/80 bg-slate-50/70 p-5 dark:border-slate-800 dark:bg-slate-900/50">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
                    Selected type
                  </div>
                  <div className="mt-2 text-lg font-semibold text-slate-900 dark:text-slate-100">{selectedTemplate?.title}</div>
                  <div className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">{selectedTemplate?.description}</div>
                </div>
                <div className="rounded-[24px] border border-slate-200/80 bg-slate-50/70 p-5 dark:border-slate-800 dark:bg-slate-900/50">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
                    Draft summary
                  </div>
                  <div className="mt-2 space-y-1 text-sm leading-7 text-slate-700 dark:text-slate-300">
                    <div><strong>Party A:</strong> {formData.partyAName || 'Not set'}</div>
                    <div><strong>Party B:</strong> {formData.partyBName || 'Not set'}</div>
                    <div><strong>Effective Date:</strong> {formData.effectiveDate || 'Not set'}</div>
                    <div><strong>Duration:</strong> {formData.duration || 'Not set'}</div>
                  </div>
                </div>
              </div>

              <div className="mt-6">
                <button type="button" onClick={handleGenerate} className="primary-button">
                  Generate Document
                  <ArrowRight size={16} />
                </button>
              </div>
            </div>

            <aside className="rounded-[28px] border border-emerald-200/70 bg-gradient-to-br from-emerald-50 via-white to-cyan-50 p-5 shadow-[0_20px_50px_rgba(16,185,129,0.10)] dark:border-emerald-400/10 dark:from-emerald-500/10 dark:via-slate-950/80 dark:to-cyan-500/10">
              <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-emerald-700 dark:text-emerald-300">
                Output style
              </div>
              <ul className="mt-4 space-y-3 text-sm leading-6 text-slate-700 dark:text-slate-300">
                <li>Neutral drafting tone with section-based clauses.</li>
                <li>Structured agreement-style layout, not a warning or complaint format.</li>
                <li>Scrollable preview pane with generated sections and paragraph blocks.</li>
              </ul>
            </aside>
          </section>
        ) : null}

        {isGenerating ? <PlaceholderLoader /> : null}

        {currentStep === 4 && document ? (
          <section className="space-y-4">
            <div>
              <p className="section-kicker text-sky-700 dark:text-sky-300">Step 4</p>
              <h2 className="mt-1 text-3xl font-semibold text-slate-950 dark:text-slate-50">Preview output</h2>
              <p className="mt-2 max-w-2xl text-sm leading-7 text-slate-600 dark:text-slate-300">
                The document below is formatted as a structured draft with title, sections, and clause text assembled from placeholders.
              </p>
            </div>
            <DocumentPreview document={document} />
          </section>
        ) : null}

        <div className="flex flex-col gap-3 border-t border-slate-200/80 pt-2 sm:flex-row sm:items-center sm:justify-between dark:border-slate-800">
          <button
            type="button"
            onClick={goBack}
            disabled={currentStep === 1 || isGenerating}
            className="neutral-button"
          >
            <ArrowLeft size={16} />
            Back
          </button>

          <div className="flex flex-wrap items-center justify-end gap-3">
            {currentStep === 1 ? (
              <button type="button" onClick={goNext} disabled={!selectedType} className="primary-button">
                Continue to Details
                <ArrowRight size={16} />
              </button>
            ) : null}

            {currentStep === 2 ? (
              <button type="button" onClick={goNext} disabled={!canContinueFromDetails} className="primary-button">
                Continue to Generate
                <ArrowRight size={16} />
              </button>
            ) : null}

            {currentStep === 4 ? (
              <button
                type="button"
                onClick={() => setCurrentStep(2)}
                className="secondary-button"
              >
                Refine Details
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
};
