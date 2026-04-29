import React from 'react';
import { Check } from 'lucide-react';

interface StepperProps {
  steps: string[];
  currentStep: number;
}

export const Stepper = ({ steps, currentStep }: StepperProps) => {
  return (
    <div className="rounded-[28px] border border-sky-200/60 bg-white/80 p-4 shadow-[0_18px_40px_rgba(14,116,144,0.08)] backdrop-blur-xl dark:border-sky-400/10 dark:bg-slate-900/40">
      <div className="grid gap-3 md:grid-cols-4">
        {steps.map((step, index) => {
          const stepNumber = index + 1;
          const isActive = currentStep === stepNumber;
          const isComplete = currentStep > stepNumber;

          return (
            <div
              key={step}
              className={`rounded-2xl border px-4 py-3 transition ${
                isActive
                  ? 'border-sky-300 bg-sky-50 text-sky-900 dark:border-sky-400/30 dark:bg-sky-500/10 dark:text-sky-100'
                  : isComplete
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-400/30 dark:bg-emerald-500/10 dark:text-emerald-100'
                    : 'border-slate-200 bg-slate-50/70 text-slate-500 dark:border-slate-700 dark:bg-slate-900/50 dark:text-slate-400'
              }`}
            >
              <div className="flex items-center gap-3">
                <div
                  className={`flex h-9 w-9 items-center justify-center rounded-full text-sm font-semibold ${
                    isActive
                      ? 'bg-sky-600 text-white'
                      : isComplete
                        ? 'bg-emerald-600 text-white'
                        : 'bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-300'
                  }`}
                >
                  {isComplete ? <Check size={16} /> : stepNumber}
                </div>
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.12em] opacity-75">Step {stepNumber}</div>
                  <div className="text-sm font-semibold">{step}</div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
