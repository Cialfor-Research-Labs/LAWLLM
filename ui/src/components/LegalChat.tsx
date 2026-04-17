import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import Markdown from 'react-markdown';
import type { Components } from 'react-markdown';
import { 
  CheckCircle2, 
  Loader2, 
  Scale, 
  Send, 
  Sparkles, 
  User, 
  FileText, 
  TrendingUp 
} from 'lucide-react';
import type { GeneratorPrefillPayload } from '../types/generatorPrefill';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface ChatSessionSummary {
    session_id: string;
    title: string;
    created_at: string;
    updated_at: string;
    last_message_at: string;
    message_count: number;
    preview: string;
}

interface ChatSessionListResponse {
    ok: boolean;
    sessions: ChatSessionSummary[];
}

interface ChatSessionDetailResponse {
    ok: boolean;
    session: ChatSessionSummary;
    messages: Array<{
        role: 'user' | 'assistant';
        content: string;
        created_at: string;
    }>;
}

interface LegalOutput {
    analysis: string;
    summary: string;
    applicable_laws: string[];
    legal_options: string[];
    next_steps: string[];
    confidence: number;
    notice_draft?: string;
    case_strategy: string[];
    evidence_checklist?: string[];
}

interface Party {
    id: string;
    name?: string;
    role: string;
    description?: string;
}

interface Event {
    sequence: number;
    actor_id: string;
    action: string;
    target_id?: string;
    description: string;
}

interface BehavioralPrimitive {
    name: string;
    supporting_events: number[];
    description?: string;
}

interface LegalInterpretation {
    label: string;
    description: string;
    confidence: number;
    supporting_behaviors: string[];
    supporting_events: number[];
}

interface ApplicableLaw {
    law: string;
    section: string;
    final_score: number;
    rank: number;
    confidence_level: 'high' | 'medium' | 'low';
    based_on_interpretations: string[];
    based_on_behaviors: string[];
    reasoning: string;
}

interface CaseModel {
    parties: Party[];
    events: Event[];
    financials: any[];
    documents: any[];
    meta: {
        intents: string[];
        claims: string[];
        uncertainties: string[];
    };
    missing_information: { field: string; question: string }[];
}

interface InterviewChatResponse {
    ok: boolean;
    session_id: string;
    issue: string;
    secondary_issues: string[];
    confidence: number;
    status: string; // "interviewing", "clarification_required", "complete", "review_required"
    is_complete: boolean;
    questions: string[];
    legal_output: LegalOutput;
    case_model?: CaseModel;
    behavioral_primitives: BehavioralPrimitive[];
    interpretations: LegalInterpretation[];
    applicable_laws: ApplicableLaw[];
    state_debug?: Record<string, unknown>;
}

interface RagQueryResponse {
    ok: boolean;
    query: string;
    answer: string;
    confidence?: number;
    meta?: {
        session_id?: string;
        [key: string]: unknown;
    };
}

const markdownComponents: Components = {
  strong: ({ children }) => <strong className="font-extrabold text-primary">{children}</strong>,
  b: ({ children }) => <b className="font-extrabold text-primary">{children}</b>,
  p: ({ children }) => <p className="mb-3 last:mb-0 leading-7">{children}</p>,
  ol: ({ children }) => <ol className="mb-3 ml-5 list-decimal space-y-2">{children}</ol>,
  ul: ({ children }) => <ul className="mb-3 ml-5 list-disc space-y-2">{children}</ul>,
  li: ({ children }) => <li className="pl-1 leading-7">{children}</li>,
};

const DEFAULT_GREETING =
    'Hello. I am Vidhi AI. Describe your legal situation, and I will identify the core issues, ask necessary follow-up questions, and provide a full FIRAC legal assessment.';

interface LegalChatProps {
    authToken: string;
    openSessionRequest?: { sessionId: string; nonce: number } | null;
    newSessionRequest?: number | null;
    onChatSessionsChange?: (sessions: ChatSessionSummary[]) => void;
    onActiveSessionChange?: (sessionId: string | null) => void;
    onPrefillDocumentGenerator?: (payload: GeneratorPrefillPayload) => void;
}

function getApiBase(): string {
  const configured = import.meta.env.VITE_API_BASE_URL?.trim();
  if (configured) {
    return configured.replace(/\/$/, '');
  }
  return '/api';
}

const NOTICE_TYPE_HINTS: Array<{ id: string; keywords: string[] }> = [
    { id: 'unpaid_salary', keywords: ['salary', 'wages', 'payroll', 'unpaid salary', 'wage'] },
    { id: 'cheque_bounce', keywords: ['cheque', 'dishonour', 'dishonor', 'bounce'] },
    { id: 'wrongful_termination', keywords: ['termination', 'terminated', 'dismissed', 'fired', 'wrongful termination'] },
    { id: 'tenant_deposit_refund', keywords: ['security deposit', 'deposit refund', 'tenant deposit', 'landlord'] },
    { id: 'breach_of_contract', keywords: ['breach of contract', 'agreement', 'contract', 'breach'] },
    { id: 'consumer_complaint', keywords: ['consumer', 'defective product', 'deficiency in service', 'refund', 'warranty'] },
    { id: 'recovery_of_money', keywords: ['recovery of money', 'debt', 'loan', 'repay', 'outstanding amount'] },
    { id: 'defamation', keywords: ['defamation', 'libel', 'slander', 'reputation'] },
    { id: 'eviction', keywords: ['eviction', 'vacate', 'premises'] },
    { id: 'rent_arrears', keywords: ['rent arrears', 'unpaid rent', 'rent due', 'rent default'] },
    { id: 'maintenance_nonpayment', keywords: ['maintenance', 'alimony', 'spousal support'] },
    { id: 'ip_infringement', keywords: ['trademark', 'copyright', 'infringement', 'counterfeit', 'brand misuse'] },
    { id: 'cyber_fraud', keywords: ['cyber fraud', 'online scam', 'spoofed email', 'phishing', 'fraudulent account', 'unauthorized transaction', 'digital payment fraud'] },
    { id: 'data_privacy_breach', keywords: ['data breach', 'privacy breach', 'personal data', 'unauthorized access'] },
    { id: 'workplace_harassment', keywords: ['workplace harassment', 'sexual harassment', 'hostile workplace', 'harassment'] },
    { id: 'builder_delay', keywords: ['builder delay', 'delayed possession', 'rera', 'project delay'] },
    { id: 'title_ownership_dispute', keywords: ['title dispute', 'ownership dispute', 'property title', 'mutation dispute'] },
];

const NOTICE_TYPE_DEADLINES: Record<string, number> = {
    unpaid_salary: 15,
    cheque_bounce: 15,
    tenant_deposit_refund: 15,
    breach_of_contract: 15,
    consumer_complaint: 15,
    recovery_of_money: 15,
    defamation: 7,
    rent_arrears: 15,
    maintenance_nonpayment: 15,
    ip_infringement: 7,
    cyber_fraud: 7,
    workplace_harassment: 7,
    data_privacy_breach: 10,
    builder_delay: 15,
    title_ownership_dispute: 15,
    wrongful_termination: 30,
    eviction: 30,
};

const SENDER_ROLE_HINTS = ['claimant', 'complainant', 'victim', 'client', 'plaintiff', 'petitioner', 'sender', 'consumer', 'buyer', 'employee', 'tenant', 'owner'];
const RECEIVER_ROLE_HINTS = ['respondent', 'receiver', 'opposite', 'defendant', 'accused', 'vendor', 'seller', 'landlord', 'employer', 'builder', 'fraudster', 'scammer', 'service provider', 'bank', 'company'];
const TRANSCRIPT_NOISE_PATTERNS = [
    /^status:/i,
    /^follow-up question:?/i,
    /^next strategic steps$/i,
    /^evidence (?:&|and) proof checklist$/i,
    /^document generator prefill ready:/i,
    /^legal notice ready:/i,
    /^case complete$/i,
    /^interviewing$/i,
    /^i need a bit more detail/i,
    /^you can transfer these facts/i,
];

function squashWhitespace(value: string | undefined | null): string {
    return String(value || '')
        .replace(/\*\*/g, '')
        .replace(/[`>#]/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
}

function humanizeToken(value: string | undefined | null): string {
    const squashed = squashWhitespace(value);
    if (!squashed) {
        return '';
    }
    return squashed
        .replace(/[_-]+/g, ' ')
        .replace(/\b\w/g, (match) => match.toUpperCase());
}

function firstSentence(value: string | undefined | null): string {
    const squashed = squashWhitespace(value);
    if (!squashed) {
        return '';
    }
    const match = squashed.match(/.*?[.!?](?:\s|$)/);
    return (match ? match[0] : squashed).trim();
}

function sentenceParts(value: string | undefined | null): string[] {
    return squashWhitespace(value)
        .split(/(?<=[.!?])\s+/)
        .map((part) => part.trim())
        .filter((part) => part.length > 12);
}

function messageText(messages: Message[], role?: Message['role']): string {
    return messages
        .filter((message) => !role || message.role === role)
        .map((message) => squashWhitespace(message.content))
        .filter(Boolean)
        .join(' ');
}

function titleCasePhrase(value: string): string {
    return value.replace(/\b\w/g, (match) => match.toUpperCase());
}

function stripListPrefix(value: string): string {
    return value
        .replace(/^\s*[-*]\s+/, '')
        .replace(/^\s*\d+[.)]\s+/, '')
        .replace(/^\s*\[\s*[x ]\s*\]\s+/, '')
        .trim();
}

function cleanTranscriptLine(value: string | undefined | null): string {
    return squashWhitespace(stripListPrefix(String(value || '')))
        .replace(/^subject:\s*/i, '')
        .replace(/^to,\s*/i, '')
        .replace(/^from,\s*/i, '');
}

function isUsefulTranscriptLine(value: string): boolean {
    const line = cleanTranscriptLine(value);
    if (!line || line.length < 10) {
        return false;
    }
    if (line === DEFAULT_GREETING) {
        return false;
    }
    return !TRANSCRIPT_NOISE_PATTERNS.some((pattern) => pattern.test(line));
}

function normalizeFactLine(value: string, senderName: string, receiverName: string): string {
    let line = cleanTranscriptLine(value);
    if (!line) {
        return '';
    }

    const senderLabel = senderName || 'the sender';
    const receiverLabel = receiverName || 'the recipient';

    line = line
        .replace(/\bmy company\b/gi, senderLabel)
        .replace(/\bour company\b/gi, senderLabel)
        .replace(/\bmy client\b/gi, senderLabel)
        .replace(/\bwe\b/gi, senderLabel)
        .replace(/\bours?\b/gi, senderLabel)
        .replace(/\bthe vendor\b/gi, receiverLabel)
        .replace(/\bvendor denied\b/gi, `${receiverLabel} denied`)
        .replace(/\bvendor\b/gi, receiverName && receiverName !== 'Vendor / Concerned Counterparty' ? receiverName : 'the vendor')
        .replace(/\bfraudsters\b/gi, receiverLabel)
        .replace(/\bthe company\b/gi, senderName || 'the company');

    line = line.replace(/\s+/g, ' ').trim();
    if (!/[.!?]$/.test(line)) {
        line = `${line}.`;
    }
    return titleCasePhrase(line.charAt(0)) + line.slice(1);
}

function dedupeLines(lines: string[], limit: number): string[] {
    const out: string[] = [];
    const seen = new Set<string>();
    lines.forEach((line) => {
        const cleaned = cleanTranscriptLine(line);
        const key = cleaned.toLowerCase();
        if (!cleaned || seen.has(key)) {
            return;
        }
        seen.add(key);
        if (out.length < limit) {
            out.push(cleaned);
        }
    });
    return out;
}

function extractMeaningfulTranscriptLines(messages: Message[]): string[] {
    const lines = messages.flatMap((message) => {
        const raw = String(message.content || '')
            .split('\n')
            .map((line) => cleanTranscriptLine(line))
            .filter(isUsefulTranscriptLine);

        if (message.role === 'assistant') {
            return raw.filter((line) => !/^error:/i.test(line));
        }

        return raw;
    });

    return dedupeLines(lines, 30);
}

function extractAddressForLabel(text: string, label: string): string {
    const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const patterns = [
        new RegExp(`${escaped}\\s+address\\s*(?:is|:|-)?\\s*([^.;\\n]+)`, 'i'),
        new RegExp(`${escaped}\\s*(?:is|at|from)\\s+([^.;\\n]+(?:india|delhi|mumbai|bengaluru|bangalore|chennai|kolkata|hyderabad|pune|noida|gurugram|gurgaon|ahmedabad|surat|lucknow|jaipur|thane|indore|bhopal))`, 'i'),
    ];

    for (const pattern of patterns) {
        const match = text.match(pattern);
        const value = squashWhitespace(match?.[1]);
        if (value) {
            return value;
        }
    }

    return '';
}

function inferPartyLabel(text: string, candidates: Array<{ pattern: RegExp; value: string }>): string {
    for (const candidate of candidates) {
        if (candidate.pattern.test(text)) {
            return candidate.value;
        }
    }
    return '';
}

function scorePartyMatch(party: Party, hints: string[], fallbackIndexBoost: number): number {
    const haystack = `${party.id} ${party.name || ''} ${party.role} ${party.description || ''}`.toLowerCase();
    return hints.reduce((score, hint) => score + (haystack.includes(hint) ? 1 : 0), fallbackIndexBoost);
}

function pickPrimaryParties(parties: Party[]): { sender: Party | null; receiver: Party | null } {
    if (!parties.length) {
        return { sender: null, receiver: null };
    }

    const sender = [...parties]
        .sort((left, right) => scorePartyMatch(right, SENDER_ROLE_HINTS, parties.indexOf(right) === 0 ? 0.25 : 0) - scorePartyMatch(left, SENDER_ROLE_HINTS, parties.indexOf(left) === 0 ? 0.25 : 0))[0] || null;

    const receiver = parties
        .filter((party) => party !== sender)
        .sort((left, right) => scorePartyMatch(right, RECEIVER_ROLE_HINTS, parties.indexOf(right) === 1 ? 0.25 : 0) - scorePartyMatch(left, RECEIVER_ROLE_HINTS, parties.indexOf(left) === 1 ? 0.25 : 0))[0]
        || parties.find((party) => party !== sender)
        || null;

    return { sender, receiver };
}

function partyDisplayName(party: Party | null): string {
    if (!party) {
        return '';
    }
    return squashWhitespace(party.name) || humanizeToken(party.id);
}

function inferSenderName(text: string, party: Party | null, noticeType: string): string {
    const fromParty = partyDisplayName(party);
    if (fromParty) {
        return fromParty;
    }

    const explicit = inferPartyLabel(text, [
        { pattern: /\bmy company\b|\bour company\b|\bthe company\b|\ba small company\b/i, value: 'The Company' },
        { pattern: /\bmy client\b|\bthe client\b/i, value: 'Client' },
        { pattern: /\bemployee\b/i, value: 'Employee' },
        { pattern: /\btenant\b/i, value: 'Tenant' },
        { pattern: /\bconsumer\b|\bcustomer\b/i, value: 'Consumer' },
        { pattern: /\bhome ?buyer\b|\ballottee\b/i, value: 'Homebuyer' },
        { pattern: /\bowner\b|\bproperty owner\b/i, value: 'Property Owner' },
    ]);

    if (explicit) {
        return explicit;
    }

    if (noticeType === 'cyber_fraud') {
        return 'Affected Customer / Company';
    }

    return '';
}

function inferReceiverName(text: string, party: Party | null, noticeType: string): string {
    const fromParty = partyDisplayName(party);
    if (fromParty) {
        return fromParty;
    }

    const explicit = inferPartyLabel(text, [
        { pattern: /\bvendor\b/i, value: 'Vendor / Concerned Counterparty' },
        { pattern: /\bemployer\b|\bcompany\b/i, value: 'Employer / Company' },
        { pattern: /\blandlord\b/i, value: 'Landlord' },
        { pattern: /\btenant\b/i, value: 'Tenant' },
        { pattern: /\bbuilder\b|\bdeveloper\b/i, value: 'Builder / Developer' },
        { pattern: /\bseller\b|\bservice provider\b/i, value: 'Seller / Service Provider' },
        { pattern: /\bbank\b/i, value: 'Concerned Bank / Account Holder' },
    ]);

    if (noticeType === 'cyber_fraud') {
        if (/\bbank\b/i.test(text)) {
            return explicit || 'Concerned Bank / Fraudulent Account Holder';
        }
        return 'Fraudulent Account Holder / Unknown Fraudster(s)';
    }

    return explicit;
}

function inferRelationshipFromNarrative(text: string, sender: Party | null, receiver: Party | null, noticeType: string): string {
    const fromParties = deriveRelationship(sender, receiver);
    if (fromParties) {
        return fromParties;
    }

    const explicit = inferPartyLabel(text, [
        { pattern: /\bvendor\b|\bsupplier\b/i, value: 'Business / vendor payment relationship' },
        { pattern: /\bemployer\b|\bemployee\b/i, value: 'Employee / employer relationship' },
        { pattern: /\blandlord\b|\btenant\b/i, value: 'Landlord / tenant relationship' },
        { pattern: /\bconsumer\b|\bcustomer\b|\bseller\b|\bservice provider\b/i, value: 'Consumer / seller relationship' },
        { pattern: /\bbuilder\b|\bhome ?buyer\b|\ballottee\b/i, value: 'Builder / homebuyer relationship' },
    ]);

    if (explicit) {
        return explicit;
    }

    if (noticeType === 'cyber_fraud') {
        return 'Digital payment / cyber fraud dispute';
    }

    return '';
}

function deriveRelationship(sender: Party | null, receiver: Party | null): string {
    const senderRole = humanizeToken(sender?.role);
    const receiverRole = humanizeToken(receiver?.role);
    if (senderRole && receiverRole && senderRole !== receiverRole) {
        return `${senderRole} / ${receiverRole}`;
    }
    return senderRole || receiverRole;
}

function deriveFacts(
    caseModel: CaseModel | null,
    fallbackText: string,
    messages: Message[],
    legalOutput: LegalOutput | null,
    senderName: string,
    receiverName: string,
): string[] {
    const facts = new Set<string>();
    const partyNames = new Map<string, string>();

    caseModel?.parties.forEach((party) => {
        partyNames.set(party.id, partyDisplayName(party));
    });

    [...(caseModel?.events || [])]
        .sort((left, right) => left.sequence - right.sequence)
        .forEach((event) => {
            const description = squashWhitespace(event.description);
            const actor = partyNames.get(event.actor_id) || humanizeToken(event.actor_id);
            const target = partyNames.get(event.target_id || '') || humanizeToken(event.target_id);
            const fallback = [actor, humanizeToken(event.action), target].filter(Boolean).join(' ');
            const fact = normalizeFactLine(description || fallback, senderName, receiverName);
            if (fact) {
                facts.add(fact);
            }
        });

    if (facts.size < 5) {
        extractMeaningfulTranscriptLines(messages)
            .flatMap((line) => sentenceParts(line))
            .map((line) => normalizeFactLine(line, senderName, receiverName))
            .forEach((sentence) => {
                if (facts.size < 6) {
                    facts.add(sentence);
                }
            });
    }

    if (facts.size < 6) {
        [legalOutput?.summary, legalOutput?.analysis, fallbackText]
            .flatMap((value) => sentenceParts(value))
            .map((line) => normalizeFactLine(line, senderName, receiverName))
            .forEach((sentence) => {
                if (facts.size < 6) {
                    facts.add(sentence);
                }
            });
    }

    if (!facts.size && fallbackText) {
        facts.add(normalizeFactLine(firstSentence(fallbackText), senderName, receiverName));
    }

    return Array.from(facts).filter(Boolean).slice(0, 6);
}

function deriveClaim(legalOutput: LegalOutput | null, secondaryIssues: string[], messages: Message[]): string {
    if (secondaryIssues.length > 0) {
        return secondaryIssues.map((issue) => humanizeToken(issue)).join(', ');
    }

    const summarySentence = firstSentence(legalOutput?.summary);
    if (summarySentence) {
        return cleanTranscriptLine(summarySentence);
    }

    const transcriptLine = extractMeaningfulTranscriptLines(messages)
        .find((line) => /recover|refund|breach|fraud|termination|salary|harassment|deposit|rent|defamation|consumer|notice/i.test(line));
    if (transcriptLine) {
        return cleanTranscriptLine(firstSentence(transcriptLine));
    }

    const lastUserMessage = [...messages].reverse().find((message) => message.role === 'user');
    return cleanTranscriptLine(firstSentence(lastUserMessage?.content)) || '';
}

function suggestNoticeType(legalOutput: LegalOutput | null, caseModel: CaseModel | null, claim: string, messages: Message[]): string {
    const combined = [
        claim,
        legalOutput?.summary,
        legalOutput?.analysis,
        messageText(messages, 'user'),
        ...(legalOutput?.applicable_laws || []),
        ...(caseModel?.meta?.claims || []),
        ...(caseModel?.events || []).map((event) => event.description),
    ]
        .map((value) => squashWhitespace(value))
        .filter(Boolean)
        .join(' ')
        .toLowerCase();

    let bestId = 'auto';
    let bestScore = 0;

    NOTICE_TYPE_HINTS.forEach(({ id, keywords }) => {
        const score = keywords.reduce((total, keyword) => total + (combined.includes(keyword) ? 1 : 0), 0);
        if (score > bestScore) {
            bestScore = score;
            bestId = id;
        }
    });

    return bestScore > 0 ? bestId : 'auto';
}

function deriveCustomRelief(legalOutput: LegalOutput | null, messages: Message[], noticeType: string): string {
    const relief = new Set<string>();

    (legalOutput?.legal_options || []).forEach((item) => {
        const cleaned = cleanTranscriptLine(item);
        if (cleaned) {
            relief.add(cleaned);
        }
    });

    (legalOutput?.next_steps || []).forEach((item) => {
        const cleaned = cleanTranscriptLine(item);
        if (cleaned && /recover|refund|pay|reverse|preserve|investigat|identify|cease|compensat|comply|return|settle/i.test(cleaned)) {
            relief.add(cleaned);
        }
    });

    extractMeaningfulTranscriptLines(messages).forEach((line) => {
        if (/recover|refund|reverse|identify|trace|preserve|return|compensat|pay/i.test(line)) {
            relief.add(cleanTranscriptLine(line));
        }
    });

    if (!relief.size && noticeType === 'cyber_fraud') {
        relief.add('Immediate reversal or refund of the fraudulently transferred amount');
        relief.add('Preservation of transaction logs, account records, and related digital evidence');
        relief.add('Disclosure of the beneficiary account details and steps taken to identify the fraudsters');
    }

    return Array.from(relief).slice(0, 5).join('\n');
}

function buildGeneratorPrefill(
    legalOutput: LegalOutput | null,
    caseModel: CaseModel | null,
    secondaryIssues: string[],
    messages: Message[],
    sessionId: string | null,
): GeneratorPrefillPayload {
    const userNarrative = messageText(messages, 'user');
    const { sender, receiver } = pickPrimaryParties(caseModel?.parties || []);
    const claim = deriveClaim(legalOutput, secondaryIssues, messages);
    const noticeType = suggestNoticeType(legalOutput, caseModel, claim, messages);
    const senderName = inferSenderName(userNarrative, sender, noticeType);
    const receiverName = inferReceiverName(userNarrative, receiver, noticeType);
    const facts = deriveFacts(caseModel, legalOutput?.summary || claim, messages, legalOutput, senderName, receiverName);
    const senderAddress = extractAddressForLabel(userNarrative, senderName || 'sender');
    const receiverAddress = extractAddressForLabel(userNarrative, receiverName || 'receiver');

    return {
        senderName,
        receiverName,
        senderAddress,
        receiverAddress,
        relationship: inferRelationshipFromNarrative(userNarrative, sender, receiver, noticeType),
        facts: facts.length ? facts : [''],
        claim,
        noticeType,
        tone: 'firm',
        deadline: NOTICE_TYPE_DEADLINES[noticeType] ?? '',
        customRelief: deriveCustomRelief(legalOutput, messages, noticeType),
        sourceSessionId: sessionId || undefined,
        sourceSummary: squashWhitespace(legalOutput?.summary),
    };
}

function formatInterviewResponse(data: InterviewChatResponse) {
    const out = data.legal_output;
    
    if (!out) {
        const lines = [
            `**Status**: âš ï¸ ${data.status.replace('_', ' ').toUpperCase()}`,
            '',
            'I need a bit more detail before I can provide a legal assessment. Please describe the specific incident or legal problem you are facing.',
        ];
        
        if (data.questions.length > 0) {
            lines.push('');
            lines.push('**Follow-up Question:**');
            lines.push(data.questions[0]);
        }
        
        return lines.join('\n').trim();
    }

    const lines = [
        `**Status**: ${data.is_complete ? 'âœ… Case Complete' : 'ðŸ“ Interviewing...'}`,
        '',
        `> ${out.summary}`,
        '',
        out.analysis,
        '',
        '**Next Strategic Steps**',
        ...out.case_strategy.map(step => `- ${step}`),
    ];

    if (out.evidence_checklist && out.evidence_checklist.length > 0) {
        lines.push('');
        lines.push('**ðŸ“ Evidence & Proof Checklist**');
        out.evidence_checklist.forEach((item) => lines.push(`- [ ] ${item}`));
    }
    
    if (data.questions.length > 0 && !data.is_complete) {
        lines.push('');
        lines.push('**Follow-up Question:**');
        lines.push(data.questions[0]);
    }

    if (data.is_complete && out.notice_draft) {
        lines.push('');
        lines.push('---');
        lines.push('**Document Generator Prefill Ready**: You can transfer these facts into the "Document Generator" tab, review them, and generate the notice there.');
    }
    
    return lines.join('\n').trim();
}

function formatInterviewResponseClean(data: InterviewChatResponse) {
    const out = data.legal_output;

    if (!out) {
        const lines = [
            `**Status**: ${data.status.replace('_', ' ').toUpperCase()}`,
            '',
            'I need a bit more detail before I can provide a legal assessment. Please describe the specific incident or legal problem you are facing.',
        ];

        if (data.questions.length > 0) {
            lines.push('');
            lines.push('**Follow-up Question:**');
            lines.push(data.questions[0]);
        }

        return lines.join('\n').trim();
    }

    const lines = [
        `**Status**: ${data.is_complete ? 'Case Complete' : 'Interviewing'}`,
        '',
        `> ${out.summary}`,
        '',
        out.analysis,
        '',
        '**Next Strategic Steps**',
        ...out.case_strategy.map((step) => `- ${step}`),
    ];

    if (out.evidence_checklist && out.evidence_checklist.length > 0) {
        lines.push('');
        lines.push('**Evidence & Proof Checklist**');
        out.evidence_checklist.forEach((item) => lines.push(`- [ ] ${item}`));
    }

    if (data.questions.length > 0 && !data.is_complete) {
        lines.push('');
        lines.push('**Follow-up Question:**');
        lines.push(data.questions[0]);
    }

    if (data.is_complete && out.notice_draft) {
        lines.push('');
        lines.push('---');
        lines.push('**Document Generator Prefill Ready**: You can transfer these facts into the "Document Generator" tab, review them, and generate the notice there.');
    }

    return lines.join('\n').trim();
}


export const LegalChat = ({
    authToken,
    openSessionRequest,
    newSessionRequest,
    onChatSessionsChange,
    onActiveSessionChange,
    onPrefillDocumentGenerator,
}: LegalChatProps) => {
    const apiBase = useMemo(() => getApiBase(), []);
    const authHeaders = useMemo(
        () => ({
            'Content-Type': 'application/json',
            Authorization: `Bearer ${authToken}`,
        }),
        [authToken],
    );
    const scrollRef = useRef<HTMLDivElement>(null);
    const [messages, setMessages] = useState<Message[]>([
        {
            role: 'assistant',
            content: DEFAULT_GREETING,
        },
    ]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [sessionId, setSessionId] = useState<string | null>(null);
    const [chatSessions, setChatSessions] = useState<ChatSessionSummary[]>([]);
    const [legalOutput, setLegalOutput] = useState<LegalOutput | null>(null);
    const [isComplete, setIsComplete] = useState(false);
    const [status, setStatus] = useState<string>("interviewing");
    const [confidence, setConfidence] = useState(0);
    const [secondaryIssues, setSecondaryIssues] = useState<string[]>([]);
    const [caseModel, setCaseModel] = useState<CaseModel | null>(null);
    const [behavioralPrimitives, setBehavioralPrimitives] = useState<BehavioralPrimitive[]>([]);
    const [interpretations, setInterpretations] = useState<LegalInterpretation[]>([]);
    const [applicableLaws, setApplicableLaws] = useState<ApplicableLaw[]>([]);

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [messages, isLoading]);

    const loadChatSessions = async () => {
        try {
            const response = await fetch(`${apiBase}/chat/sessions?limit=50`, {
                method: 'GET',
                headers: authHeaders,
            });
            if (!response.ok) {
                throw new Error(`Failed to load chat history (${response.status})`);
            }
            const data: ChatSessionListResponse = await response.json();
            setChatSessions(Array.isArray(data.sessions) ? data.sessions : []);
        } catch (error) {
            console.error('History load error:', error);
            setChatSessions([]);
        }
    };

    useEffect(() => {
        void loadChatSessions();
    }, [authToken]);

    useEffect(() => {
        onChatSessionsChange?.(chatSessions);
    }, [chatSessions, onChatSessionsChange]);

    useEffect(() => {
        onActiveSessionChange?.(sessionId);
    }, [sessionId, onActiveSessionChange]);

    const resetConversation = () => {
        setMessages([
            {
                role: 'assistant',
                content: DEFAULT_GREETING,
            },
        ]);
        setInput('');
        setSessionId(null);
        setLegalOutput(null);
        setIsComplete(false);
        setStatus("interviewing");
        setConfidence(0);
        setSecondaryIssues([]);
        setCaseModel(null);
        setBehavioralPrimitives([]);
        setInterpretations([]);
        setApplicableLaws([]);
    };

    const openConversation = async (targetSessionId: string) => {
        if (!targetSessionId) {
            resetConversation();
            return;
        }
        try {
            const response = await fetch(`${apiBase}/chat/sessions/${encodeURIComponent(targetSessionId)}?limit=200`, {
                method: 'GET',
                headers: authHeaders,
            });
            if (!response.ok) {
                throw new Error(`Could not open selected conversation (${response.status})`);
            }
            const data: ChatSessionDetailResponse = await response.json();
            const loadedMessages: Message[] = (data.messages || []).map((item) => ({
                role: item.role,
                content: item.content,
            }));
            setSessionId(data.session?.session_id || targetSessionId);
            setMessages(
                loadedMessages.length
                    ? loadedMessages
                    : [{ role: 'assistant', content: DEFAULT_GREETING }],
            );
            setInput('');
            setLegalOutput(null);
            setIsComplete(false);
            setStatus("interviewing");
            setConfidence(0);
            setSecondaryIssues([]);
            setCaseModel(null);
            setBehavioralPrimitives([]);
            setInterpretations([]);
            setApplicableLaws([]);
        } catch (error) {
            console.error('Open conversation error:', error);
            setMessages((prev) => [
                ...prev,
                { role: 'assistant', content: 'Could not load that previous conversation. Please try again.' },
            ]);
        }
    };

    useEffect(() => {
        if (!openSessionRequest?.sessionId) {
            return;
        }
        if (openSessionRequest.sessionId === sessionId) {
            return;
        }
        void openConversation(openSessionRequest.sessionId);
    }, [openSessionRequest, sessionId]);

    useEffect(() => {
        if (newSessionRequest == null) {
            return;
        }
        resetConversation();
    }, [newSessionRequest]);

    const handleSend = async () => {
        if (!input.trim() || isLoading) return;
        const userMessage = input.trim();
        setInput('');
        setMessages((prev) => [...prev, { role: 'user', content: userMessage }]);
        setIsLoading(true);

        try {
            const response = await fetch(`${apiBase}/query`, {
                method: 'POST',
                headers: authHeaders,
                body: JSON.stringify({
                    query: userMessage,
                    mode: 'lawyer_case',
                    session_id: sessionId,
                }),
            });
            
            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                throw new Error(errData.detail?.error || `Request failed: ${response.status}`);
            }
            
            const data: RagQueryResponse | InterviewChatResponse = await response.json();

            // Primary path: /query RAG response
            if ('answer' in data) {
                const nextSessionId = data.meta?.session_id || sessionId || null;
                setSessionId(nextSessionId);
                setIsComplete(true);
                setStatus("complete");
                setSecondaryIssues([]);
                setLegalOutput(null);
                setCaseModel(null);
                setBehavioralPrimitives([]);
                setInterpretations([]);
                setApplicableLaws([]);
                setConfidence(data.confidence || 0);
                setMessages((prev) => [...prev, { role: 'assistant', content: data.answer }]);
                await loadChatSessions();
            } else {
                // Backward compatible fallback if interview response is returned
                setSessionId(data.session_id);
                setIsComplete(data.is_complete);
                setStatus(data.status);
                setSecondaryIssues(data.secondary_issues || []);
                
                if (data.legal_output) {
                    setLegalOutput(data.legal_output);
                    setConfidence(data.confidence);
                } else {
                    setConfidence(data.confidence || 0);
                }
                
                if (data.case_model) {
                    setCaseModel(data.case_model);
                }
                
                setBehavioralPrimitives(data.behavioral_primitives || []);
                setInterpretations(data.interpretations || []);
                setApplicableLaws(data.applicable_laws || []);
                setMessages((prev) => [...prev, { role: 'assistant', content: formatInterviewResponseClean(data) }]);
                await loadChatSessions();
            }
            
        } catch (error: any) {
            console.error('Chat Error:', error);
            setMessages((prev) => [
                ...prev,
                { role: 'assistant', content: `Error: ${error.message || 'Technical glitch. Try again.'}` },
            ]);
        } finally {
            setIsLoading(false);
        }
    };

    const canPrefillDocumentGenerator =
        !isLoading &&
        messages.some((message) => message.role === 'user') &&
        (Boolean(legalOutput) || status === 'complete');

    const sendToGenerator = () => {
        if (!canPrefillDocumentGenerator) return;
        onPrefillDocumentGenerator?.(
            buildGeneratorPrefill(
                legalOutput,
                caseModel,
                secondaryIssues,
                messages,
                sessionId,
            ),
        );
    };

    const progressLabel =
        status === 'clarification_required'
            ? 'Signal Low'
            : status === 'complete'
                ? 'Factual Certainty'
                : 'Analyzing Situation';
    const systemModeLabel = status.replace('_', ' ');

    return (
        <div className="flex-1 flex flex-col h-full overflow-hidden bg-gradient-to-b from-surface to-surface-container-low">
            <div className="border-b border-outline-variant/10 bg-surface/90 px-8 py-6 backdrop-blur-sm">
                <div className="mx-auto flex max-w-6xl items-start justify-between gap-6">
                    <div className="max-w-3xl">
                        <h2 className="text-3xl font-headline font-bold text-primary">Vidhi AI: Intelligent Interviewer</h2>
                        <p className="hidden text-sm text-on-surface-variant">
                            Unified Legal Case Engine Â· Factual Extraction Â· FIRAC Analysis
                        </p>
                        <p className="mt-2 text-base text-on-surface-variant">
                            Unified Legal Case Engine · Factual Extraction · FIRAC Analysis
                        </p>
                    </div>
                    <div className="hidden items-center gap-3">
                        <div className="flex flex-col items-end mr-4">
                            <span className="text-[10px] font-bold uppercase text-on-surface-variant">
                                {status === "clarification_required" ? "âš ï¸ Signal Low" : status === "complete" ? "âœ… Factual Certainty" : "ðŸ” Analyzing Situation"}
                            </span>
                            <div className="w-32 h-1.5 bg-surface-container rounded-full mt-1 overflow-hidden shadow-inner">
                                <motion.div 
                                    className={`h-full ${confidence < 0.4 ? 'bg-amber-500' : confidence < 0.7 ? 'bg-primary' : 'bg-emerald-500'}`}
                                    initial={{ width: 0 }}
                                    animate={{ width: `${confidence * 100}%` }}
                                    transition={{ duration: 0.5 }}
                                />
                            </div>
                        </div>
                        <div className="hidden sm:flex flex-col items-start px-3 py-1.5 bg-surface-container-low border border-outline-variant/20 rounded-xl mr-2">
                             <span className="text-[9px] font-black uppercase text-on-surface-variant/70 leading-none">System Mode</span>
                             <span className={`text-[11px] font-bold uppercase tracking-tight leading-normal ${status === 'complete' ? 'text-emerald-600' : status === 'clarification_required' ? 'text-amber-600' : 'text-primary'}`}>
                                {status.replace('_', ' ')}
                             </span>
                        </div>
                    </div>
                    <div className="flex min-w-[260px] items-center gap-3">
                        <div className="flex flex-1 flex-col items-end rounded-2xl border border-outline-variant/15 bg-surface-container-low px-4 py-3 shadow-sm">
                            <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-on-surface-variant">
                                {progressLabel}
                            </span>
                            <div className="mt-2 h-2 w-40 overflow-hidden rounded-full bg-surface-container-high shadow-inner">
                                <motion.div
                                    className={`h-full ${confidence < 0.4 ? 'bg-amber-500' : confidence < 0.7 ? 'bg-primary' : 'bg-emerald-500'}`}
                                    initial={{ width: 0 }}
                                    animate={{ width: `${confidence * 100}%` }}
                                    transition={{ duration: 0.5 }}
                                />
                            </div>
                        </div>
                        <div className="hidden rounded-2xl border border-outline-variant/20 bg-surface-container-low px-4 py-3 shadow-sm sm:flex sm:flex-col">
                            <span className="text-[9px] font-black uppercase tracking-[0.12em] text-on-surface-variant/70 leading-none">System Mode</span>
                            <span className={`mt-1 text-[11px] font-bold uppercase tracking-[0.08em] leading-normal ${status === 'complete' ? 'text-emerald-600' : status === 'clarification_required' ? 'text-amber-600' : 'text-primary'}`}>
                                {systemModeLabel}
                            </span>
                        </div>
                    </div>
                </div>
            </div>

            <div ref={scrollRef} className="flex-1 overflow-y-auto px-8 py-6 no-scrollbar">
                <div className="mx-auto flex max-w-6xl flex-col gap-5">
                <AnimatePresence initial={false}>
                    {messages.map((msg, idx) => (
                        <motion.div
                            key={`${msg.role}-${idx}`}
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                        >
                            <div className={`flex max-w-[82%] items-start gap-4 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                                <div
                                    className={`mt-1 flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl shadow-sm ${
                                        msg.role === 'user' ? 'bg-secondary-container text-on-secondary-container' : 'bg-primary text-on-primary'
                                    }`}
                                >
                                    {msg.role === 'user' ? <User size={18} /> : <Sparkles size={18} />}
                                </div>
                                <div
                                    className={`rounded-[28px] border px-6 py-5 shadow-sm ${
                                        msg.role === 'user'
                                            ? 'border-primary/20 bg-primary text-on-primary'
                                            : 'chat-assistant-bubble'
                                    }`}
                                >
                                    <Markdown components={markdownComponents}>{msg.content}</Markdown>
                                </div>
                            </div>
                        </motion.div>
                    ))}
                </AnimatePresence>

                {isLoading && (
                    <div className="flex justify-start">
                        <div className="chat-assistant-bubble flex items-center gap-4 rounded-[24px] border px-5 py-4">
                            <Loader2 size={18} className="animate-spin text-primary" />
                            <div className="text-sm font-medium text-on-surface">
                                Preparing a guided legal response...
                            </div>
                        </div>
                    </div>
                )}

                {status === 'review_required' && caseModel && (
                    <motion.div
                        initial={{ opacity: 0, scale: 0.95 }}
                        animate={{ opacity: 1, scale: 1 }}
                        className="rounded-2xl border border-amber-200 bg-amber-50 p-6 shadow-sm mb-8"
                    >
                        <div className="flex items-center gap-2 text-amber-700 font-bold uppercase tracking-wider text-xs mb-4">
                            <FileText size={16} />
                            Case Model Review Required
                        </div>
                        
                        <p className="text-sm text-amber-900 mb-6">
                            I've reconstructed the timeline and parties involved. Please confirm if this is correct before we proceed to legal analysis.
                        </p>

                        <div className="grid gap-6 md:grid-cols-2">
                             <div className="space-y-4">
                                <h4 className="text-xs font-black uppercase text-amber-800/60">Resolved Timeline</h4>
                                <div className="space-y-3">
                                    {caseModel.events.map((evt) => (
                                        <div key={evt.sequence} className="flex gap-3 text-xs bg-surface-container-low p-3 rounded-lg border border-amber-200/50">
                                            <span className="font-bold text-amber-700">#{evt.sequence}</span>
                                            <div>
                                                <span className="font-bold text-primary">{evt.actor_id}</span> {evt.action}
                                                <p className="mt-1 text-[10px] text-on-surface-variant italic">{evt.description}</p>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                             </div>

                             <div className="space-y-4">
                                <h4 className="text-xs font-black uppercase text-amber-800/60">Parties Involved</h4>
                                <div className="grid grid-cols-2 gap-2">
                                    {caseModel.parties.map((p) => (
                                        <div key={p.id} className="p-3 bg-surface-container-low rounded-lg border border-amber-200/50 text-xs">
                                            <div className="font-bold text-primary">{p.id}</div>
                                            <div className="font-medium text-on-surface">{p.role}</div>
                                            <div className="text-[10px] text-on-surface-variant line-clamp-1">{p.description}</div>
                                        </div>
                                    ))}
                                </div>

                                {caseModel.financials && caseModel.financials.length > 0 && (
                                    <>
                                        <h4 className="text-xs font-black uppercase text-amber-800/60 mt-4">Financials</h4>
                                        <div className="space-y-2">
                                            {caseModel.financials.map((f, i) => (
                                                <div key={i} className="flex justify-between items-center p-2 bg-surface-container-high rounded border border-amber-200/50 text-xs text-amber-900">
                                                    <span>{f.context}</span>
                                                    <span className="font-bold">â‚¹{f.amount.toLocaleString()}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </>
                                )}
                             </div>
                        </div>

                        <div className="mt-8 flex gap-4">
                            <button
                                onClick={async () => {
                                    setIsLoading(true);
                                    try {
                                        const response = await fetch(`${apiBase}/query`, {
                                            method: 'POST',
                                            headers: authHeaders,
                                            body: JSON.stringify({
                                                query: "Confirmed",
                                                session_id: sessionId,
                                                mode: 'lawyer_case',
                                            }),
                                        });
                                        const data: RagQueryResponse | InterviewChatResponse = await response.json();
                                        if ('answer' in data) {
                                            const nextSessionId = data.meta?.session_id || sessionId || null;
                                            setSessionId(nextSessionId);
                                            setMessages((prev) => [...prev, { role: 'assistant', content: data.answer }]);
                                            setStatus("complete");
                                            setConfidence(data.confidence || 0);
                                            setLegalOutput(null);
                                            setIsComplete(true);
                                            await loadChatSessions();
                                        } else {
                                            setSessionId(data.session_id);
                                            setMessages((prev) => [...prev, { role: 'assistant', content: formatInterviewResponseClean(data) }]);
                                            setStatus(data.status);
                                            setConfidence(data.confidence);
                                            setLegalOutput(data.legal_output);
                                            setIsComplete(data.is_complete);
                                            await loadChatSessions();
                                        }
                                    } catch (e) {
                                        console.error(e);
                                    } finally {
                                        setIsLoading(false);
                                    }
                                }}
                                className="flex-1 bg-primary text-on-primary py-3 rounded-xl font-bold text-xs uppercase tracking-widest hover:opacity-90 shadow-lg shadow-primary/20"
                            >
                                Confirm & Proceed
                            </button>
                            <button className="px-6 py-3 border border-outline-variant rounded-xl text-xs font-bold text-on-surface hover:bg-surface-container">
                                Edit
                            </button>
                        </div>
                    </motion.div>
                )}

                {(behavioralPrimitives.length > 0 || interpretations.length > 0) && status !== 'review_required' && (
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="rounded-2xl border border-primary/10 bg-surface-container-low p-6 shadow-sm mb-8"
                    >
                         <div className="flex items-center gap-2 text-primary font-bold uppercase tracking-wider text-[10px] mb-4">
                            <Sparkles size={14} className="text-secondary" />
                            Legal Brain Analysis (Phase 2)
                        </div>

                        {/* Behavioral Primitives (Objective Markers) */}
                        {behavioralPrimitives.length > 0 && (
                            <div className="mb-6">
                                <div className="text-[9px] font-black text-on-surface-variant uppercase tracking-widest mb-3 flex items-center gap-2">
                                    <div className="w-1.5 h-1.5 rounded-full bg-secondary" />
                                    Observable Behaviors
                                </div>
                                <div className="flex flex-wrap gap-2">
                                    {behavioralPrimitives.map((b, idx) => (
                                        <div key={idx} className="px-3 py-1.5 bg-surface-container-lowest border border-outline-variant/30 rounded-lg text-[10px] font-bold text-primary flex items-center gap-2 shadow-sm">
                                            {b.name.replace(/_/g, ' ')}
                                            <div className="w-px h-3 bg-outline-variant" />
                                            <span className="text-on-surface-variant font-medium">Events {b.supporting_events.join(',')}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Legal Interpretations (Probabilistic) */}
                        {interpretations.length > 0 && (
                            <div className="mb-8">
                                <div className="text-[9px] font-black text-on-surface-variant uppercase tracking-widest mb-3 flex items-center gap-2">
                                    <div className="w-1.5 h-1.5 rounded-full bg-primary" />
                                    Potential Legal Meanings
                                </div>
                                <div className="grid gap-4 md:grid-cols-2">
                                    {interpretations.map((item, idx) => (
                                        <div key={idx} className="p-4 bg-surface-container-lowest rounded-xl border border-outline-variant/30 relative overflow-hidden group">
                                            <div className="flex items-center justify-between mb-2">
                                                <span className="text-xs font-black uppercase text-primary tracking-tighter">
                                                    {item.label.replace(/_/g, ' ')}
                                                </span>
                                                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${item.confidence > 0.8 ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>
                                                    {Math.round(item.confidence * 100)}%
                                                </span>
                                            </div>
                                            <p className="text-[11px] text-on-surface-variant leading-relaxed">
                                                {item.description}
                                            </p>
                                            <div className="mt-3 flex flex-wrap gap-1.5">
                                                {item.supporting_behaviors.map(b => (
                                                    <span key={b} className="px-1.5 py-0.5 bg-secondary/5 text-secondary rounded text-[8px] font-bold uppercase">
                                                        {b.replace(/_/g, ' ')}
                                                    </span>
                                                ))}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Applicable Statutes - Ranked (Phase 4) */}
                        {applicableLaws.length > 0 && (
                            <div>
                                <div className="text-[9px] font-black text-on-surface-variant uppercase tracking-widest mb-3 flex items-center gap-2">
                                    <Scale size={14} className="text-primary" />
                                    Ranked Legal Statutes
                                </div>
                                <div className="space-y-4">
                                    {applicableLaws.map((law, idx) => (
                                        <div key={idx} className={`p-4 rounded-xl border relative ${
                                            law.rank === 1 ? 'bg-primary/5 border-primary/20 shadow-sm ring-1 ring-primary/5' : 'bg-surface/50 border-outline-variant/30'
                                        }`}>
                                            {/* Rank Badge */}
                                            <div className="absolute -top-2 -left-2 w-6 h-6 rounded-full bg-primary text-on-primary text-[10px] font-black flex items-center justify-center shadow-md">
                                                #{law.rank}
                                            </div>

                                            <div className="flex items-center justify-between mb-2 pl-2">
                                                <div className="flex items-center gap-2">
                                                     <span className="text-[10px] font-black text-primary uppercase leading-tight">
                                                        {law.law}
                                                    </span>
                                                    <div className="w-1 h-1 rounded-full bg-outline-variant" />
                                                    <span className="text-[10px] font-extrabold text-secondary">
                                                        {law.section}
                                                    </span>
                                                </div>
                                                <div className={`text-[9px] font-black uppercase px-2 py-0.5 rounded ${
                                                    law.confidence_level === 'high' ? 'bg-emerald-500/10 text-emerald-600' : 
                                                    law.confidence_level === 'medium' ? 'bg-amber-500/10 text-amber-600' : 
                                                    'bg-slate-500/10 text-slate-600'
                                                }`}>
                                                    {law.confidence_level} CONFIDENCE
                                                </div>
                                            </div>
                                            <p className="text-[11px] text-on-surface-variant mb-3 leading-relaxed pl-2 font-medium opacity-90">
                                                {law.reasoning}
                                            </p>
                                            <div className="flex items-center gap-4 pl-2">
                                                <div className="flex items-center gap-1.5">
                                                    <div className="text-[8px] uppercase font-black text-on-surface-variant/60">Behaviors:</div>
                                                    <div className="flex gap-1.5">
                                                        {law.based_on_behaviors.map(b => (
                                                            <span key={b} className="text-[8.5px] font-black text-secondary tracking-tight">
                                                                {b.replace(/_/g, ' ')}
                                                            </span>
                                                        ))}
                                                    </div>
                                                </div>
                                                <div className="flex items-center gap-1.5 ml-auto">
                                                    <div className="text-[8px] uppercase font-black text-on-surface-variant/60">Source:</div>
                                                     <div className="flex gap-1">
                                                        {law.based_on_interpretations.map(i => (
                                                            <span key={i} className="text-[8.5px] font-black text-primary tracking-tight">
                                                                {i.replace(/_/g, ' ')}
                                                            </span>
                                                        ))}
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                        
                        <p className="mt-4 text-[9px] text-on-surface-variant italic">
                            * Legal brain analysis separates objective observable behaviors from derived legal interpretations and statutory applicability.
                        </p>
                    </motion.div>
                )}

                {legalOutput && (
                    <motion.div
                        initial={{ opacity: 0, scale: 0.95 }}
                        animate={{ opacity: 1, scale: 1 }}
                        className="rounded-2xl border border-primary/20 bg-primary/5 p-6 shadow-sm mb-8"
                    >
                        <div className="flex items-center justify-between mb-4">
                            <div className="flex flex-col gap-1">
                                <div className="flex items-center gap-2 text-primary font-bold uppercase tracking-wider text-xs">
                                    <Scale size={16} />
                                    {isComplete ? "Final Legal Assessment" : "Draft Case Reasoning"}
                                </div>
                                {!isComplete && (
                                    <span className="text-[10px] text-on-surface-variant italic">
                                        * Subject to additional facts from the current interview.
                                    </span>
                                )}
                            </div>
                            {isComplete && (
                                <span className="flex items-center gap-1 text-emerald-600 font-bold text-xs bg-emerald-50 px-2 py-1 rounded-lg border border-emerald-200">
                                    <CheckCircle2 size={14} /> Factual Completeness Reached
                                </span>
                            )}
                        </div>

                        {secondaryIssues.length > 0 && (
                            <div className="mb-4">
                                <span className="text-[10px] font-bold uppercase text-on-surface-variant block mb-1.5">Related Concerns Detected:</span>
                                <div className="flex flex-wrap gap-2">
                                    {secondaryIssues.map(issue => (
                                        <span key={issue} className="px-2 py-0.5 bg-surface-container border border-outline-variant/30 rounded text-[10px] font-bold text-primary uppercase">
                                            {issue.replace('_', ' ')}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        )}
                        
                        <div className="grid gap-6 lg:grid-cols-2 mt-4">
                            <div className="space-y-4">
                                <div>
                                    <h4 className="text-sm font-bold text-on-surface mb-2">Legal Options</h4>
                                    <div className="flex flex-wrap gap-2">
                                        {legalOutput.legal_options.map(opt => (
                                            <span key={opt} className="px-3 py-1 bg-surface-container-lowest border border-outline-variant/30 rounded-lg text-xs font-medium">
                                                {opt}
                                            </span>
                                        ))}
                                    </div>
                                </div>
                                <div>
                                    <h4 className="text-sm font-bold text-on-surface mb-2">Applicable Laws</h4>
                                    <div className="space-y-2">
                                        {legalOutput.applicable_laws.map(law => (
                                            <div key={law} className="text-xs text-on-surface-variant bg-surface-container-low p-2 rounded-lg border border-outline-variant/10">
                                                âš–ï¸ {law}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>
                            
                            <div className="bg-surface-container-lowest rounded-xl p-4 border border-outline-variant/20 shadow-inner">
                                <h4 className="text-sm font-bold text-on-surface mb-3 flex items-center gap-2">
                                    <TrendingUp size={16} className="text-primary" />
                                    Next Action Steps
                                </h4>
                                <div className="space-y-3">
                                    {legalOutput.next_steps.map((step, idx) => (
                                        <div key={idx} className="flex gap-3 text-xs text-on-surface">
                                            <span className="w-5 h-5 rounded-full bg-surface-container flex items-center justify-center shrink-0 font-bold">
                                                {idx + 1}
                                            </span>
                                            {step}
                                        </div>
                                    ))}
                                </div>
                                
                                {canPrefillDocumentGenerator && (
                                    <button
                                        onClick={sendToGenerator}
                                        className="w-full mt-6 flex items-center justify-center gap-2 bg-primary text-on-primary py-3 rounded-lg text-xs font-bold hover:opacity-90 transition shadow-lg shadow-primary/20"
                                    >
                                        <FileText size={16} />
                                        Fill in Document Generator
                                    </button>
                                )}
                            </div>
                        </div>
                    </motion.div>
                )}

                {!legalOutput && canPrefillDocumentGenerator && (
                    <motion.div
                        initial={{ opacity: 0, y: 12 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="mb-8 rounded-2xl border border-primary/20 bg-primary/5 p-5 shadow-sm"
                    >
                        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                            <div>
                                <div className="text-xs font-bold uppercase tracking-[0.14em] text-primary">
                                    Document Generator Prefill
                                </div>
                                <p className="mt-1 text-sm text-on-surface-variant">
                                    Use this chat to prefill the document form, then review and generate the notice there.
                                </p>
                            </div>
                            <button
                                onClick={sendToGenerator}
                                className="flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-3 text-xs font-bold text-on-primary shadow-lg shadow-primary/20 transition hover:opacity-90"
                            >
                                <FileText size={16} />
                                Fill in Document Generator
                            </button>
                        </div>
                    </motion.div>
                )}
                </div>
            </div>

            <div className="border-t border-outline-variant/10 bg-surface/92 px-8 py-5 backdrop-blur-sm">
                <div className="mx-auto max-w-6xl">
                    <div className="relative overflow-hidden rounded-[30px] border border-outline-variant/15 bg-surface-container-lowest p-3 shadow-[0_18px_40px_rgba(72,75,106,0.08)]">
                    <textarea
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                                e.preventDefault();
                                handleSend();
                            }
                        }}
                        placeholder="Describe your legal issue (e.g., 'My salary is unpaid for 3 months')..."
                        disabled={isLoading}
                        className="h-24 w-full resize-none rounded-[24px] border border-transparent bg-surface-container-low px-6 py-5 pr-20 text-on-surface placeholder:text-on-surface-variant focus:border-primary/20 focus:ring-4 focus:ring-primary/10 transition-all shadow-inner disabled:opacity-70"
                    />
                    <button
                        onClick={handleSend}
                        disabled={isLoading || !input.trim()}
                        className="absolute bottom-6 right-6 rounded-2xl bg-primary p-4 text-on-primary shadow-xl shadow-primary/25 transition-all hover:scale-105 active:scale-95 disabled:opacity-50"
                    >
                        <Send size={22} />
                    </button>
                    </div>
                </div>
            </div>
        </div>
    );
};
