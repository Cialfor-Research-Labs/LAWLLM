export type DocumentTypeId =
  | 'rental'
  | 'employment'
  | 'nda'
  | 'affidavit'
  | 'sale_deed'
  | 'power_of_attorney';

export interface DocumentTemplate {
  id: DocumentTypeId;
  title: string;
  shortLabel: string;
  description: string;
  tone: string;
  accentClass: string;
  sections: string[];
  clausePrompt: string;
  termsPrompt: string;
  helperText: string;
}

export const templates: Record<DocumentTypeId, DocumentTemplate> = {
  rental: {
    id: 'rental',
    title: 'Rental Agreement',
    shortLabel: 'Rental',
    description: 'Draft a tenancy-style agreement with occupancy, rent, and maintenance clauses.',
    tone: 'Property and occupancy drafting',
    accentClass: 'from-sky-500/20 via-cyan-500/10 to-emerald-500/15',
    sections: ['Term', 'Rent', 'Use of Premises', 'Maintenance', 'Termination'],
    clausePrompt: 'Add move-in restrictions, security deposit notes, or visitor policies.',
    termsPrompt: 'Describe rent cycle, utilities, maintenance duties, and possession terms.',
    helperText: 'Best for landlord-tenant drafting, possession clarity, and payment obligations.',
  },
  employment: {
    id: 'employment',
    title: 'Employment Contract',
    shortLabel: 'Employment',
    description: 'Prepare a structured employment draft covering role, term, compensation, and conduct.',
    tone: 'Professional engagement drafting',
    accentClass: 'from-emerald-500/20 via-teal-500/10 to-sky-500/15',
    sections: ['Role and Duties', 'Compensation', 'Working Hours', 'Confidentiality', 'Termination'],
    clausePrompt: 'Include probation, leave policy, notice period, or non-solicit language.',
    termsPrompt: 'Describe role scope, compensation, reporting line, and termination mechanics.',
    helperText: 'Useful for offer-to-contract conversion and structured employer-employee terms.',
  },
  nda: {
    id: 'nda',
    title: 'Non Disclosure Agreement',
    shortLabel: 'NDA',
    description: 'Outline confidentiality obligations, disclosure scope, and permitted exceptions.',
    tone: 'Confidentiality and information control',
    accentClass: 'from-indigo-500/20 via-sky-500/10 to-emerald-500/15',
    sections: ['Definition of Confidential Information', 'Use Restrictions', 'Exceptions', 'Duration', 'Return of Material'],
    clausePrompt: 'Add carve-outs, residual knowledge language, or data handling obligations.',
    termsPrompt: 'Describe what is confidential, how it may be used, and how long restrictions apply.',
    helperText: 'Designed for business-sensitive disclosures without drifting into dispute language.',
  },
  affidavit: {
    id: 'affidavit',
    title: 'Affidavit',
    shortLabel: 'Affidavit',
    description: 'Create a formal sworn statement structure with declarations and verification clauses.',
    tone: 'Declaratory legal drafting',
    accentClass: 'from-cyan-500/20 via-slate-500/10 to-emerald-500/15',
    sections: ['Statement of Identity', 'Facts Declared', 'Supporting Statement', 'Verification'],
    clausePrompt: 'Add identifiers, exhibit references, or statement-specific declarations.',
    termsPrompt: 'Describe the factual statements being affirmed and any supporting context.',
    helperText: 'Ideal for sworn narrative-style documents and factual declarations.',
  },
  sale_deed: {
    id: 'sale_deed',
    title: 'Sale Deed',
    shortLabel: 'Sale Deed',
    description: 'Build a property transfer style draft with consideration, title, and possession sections.',
    tone: 'Transfer and ownership drafting',
    accentClass: 'from-blue-500/20 via-sky-500/10 to-green-500/15',
    sections: ['Property Description', 'Consideration', 'Representations', 'Transfer of Possession', 'Indemnity'],
    clausePrompt: 'Add title assurances, encumbrance statements, or possession delivery notes.',
    termsPrompt: 'Describe consideration, property particulars, transfer obligations, and warranties.',
    helperText: 'Useful for structured sale-transfer drafting and ownership language.',
  },
  power_of_attorney: {
    id: 'power_of_attorney',
    title: 'Power of Attorney',
    shortLabel: 'POA',
    description: 'Frame delegated authority, powers granted, limits, and revocation provisions.',
    tone: 'Delegated authority drafting',
    accentClass: 'from-teal-500/20 via-emerald-500/10 to-cyan-500/15',
    sections: ['Appointment', 'Powers Granted', 'Limitations', 'Duration', 'Revocation'],
    clausePrompt: 'Add banking powers, property authority, signing authority, or revocation conditions.',
    termsPrompt: 'Describe the authority granted, actions permitted, and any scope limitations.',
    helperText: 'Built for agency and authorization structures, not complaint or notice workflows.',
  },
};

export const documentTypeList = Object.values(templates);
