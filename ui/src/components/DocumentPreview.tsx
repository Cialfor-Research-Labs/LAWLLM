import React from 'react';

export interface GeneratedDocument {
  title: string;
  intro: string;
  sections: Array<{
    heading: string;
    body: string;
  }>;
  closing: string;
  rawText: string;
}

interface DocumentPreviewProps {
  document: GeneratedDocument;
}

export const DocumentPreview = ({ document }: DocumentPreviewProps) => {
  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_300px]">
      <div className="app-shell-panel flex min-h-[620px] flex-col overflow-hidden">
        <div className="border-b border-slate-200/80 bg-gradient-to-r from-sky-50 via-white to-emerald-50 px-6 py-5 dark:border-slate-800 dark:from-sky-500/10 dark:via-slate-950 dark:to-emerald-500/10">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-sky-700 dark:text-sky-300">
            Generated preview
          </div>
          <h3 className="mt-2 text-2xl font-semibold text-slate-900 dark:text-slate-100">{document.title}</h3>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
          <div className="mx-auto max-w-3xl rounded-[28px] border border-slate-200/80 bg-white px-6 py-8 shadow-[0_22px_50px_rgba(15,23,42,0.06)] dark:border-slate-800 dark:bg-slate-950">
            <div className="text-center">
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                Structured Draft
              </div>
              <h4 className="mt-2 text-3xl font-semibold text-slate-950 dark:text-slate-100">{document.title}</h4>
            </div>
            <p className="mt-8 whitespace-pre-line text-sm leading-7 text-slate-700 dark:text-slate-300">{document.intro}</p>

            <div className="mt-8 space-y-6">
              {document.sections.map((section, index) => (
                <section key={section.heading} className="rounded-[24px] border border-slate-200/80 bg-slate-50/70 p-5 dark:border-slate-800 dark:bg-slate-900/50">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-emerald-700 dark:text-emerald-300">
                    Clause {index + 1}
                  </div>
                  <h5 className="mt-2 text-lg font-semibold text-slate-900 dark:text-slate-100">{section.heading}</h5>
                  <p className="mt-3 whitespace-pre-line text-sm leading-7 text-slate-700 dark:text-slate-300">{section.body}</p>
                </section>
              ))}
            </div>

            <p className="mt-8 whitespace-pre-line text-sm leading-7 text-slate-700 dark:text-slate-300">{document.closing}</p>
          </div>
        </div>
      </div>

      <aside className="space-y-4">
        <div className="rounded-[28px] border border-sky-200/70 bg-white/80 p-5 dark:border-sky-400/10 dark:bg-slate-950/60">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-sky-700 dark:text-sky-300">
            Included sections
          </div>
          <div className="mt-4 space-y-2">
            {document.sections.map((section, index) => (
              <div
                key={section.heading}
                className="rounded-2xl border border-slate-200/80 bg-slate-50/70 px-4 py-3 text-sm text-slate-700 dark:border-slate-800 dark:bg-slate-900/50 dark:text-slate-300"
              >
                {index + 1}. {section.heading}
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-[28px] border border-emerald-200/70 bg-gradient-to-br from-emerald-50 to-white p-5 dark:border-emerald-400/10 dark:from-emerald-500/10 dark:to-slate-950/70">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-emerald-700 dark:text-emerald-300">
            Placeholder mode
          </div>
          <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">
            This preview is assembled entirely on the frontend with mock drafting logic and no backend calls.
          </p>
          <pre className="mt-4 max-h-56 overflow-auto rounded-2xl bg-slate-950 px-4 py-4 text-xs leading-6 text-emerald-100">
            {document.rawText}
          </pre>
        </div>
      </aside>
    </div>
  );
};
