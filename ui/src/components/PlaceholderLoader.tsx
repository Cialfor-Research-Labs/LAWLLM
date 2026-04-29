import React from 'react';

export const PlaceholderLoader = () => {
  return (
    <div className="app-shell-panel overflow-hidden p-6">
      <div className="animate-pulse space-y-5">
        <div className="h-5 w-40 rounded-full bg-sky-100 dark:bg-sky-500/20" />
        <div className="h-10 w-3/4 rounded-2xl bg-slate-100 dark:bg-slate-800" />
        <div className="grid gap-3">
          <div className="h-4 w-full rounded-full bg-slate-100 dark:bg-slate-800" />
          <div className="h-4 w-11/12 rounded-full bg-slate-100 dark:bg-slate-800" />
          <div className="h-4 w-10/12 rounded-full bg-slate-100 dark:bg-slate-800" />
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-3xl border border-slate-200/70 p-4 dark:border-slate-800">
            <div className="h-4 w-24 rounded-full bg-emerald-100 dark:bg-emerald-500/20" />
            <div className="mt-3 h-3 w-full rounded-full bg-slate-100 dark:bg-slate-800" />
            <div className="mt-2 h-3 w-5/6 rounded-full bg-slate-100 dark:bg-slate-800" />
          </div>
          <div className="rounded-3xl border border-slate-200/70 p-4 dark:border-slate-800">
            <div className="h-4 w-24 rounded-full bg-emerald-100 dark:bg-emerald-500/20" />
            <div className="mt-3 h-3 w-full rounded-full bg-slate-100 dark:bg-slate-800" />
            <div className="mt-2 h-3 w-4/6 rounded-full bg-slate-100 dark:bg-slate-800" />
          </div>
        </div>
      </div>
    </div>
  );
};
