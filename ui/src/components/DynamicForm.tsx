import React from 'react';
import { templates, type DocumentTypeId } from '../mock/documentTemplates';

export interface DocumentFormData {
  partyAName: string;
  partyBName: string;
  address: string;
  effectiveDate: string;
  duration: string;
  terms: string;
  customClauses: string;
}

interface DynamicFormProps {
  documentType: DocumentTypeId;
  value: DocumentFormData;
  onChange: (field: keyof DocumentFormData, nextValue: string) => void;
}

export const defaultDocumentFormData: DocumentFormData = {
  partyAName: '',
  partyBName: '',
  address: '',
  effectiveDate: '',
  duration: '',
  terms: '',
  customClauses: '',
};

export const DynamicForm = ({ documentType, value, onChange }: DynamicFormProps) => {
  const template = templates[documentType];

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
      <div className="app-shell-panel p-6">
        <div className="grid gap-5 md:grid-cols-2">
          <div>
            <label className="field-label">Party A Name</label>
            <input
              value={value.partyAName}
              onChange={(event) => onChange('partyAName', event.target.value)}
              className="text-field"
              placeholder="Enter first party or principal party"
            />
          </div>
          <div>
            <label className="field-label">Party B Name</label>
            <input
              value={value.partyBName}
              onChange={(event) => onChange('partyBName', event.target.value)}
              className="text-field"
              placeholder="Enter second party or counterparty"
            />
          </div>
          <div className="md:col-span-2">
            <label className="field-label">Address</label>
            <textarea
              value={value.address}
              onChange={(event) => onChange('address', event.target.value)}
              className="text-field min-h-[96px]"
              placeholder="Registered office, service address, or document execution location"
            />
          </div>
          <div>
            <label className="field-label">Effective Date</label>
            <input
              type="date"
              value={value.effectiveDate}
              onChange={(event) => onChange('effectiveDate', event.target.value)}
              className="text-field"
            />
          </div>
          <div>
            <label className="field-label">Duration</label>
            <input
              value={value.duration}
              onChange={(event) => onChange('duration', event.target.value)}
              className="text-field"
              placeholder="12 months, until revoked, project term"
            />
          </div>
          <div className="md:col-span-2">
            <label className="field-label">Terms &amp; Conditions</label>
            <textarea
              value={value.terms}
              onChange={(event) => onChange('terms', event.target.value)}
              className="text-field min-h-[148px]"
              placeholder={template.termsPrompt}
            />
          </div>
          <div className="md:col-span-2">
            <label className="field-label">Custom Clauses</label>
            <textarea
              value={value.customClauses}
              onChange={(event) => onChange('customClauses', event.target.value)}
              className="text-field min-h-[132px]"
              placeholder={template.clausePrompt}
            />
          </div>
        </div>
      </div>

      <aside className="space-y-4">
        <div className="rounded-[28px] border border-emerald-200/70 bg-gradient-to-br from-emerald-50 via-cyan-50 to-white p-5 shadow-[0_20px_50px_rgba(16,185,129,0.10)] dark:border-emerald-400/10 dark:from-emerald-500/10 dark:via-cyan-500/10 dark:to-slate-950/70">
          <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-emerald-700 dark:text-emerald-300">
            Template guidance
          </div>
          <h3 className="mt-3 text-lg font-semibold text-slate-900 dark:text-slate-100">{template.title}</h3>
          <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{template.helperText}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            {template.sections.map((section) => (
              <span
                key={section}
                className="rounded-full border border-emerald-200 bg-white/80 px-3 py-1 text-[11px] font-medium text-emerald-800 dark:border-emerald-400/20 dark:bg-slate-900/70 dark:text-emerald-200"
              >
                {section}
              </span>
            ))}
          </div>
        </div>

        <div className="rounded-[28px] border border-slate-200/80 bg-white/80 p-5 dark:border-slate-800 dark:bg-slate-950/60">
          <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
            Drafting notes
          </div>
          <ul className="mt-3 space-y-3 text-sm leading-6 text-slate-600 dark:text-slate-300">
            <li>Keep commercial terms neutral and obligation-focused.</li>
            <li>Use custom clauses for special carve-outs or execution details.</li>
            <li>This builder stays frontend-only and uses placeholder document assembly.</li>
          </ul>
        </div>
      </aside>
    </div>
  );
};
