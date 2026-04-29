import React from 'react';
import { BriefcaseBusiness, FileBadge2, FileKey2, FileSignature, Home, ScrollText } from 'lucide-react';
import { documentTypeList, type DocumentTypeId } from '../mock/documentTemplates';

interface DocumentTypeSelectorProps {
  selectedType: DocumentTypeId | null;
  onSelect: (value: DocumentTypeId) => void;
}

const iconMap = {
  rental: Home,
  employment: BriefcaseBusiness,
  nda: FileKey2,
  affidavit: FileBadge2,
  sale_deed: ScrollText,
  power_of_attorney: FileSignature,
} satisfies Record<DocumentTypeId, React.ElementType>;

export const DocumentTypeSelector = ({ selectedType, onSelect }: DocumentTypeSelectorProps) => {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {documentTypeList.map((template) => {
        const Icon = iconMap[template.id];
        const isSelected = selectedType === template.id;

        return (
          <button
            key={template.id}
            type="button"
            onClick={() => onSelect(template.id)}
            className={`group rounded-[28px] border p-5 text-left transition ${
              isSelected
                ? 'border-sky-300 bg-white shadow-[0_22px_50px_rgba(14,116,144,0.14)] dark:border-sky-400/40 dark:bg-slate-900/70'
                : 'border-slate-200/80 bg-white/80 hover:-translate-y-0.5 hover:border-sky-200 hover:shadow-[0_18px_40px_rgba(15,23,42,0.08)] dark:border-slate-800 dark:bg-slate-950/50 dark:hover:border-sky-400/20'
            }`}
          >
            <div className={`rounded-[22px] bg-gradient-to-br p-4 ${template.accentClass}`}>
              <div className="flex items-start justify-between gap-4">
                <div className="rounded-2xl bg-white/85 p-3 text-sky-700 shadow-sm dark:bg-slate-900/80 dark:text-sky-200">
                  <Icon size={20} />
                </div>
                <span className="rounded-full border border-white/70 bg-white/65 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-700 dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-200">
                  {template.shortLabel}
                </span>
              </div>
              <div className="mt-6">
                <h3 className="text-xl font-semibold text-slate-900 dark:text-slate-100">{template.title}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{template.description}</p>
              </div>
            </div>
            <div className="mt-4 space-y-3">
              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-sky-700 dark:text-sky-300">
                Drafting focus
              </div>
              <p className="text-sm leading-6 text-slate-600 dark:text-slate-300">{template.tone}</p>
              <p className="text-sm leading-6 text-slate-500 dark:text-slate-400">{template.helperText}</p>
            </div>
          </button>
        );
      })}
    </div>
  );
};
