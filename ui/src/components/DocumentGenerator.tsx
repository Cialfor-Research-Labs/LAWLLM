import React, { useEffect, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import Markdown from 'react-markdown';
import type { Components } from 'react-markdown';
import { jsPDF } from 'jspdf';
import {
  FileText,
  Plus,
  Trash2,
  Loader2,
  Download,
  Copy,
  CheckCircle2,
  AlertCircle,
  ChevronDown,
  Scale,
  Shield,
  Zap,
  ArrowRight,
} from 'lucide-react';
import type { GeneratorPrefillRequest } from '../types/generatorPrefill';

// ---- Types ----

interface NoticeType {
  id: string;
  label: string;
}

interface NoticeResponse {
  ok: boolean;
  notice: string;
  laws_used: string[];
  notice_type: string;
  notice_type_label: string;
  confidence: number;
  confidence_label: string;
  meta?: Record<string, unknown>;
}

type Tone = 'firm' | 'aggressive' | 'polite';

interface GeneratorFormSnapshot {
  senderName: string;
  receiverName: string;
  senderAddress: string;
  receiverAddress: string;
  relationship: string;
  facts: string[];
  claim: string;
  noticeType: string;
  tone: Tone;
  deadline: number | '';
  customRelief: string;
}

interface GeneratorHistoryItem {
  id: string;
  title: string;
  created_at: string;
  preview: string;
  form: GeneratorFormSnapshot;
  result: NoticeResponse;
}

interface ApiErrorDetailItem {
  loc?: Array<string | number>;
  msg?: string;
  type?: string;
}

interface DocumentGeneratorProps {
  authToken: string;
  currentUserName?: string;
  currentUserEmail?: string;
  currentUserAdvocateAddress?: string;
  currentUserAdvocateMobile?: string;
  openHistoryRequest?: { id: string; nonce: number } | null;
  newSessionRequest?: number | null;
  prefillRequest?: GeneratorPrefillRequest | null;
  onHistoryChange?: (items: Array<{ id: string; title: string; created_at: string; preview?: string }>) => void;
  onActiveHistoryChange?: (id: string | null) => void;
}

// ---- API ----

function getApiBase(): string {
  const configured = import.meta.env.VITE_API_BASE_URL?.trim();
  if (configured) {
    return configured.replace(/\/$/, '');
  }
  return '/api';
}

const markdownComponents: Components = {
  strong: ({ children }) => <strong className="font-extrabold text-primary">{children}</strong>,
  p: ({ children }) => {
    const rawText = React.Children.toArray(children)
      .map((child) => (typeof child === 'string' ? child : ''))
      .join('')
      .trim();
    if (/^legal notice$/i.test(rawText)) {
      return (
        <p className="mb-4 text-center text-2xl font-black uppercase tracking-[0.08em] text-primary">
          LEGAL NOTICE
        </p>
      );
    }
    return <p className="mb-3 last:mb-0 leading-7">{children}</p>;
  },
  ol: ({ children }) => <ol className="mb-3 ml-5 list-decimal space-y-1">{children}</ol>,
  ul: ({ children }) => <ul className="mb-3 ml-5 list-disc space-y-1">{children}</ul>,
  li: ({ children }) => <li className="pl-1 leading-7 [&>p]:m-0">{children}</li>,
  h1: ({ children }) => <h1 className="text-xl font-bold text-primary mt-4 mb-2">{children}</h1>,
  h2: ({ children }) => <h2 className="text-lg font-bold text-primary mt-3 mb-2">{children}</h2>,
  h3: ({ children }) => <h3 className="text-base font-bold mt-2 mb-1">{children}</h3>,
  hr: () => <hr className="my-4 border-outline-variant/20" />,
};

const TONE_OPTIONS: { id: Tone; label: string; description: string; icon: React.ElementType }[] = [
  { id: 'polite', label: 'Polite', description: 'Professional and measured', icon: Shield },
  { id: 'firm', label: 'Firm', description: 'Direct and assertive', icon: Scale },
  { id: 'aggressive', label: 'Aggressive', description: 'Strong and urgent', icon: Zap },
];

const CONFIDENCE_COLORS: Record<string, string> = {
  high: 'text-emerald-700 bg-emerald-50 border-emerald-200',
  medium: 'text-amber-700 bg-amber-50 border-amber-200',
  low: 'text-orange-700 bg-orange-50 border-orange-200',
  very_low: 'text-rose-700 bg-rose-50 border-rose-200',
};

function FieldLabel({
  children,
  required = false,
}: {
  children: React.ReactNode;
  required?: boolean;
}) {
  return (
    <label className="field-label">
      {children}
      {required ? <span className="field-required">*</span> : null}
    </label>
  );
}

function getNoticeTypeIcon(id: string) {
  if (/salary|termination|harassment/.test(id)) return Shield;
  if (/builder|tenant|property|eviction|title/.test(id)) return Scale;
  if (/consumer|contract|money|cheque|maintenance/.test(id)) return FileText;
  return FileText;
}

const GENERATOR_HISTORY_KEY = 'vidhi_generator_history_v1';
const GENERATOR_HISTORY_LIMIT = 40;
const DOWNLOAD_DATE_FORMATTER = () => new Date().toISOString().slice(0, 10);

function formatApiError(payload: unknown, fallbackStatus: number): string {
  const detail = (payload as { detail?: unknown } | null)?.detail;

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        const entry = item as ApiErrorDetailItem;
        const field = Array.isArray(entry.loc) ? String(entry.loc[entry.loc.length - 1] || '').replace(/_/g, ' ') : '';
        const msg = String(entry.msg || '').trim();
        if (field && msg) {
          return `${field}: ${msg}`;
        }
        return msg;
      })
      .filter(Boolean);

    if (messages.length > 0) {
      return messages.join(' | ');
    }
  }

  if (typeof detail === 'string' && detail.trim()) {
    return detail.trim();
  }

  return `Server responded with ${fallbackStatus}`;
}

function escapeHtml(input: string): string {
  return String(input)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatNoticeAsWordHtml(notice: string): string {
  const lines = (notice || '').split('\n');
  return lines
    .map((line) => {
      const plain = line.replace(/\*\*/g, '').trim();
      if (/^legal notice$/i.test(plain)) {
        return '<div style="text-align:center;font-weight:700;font-size:22px;text-transform:uppercase;letter-spacing:1px;">LEGAL NOTICE</div>';
      }
      if (/^subject\s*:/i.test(plain)) {
        return `<div><strong>${escapeHtml(plain)}</strong></div>`;
      }
      const safe = escapeHtml(line).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
      return `<div>${safe || '&nbsp;'}</div>`;
    })
    .join('');
}

function normalizeBrokenListMarkers(notice: string): string {
  const text = String(notice || '');
  if (!text) return text;

  const markerOnlyRe = /^(\s*(?:[-*\u2022]|\d+[.)]|[A-Za-z][.)]|[IVXLCDMivxlcdm]+[.)]))\s*$/;
  const srcLines = text.split('\n');
  const out: string[] = [];
  let i = 0;

  while (i < srcLines.length) {
    const line = srcLines[i];
    const markerMatch = markerOnlyRe.exec(line);
    if (!markerMatch) {
      out.push(line);
      i += 1;
      continue;
    }

    let j = i + 1;
    while (j < srcLines.length && !srcLines[j].trim()) {
      j += 1;
    }

    if (j < srcLines.length) {
      out.push(`${markerMatch[1]} ${srcLines[j].trimStart()}`);
      i = j + 1;
      continue;
    }

    out.push(line);
    i += 1;
  }

  let normalized = out.join('\n');
  normalized = normalized.replace(
    /(^|\n)(\s*(?:[-*\u2022]|\d+[.)]|[A-Za-z][.)]|[IVXLCDMivxlcdm]+[.)]))\s*\n+(?=\s*\S)/g,
    '$1$2 ',
  );
  return normalized;
}

function applyAdvocateIdentityToNotice(
  notice: string,
  advocateName: string,
  advocateAddress: string,
  advocateMobile: string,
  advocateEmail: string,
  advocateContact: string,
): string {
  let text = notice || '';
  if (!text) return text;

  const name = advocateName.trim();
  const address = advocateAddress.trim();
  const mobile = advocateMobile.trim();
  const email = advocateEmail.trim();
  const contact = advocateContact.trim();

  if (name) {
    text = text.replace(/\[\s*your\s+name\s*\]/gi, name);
    text = text.replace(/^\s*your\s+name\s*[:\-]?\s*$/gim, `Name: ${name}`);
    text = text.replace(/^\s*name\s*[:\-]\s*(?:\[\s*your\s+name\s*\]|your\s+name)?\s*$/gim, `Name: ${name}`);
  }

  if (contact) {
    text = text.replace(/\[\s*your\s+contact\s+details?\s*\]/gi, contact);
    text = text.replace(/\[\s*contact\s+details?\s*\]/gi, contact);
    text = text.replace(/^\s*your\s+contact\s+details?\s*[:\-]?\s*$/gim, `Contact Details: ${contact}`);
    text = text.replace(/^\s*contact\s+details?\s*[:\-]\s*(?:\[\s*contact\s+details?\s*\])?\s*$/gim, `Contact Details: ${contact}`);
    text = text.replace(/^\s*email\s*[:\-]\s*$/gim, `Email: ${contact}`);
  }

  if (address) {
    text = text.replace(/\[\s*your\s+address\s*\]/gi, address);
    text = text.replace(/^\s*your\s+address\s*[:\-]?\s*$/gim, `Address: ${address}`);
  }

  if (mobile) {
    text = text.replace(/\[\s*your\s+mobile\s*\]/gi, mobile);
    text = text.replace(/^\s*mobile\s*[:\-]\s*(?:\[\s*your\s+mobile\s*\])?\s*$/gim, `Mobile: ${mobile}`);
  }

  if (email) {
    text = text.replace(/\[\s*your\s+email\s*\]/gi, email);
    text = text.replace(/^\s*email\s*[:\-]\s*(?:\[\s*your\s+email\s*\])?\s*$/gim, `Email: ${email}`);
  }

  return normalizeBrokenListMarkers(text);
}

function loadGeneratorHistoryFromStorage(): GeneratorHistoryItem[] {
  try {
    const raw = localStorage.getItem(GENERATOR_HISTORY_KEY);
    if (!raw) return [];

    const parsed = JSON.parse(raw) as Array<Partial<GeneratorHistoryItem>> | unknown;
    if (!Array.isArray(parsed)) return [];

    return parsed
      .filter((item): item is Partial<GeneratorHistoryItem> => Boolean(item && typeof item === 'object'))
      .map((item) => {
        const result = item.result;
        const form = item.form;
        if (
          !item.id ||
          !result ||
          typeof result.notice !== 'string' ||
          !form ||
          typeof form.senderName !== 'string' ||
          typeof form.receiverName !== 'string'
        ) {
          return null;
        }

        return {
          id: String(item.id),
          title: typeof item.title === 'string' && item.title.trim() ? item.title : 'Generated Legal Notice',
          created_at: typeof item.created_at === 'string' ? item.created_at : new Date().toISOString(),
          preview: typeof item.preview === 'string' ? item.preview : '',
          form: {
            senderName: form.senderName,
            receiverName: form.receiverName,
            senderAddress: typeof form.senderAddress === 'string' ? form.senderAddress : '',
            receiverAddress: typeof form.receiverAddress === 'string' ? form.receiverAddress : '',
            relationship: typeof form.relationship === 'string' ? form.relationship : '',
            facts: Array.isArray(form.facts) && form.facts.length
              ? form.facts.map((fact) => String(fact))
              : [''],
            claim: typeof form.claim === 'string' ? form.claim : '',
            noticeType: typeof form.noticeType === 'string' ? form.noticeType : 'auto',
            tone: form.tone === 'polite' || form.tone === 'aggressive' ? form.tone : 'firm',
            deadline: typeof form.deadline === 'number' ? form.deadline : '',
            customRelief: typeof form.customRelief === 'string' ? form.customRelief : '',
          },
          result: {
            ok: Boolean(result.ok),
            notice: result.notice,
            laws_used: Array.isArray(result.laws_used) ? result.laws_used.map((law) => String(law)) : [],
            notice_type: typeof result.notice_type === 'string' ? result.notice_type : 'auto',
            notice_type_label: typeof result.notice_type_label === 'string' ? result.notice_type_label : 'Generated Legal Notice',
            confidence: typeof result.confidence === 'number' ? result.confidence : 0,
            confidence_label: typeof result.confidence_label === 'string' ? result.confidence_label : 'unknown',
            meta: typeof result.meta === 'object' && result.meta !== null ? result.meta : undefined,
          },
        } satisfies GeneratorHistoryItem;
      })
      .filter((item): item is GeneratorHistoryItem => Boolean(item));
  } catch {
    return [];
  }
}

// ---- Component ----

export const DocumentGenerator = ({
  authToken,
  currentUserName = '',
  currentUserEmail = '',
  currentUserAdvocateAddress = '',
  currentUserAdvocateMobile = '',
  openHistoryRequest,
  newSessionRequest,
  prefillRequest,
  onHistoryChange,
  onActiveHistoryChange,
}: DocumentGeneratorProps) => {
  const apiBase = useMemo(() => getApiBase(), []);
  const authHeaders = useMemo(
    () => ({
      'Content-Type': 'application/json',
      Authorization: `Bearer ${authToken}`,
    }),
    [authToken],
  );

  const advocateName = currentUserName.trim();
  const advocateAddress = currentUserAdvocateAddress.trim();
  const advocateMobile = currentUserAdvocateMobile.trim();
  const advocateEmail = currentUserEmail.trim();
  const advocateContact = [
    advocateMobile ? `Mobile: ${advocateMobile}` : '',
    advocateEmail ? `Email: ${advocateEmail}` : '',
  ]
    .filter(Boolean)
    .join(' | ');

  // Form state
  const [senderName, setSenderName] = useState('');
  const [receiverName, setReceiverName] = useState('');
  const [senderAddress, setSenderAddress] = useState('');
  const [receiverAddress, setReceiverAddress] = useState('');
  const [relationship, setRelationship] = useState('');
  const [facts, setFacts] = useState<string[]>(['']);
  const [claim, setClaim] = useState('');
  const [noticeType, setNoticeType] = useState('auto');
  const [tone, setTone] = useState<Tone>('firm');
  const [deadline, setDeadline] = useState<number | ''>('');
  const [customRelief, setCustomRelief] = useState('');

  // Data
  const [noticeTypes, setNoticeTypes] = useState<NoticeType[]>([]);
  const [result, setResult] = useState<NoticeResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const [showTypeDropdown, setShowTypeDropdown] = useState(false);
  const [showDownloadChooser, setShowDownloadChooser] = useState(false);
  const [historyItems, setHistoryItems] = useState<GeneratorHistoryItem[]>(() => loadGeneratorHistoryFromStorage());
  const [activeHistoryId, setActiveHistoryId] = useState<string | null>(null);
  const normalizedNotice = useMemo(
    () => normalizeBrokenListMarkers(result?.notice || ''),
    [result?.notice],
  );

  // Fetch notice types on mount
  useEffect(() => {
    fetch(`${apiBase}/generate/notice-types`, {
      headers: { Authorization: `Bearer ${authToken}` },
    })
      .then((res) => {
        if (!res.ok) throw new Error(`Unable to load notice types (${res.status})`);
        return res.json();
      })
      .then((data) => {
        if (data.ok) setNoticeTypes(data.types || []);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Failed to load notice types');
      });
  }, [apiBase, authToken]);

  const toHistorySummary = (items: GeneratorHistoryItem[]) =>
    items.map((item) => ({
      id: item.id,
      title: item.title,
      created_at: item.created_at,
      preview: item.preview,
    }));

  const applyHistoryItem = (item: GeneratorHistoryItem) => {
    setSenderName(item.form.senderName);
    setReceiverName(item.form.receiverName);
    setSenderAddress(item.form.senderAddress || '');
    setReceiverAddress(item.form.receiverAddress || '');
    setRelationship(item.form.relationship);
    setFacts(item.form.facts?.length ? item.form.facts : ['']);
    setClaim(item.form.claim);
    setNoticeType(item.form.noticeType || 'auto');
    setTone(item.form.tone || 'firm');
    setDeadline(item.form.deadline ?? '');
    setCustomRelief(item.form.customRelief || '');
    setResult({
      ...item.result,
      notice: normalizeBrokenListMarkers(item.result.notice),
    });
    setError('');
    setActiveHistoryId(item.id);
  };

  const applyPrefill = (request: GeneratorPrefillRequest['payload']) => {
    setSenderName(request.senderName || '');
    setReceiverName(request.receiverName || '');
    setSenderAddress(request.senderAddress || '');
    setReceiverAddress(request.receiverAddress || '');
    setRelationship(request.relationship || '');
    setFacts(request.facts?.length ? request.facts : ['']);
    setClaim(request.claim || '');
    setNoticeType(request.noticeType || 'auto');
    setTone(request.tone || 'firm');
    setDeadline(request.deadline ?? '');
    setCustomRelief(request.customRelief || '');
    setResult(null);
    setError('');
    setCopied(false);
    setShowTypeDropdown(false);
    setShowDownloadChooser(false);
    setActiveHistoryId(null);
  };

  useEffect(() => {
    localStorage.setItem(GENERATOR_HISTORY_KEY, JSON.stringify(historyItems));
    onHistoryChange?.(toHistorySummary(historyItems));
  }, [historyItems, onHistoryChange]);

  useEffect(() => {
    onActiveHistoryChange?.(activeHistoryId);
  }, [activeHistoryId, onActiveHistoryChange]);

  useEffect(() => {
    if (!openHistoryRequest?.id) return;
    const target = historyItems.find((item) => item.id === openHistoryRequest.id);
    if (!target) return;
    applyHistoryItem(target);
  }, [openHistoryRequest, historyItems]);

  const pushHistoryItem = (generated: NoticeResponse) => {
    const snapshot: GeneratorFormSnapshot = {
      senderName,
      receiverName,
      senderAddress,
      receiverAddress,
      relationship,
      facts,
      claim,
      noticeType,
      tone,
      deadline,
      customRelief,
    };
    const createdAt = new Date().toISOString();
    const titleBase = claim.trim() || generated.notice_type_label || 'Generated Legal Notice';
    const item: GeneratorHistoryItem = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      title: titleBase.length > 72 ? `${titleBase.slice(0, 69)}...` : titleBase,
      created_at: createdAt,
      preview: generated.notice.slice(0, 120).replace(/\s+/g, ' ').trim(),
      form: snapshot,
      result: generated,
    };
    setHistoryItems((prev) => [item, ...prev].slice(0, GENERATOR_HISTORY_LIMIT));
    setActiveHistoryId(item.id);
  };

  const addFact = () => setFacts((prev) => [...prev, '']);
  const removeFact = (index: number) => setFacts((prev) => prev.filter((_, i) => i !== index));
  const updateFact = (index: number, value: string) =>
    setFacts((prev) => prev.map((f, i) => (i === index ? value : f)));

  const validateForm = (): string | null => {
    if (senderName.trim().length < 2) return 'Sender name must be at least 2 characters.';
    if (receiverName.trim().length < 2) return 'Receiver name must be at least 2 characters.';
    if (senderAddress.trim().length < 5) return 'Sender address must be at least 5 characters.';
    if (receiverAddress.trim().length < 5) return 'Receiver address must be at least 5 characters.';
    if (claim.trim().length < 2) return 'Claim / Issue must be at least 2 characters.';
    if (!facts.some((f) => f.trim())) return 'Please add at least one fact of the case.';
    return null;
  };

  const validationError = validateForm();
  const isFormValid = validationError == null;

  const handleGenerate = async () => {
    if (!isFormValid) {
      setError(validationError || 'Please complete the required fields.');
      return;
    }
    if (!advocateAddress || !advocateMobile) {
      setError('Please complete Advocate Address and Advocate Mobile in Settings > Details before generating a notice.');
      return;
    }
    setIsLoading(true);
    setError('');
    setResult(null);

    try {
      const body: Record<string, unknown> = {
        sender_name: senderName.trim(),
        receiver_name: receiverName.trim(),
        sender_address: senderAddress.trim(),
        receiver_address: receiverAddress.trim(),
        relationship: relationship.trim(),
        facts: facts.filter((f) => f.trim()),
        claim: claim.trim(),
        notice_type: noticeType,
        tone,
      };
      if (advocateName) body.advocate_name = advocateName;
      if (advocateAddress) body.advocate_address = advocateAddress;
      if (advocateMobile) body.advocate_mobile = advocateMobile;
      if (advocateContact) body.advocate_contact = advocateContact;
      if (deadline) body.custom_deadline = Number(deadline);
      if (customRelief.trim()) {
        body.custom_relief = customRelief
          .split('\n')
          .map((l) => l.trim())
          .filter(Boolean);
      }

      const response = await fetch(`${apiBase}/generate/notice`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(formatApiError(payload, response.status));
      }
      const data: NoticeResponse = await response.json();
      const normalized: NoticeResponse = {
        ...data,
        notice: applyAdvocateIdentityToNotice(
          data.notice,
          advocateName,
          advocateAddress,
          advocateMobile,
          advocateEmail,
          advocateContact,
        ),
      };
      setResult(normalized);
      pushHistoryItem(normalized);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to generate notice');
    } finally {
      setIsLoading(false);
    }
  };

  const handleCopy = () => {
    if (!normalizedNotice) return;
    navigator.clipboard.writeText(normalizedNotice);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadWord = () => {
    if (!normalizedNotice) return;
    const safeNotice = formatNoticeAsWordHtml(normalizedNotice);
    const htmlDoc = `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <title>Legal Notice</title>
</head>
<body style="font-family: 'Times New Roman', serif; line-height: 1.5; margin: 28px;">
  ${safeNotice}
</body>
</html>`;
    const blob = new Blob(['\ufeff', htmlDoc], { type: 'application/msword;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `legal_notice_${DOWNLOAD_DATE_FORMATTER()}.doc`;
    a.click();
    URL.revokeObjectURL(url);
    setShowDownloadChooser(false);
  };

  const handleDownloadPdf = () => {
    if (!normalizedNotice) return;
    const doc = new jsPDF({ unit: 'pt', format: 'a4' });
    const pageWidth = doc.internal.pageSize.getWidth();
    const pageHeight = doc.internal.pageSize.getHeight();
    const margin = 48;
    const lineHeight = 16;
    const textWidth = pageWidth - margin * 2;

    let y = margin;

    const rawLines = normalizedNotice.split('\n');
    for (const rawLine of rawLines) {
      const cleanLine = rawLine.replace(/\*\*(.*?)\*\*/g, '$1');
      const isHeadingLine = /^\s*legal\s+notice\s*$/i.test(cleanLine.trim());
      const isSubjectLine = /^\s*subject:/i.test(cleanLine.trim());
      doc.setFont('times', isHeadingLine || isSubjectLine ? 'bold' : 'normal');
      doc.setFontSize(isHeadingLine ? 16 : 11);

      const wrappedLines = doc.splitTextToSize(cleanLine, textWidth) as string[];
      for (const line of wrappedLines) {
        if (y > pageHeight - margin) {
          doc.addPage();
          y = margin;
        }
        if (isHeadingLine) {
          doc.text(line.trim().toUpperCase(), pageWidth / 2, y, { align: 'center' });
        } else {
          doc.text(line, margin, y);
        }
        y += lineHeight;
      }
    }

    doc.save(`legal_notice_${DOWNLOAD_DATE_FORMATTER()}.pdf`);
    setShowDownloadChooser(false);
  };

  const handleReset = () => {
    setSenderName('');
    setReceiverName('');
    setSenderAddress('');
    setReceiverAddress('');
    setRelationship('');
    setFacts(['']);
    setClaim('');
    setNoticeType('auto');
    setTone('firm');
    setDeadline('');
    setCustomRelief('');
    setResult(null);
    setError('');
    setActiveHistoryId(null);
  };

  useEffect(() => {
    if (newSessionRequest == null) {
      return;
    }
    handleReset();
  }, [newSessionRequest]);

  useEffect(() => {
    if (!prefillRequest?.payload) {
      return;
    }
    applyPrefill(prefillRequest.payload);
  }, [prefillRequest]);

  const selectedTypeLabel = noticeType === 'auto'
    ? 'Auto-detect'
    : noticeTypes.find((t) => t.id === noticeType)?.label || noticeType;
  const previewFacts = facts.map((fact) => fact.trim()).filter(Boolean);
  const previewSections = [
    { label: 'Sender', value: senderName.trim() || 'Not provided' },
    { label: 'Receiver', value: receiverName.trim() || 'Not provided' },
    { label: 'Relationship', value: relationship.trim() || 'Not specified' },
    { label: 'Deadline', value: deadline ? `${deadline} days` : 'Default by notice type' },
  ];

  return (
    <div className="flex flex-1 flex-col overflow-hidden px-4 py-4 sm:px-6 sm:py-6 lg:px-8">
      <div className="grid h-full min-h-0 gap-6 xl:grid-cols-[minmax(420px,520px)_minmax(0,1fr)]">
      <div className="app-shell-panel flex min-h-0 flex-col overflow-hidden">
        <div className="border-b border-outline-variant/70 px-6 py-5">
          <p className="section-kicker">Notice generator</p>
          <h2 className="mt-1 text-2xl font-semibold text-secondary">Create a legal notice</h2>
          <p className="mt-2 text-sm leading-7 text-on-surface-variant">
            The generation flow is unchanged. The form is simply organized into clearer sections so it is easier to review before drafting.
          </p>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-5 no-scrollbar">
          <div className="app-shell-panel bg-surface-container-low px-5 py-5">
          {/* Notice Type */}
          <div className="relative">
            <FieldLabel>Notice type</FieldLabel>
            <button
              type="button"
              onClick={() => setShowTypeDropdown(!showTypeDropdown)}
              className="text-field flex items-center justify-between text-left"
            >
              <span className="flex items-center gap-3">
                <FileText size={16} className="text-primary" />
                <span>{selectedTypeLabel}</span>
              </span>
              <ChevronDown size={16} className={`transition-transform ${showTypeDropdown ? 'rotate-180' : ''}`} />
            </button>
            <AnimatePresence>
              {showTypeDropdown && (
                <motion.div
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  className="app-shell-panel absolute top-full z-30 mt-2 w-full overflow-hidden p-2"
                >
                  <button
                    type="button"
                    onClick={() => { setNoticeType('auto'); setShowTypeDropdown(false); }}
                    className={`flex w-full items-center gap-3 rounded-2xl px-3 py-3 text-left text-sm transition ${noticeType === 'auto' ? 'bg-primary/10 font-medium text-primary' : 'text-on-surface hover:bg-surface-container-low'}`}
                  >
                    Auto-detect from claim
                  </button>
                  {noticeTypes.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => { setNoticeType(t.id); setShowTypeDropdown(false); }}
                      className={`flex w-full items-center gap-3 rounded-2xl px-3 py-3 text-left text-sm transition ${noticeType === t.id ? 'bg-primary/10 font-medium text-primary' : 'text-on-surface hover:bg-surface-container-low'}`}
                    >
                      {React.createElement(getNoticeTypeIcon(t.id), { size: 16, className: 'text-primary' })}
                      {t.label}
                    </button>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
          </div>

          <div className="app-shell-panel bg-surface-container-low px-5 py-5">
          <div className="mb-4">
            <p className="section-kicker">Parties involved</p>
            <h3 className="mt-1 text-base font-semibold text-on-surface">Sender and receiver</h3>
          </div>
          {/* Sender & Receiver */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <FieldLabel required>Sender name</FieldLabel>
              <input
                value={senderName}
                onChange={(e) => setSenderName(e.target.value)}
                placeholder="e.g. Rajesh Kumar"
                minLength={2}
                className="text-field"
              />
            </div>
            <div>
              <FieldLabel required>Receiver name</FieldLabel>
              <input
                value={receiverName}
                onChange={(e) => setReceiverName(e.target.value)}
                placeholder="e.g. ABC Pvt Ltd"
                minLength={2}
                className="text-field"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <FieldLabel required>Sender address</FieldLabel>
              <input
                value={senderAddress}
                onChange={(e) => setSenderAddress(e.target.value)}
                placeholder="e.g. Kaushik, Delhi, India"
                minLength={5}
                className="text-field"
              />
            </div>
            <div>
              <FieldLabel required>Receiver address</FieldLabel>
              <input
                value={receiverAddress}
                onChange={(e) => setReceiverAddress(e.target.value)}
                placeholder="e.g. BMS Pvt Ltd, Bengaluru, Karnataka"
                minLength={5}
                className="text-field"
              />
            </div>
          </div>
          </div>

          <div className="app-shell-panel bg-surface-container-low px-5 py-5">
          <div className="mb-4">
            <p className="section-kicker">Notice details</p>
            <h3 className="mt-1 text-base font-semibold text-on-surface">Claim and supporting facts</h3>
          </div>
          {/* Relationship */}
          <div>
            <FieldLabel>Relationship</FieldLabel>
            <input
              value={relationship}
              onChange={(e) => setRelationship(e.target.value)}
              placeholder="e.g. employee-employer, landlord-tenant"
              className="text-field"
            />
          </div>

          {/* Claim */}
          <div>
            <FieldLabel required>Claim or issue</FieldLabel>
            <input
              value={claim}
              onChange={(e) => setClaim(e.target.value)}
              placeholder="e.g. unpaid salary for 3 months"
              minLength={2}
              className="text-field"
            />
          </div>

          {/* Facts */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <FieldLabel required>Facts of the case</FieldLabel>
              <button type="button" onClick={addFact} className="secondary-button px-3 py-2 text-xs">
                <Plus size={14} /> Add Fact
              </button>
            </div>
            <div className="space-y-2">
              {facts.map((fact, index) => (
                <div key={index} className="flex gap-2">
                  <div className="flex h-12 w-10 items-center justify-center rounded-2xl bg-surface-container text-xs font-bold text-on-surface-variant/60">{index + 1}</div>
                  <input
                    value={fact}
                    onChange={(e) => updateFact(index, e.target.value)}
                    placeholder={index === 0 ? 'e.g. Worked from January to March 2024' : 'Add another fact'}
                    className="text-field flex-1"
                  />
                  {facts.length > 1 && (
                    <button type="button" onClick={() => removeFact(index)} className="neutral-button px-3 text-on-surface-variant">
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Tone */}
          <div>
            <FieldLabel>Tone</FieldLabel>
            <div className="grid grid-cols-3 gap-2">
              {TONE_OPTIONS.map((option) => (
                <button
                  key={option.id}
                  type="button"
                  onClick={() => setTone(option.id)}
                  className={`flex flex-col items-center gap-1.5 rounded-2xl border p-3 text-xs transition ${
                    tone === option.id
                      ? 'border-primary bg-primary/10 text-primary font-semibold'
                      : 'border-outline-variant/70 bg-surface-container-lowest text-on-surface-variant hover:border-primary/20'
                  }`}
                >
                  <option.icon size={16} />
                  <span className="font-semibold">{option.label}</span>
                  <span className="text-[10px] opacity-70">{option.description}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Deadline */}
          <div>
            <label className="field-label">
              Custom Deadline (days) <span className="font-normal normal-case tracking-normal text-on-surface-variant/60">- optional</span>
            </label>
            <input
              type="number"
              min={1}
              max={90}
              value={deadline}
              onChange={(e) => setDeadline(e.target.value ? Number(e.target.value) : '')}
              placeholder="Default based on notice type"
              className="text-field"
            />
          </div>

          {/* Custom Relief */}
          <div>
            <label className="field-label">
              Custom Relief <span className="font-normal normal-case tracking-normal text-on-surface-variant/60">- optional, one per line</span>
            </label>
            <textarea
              value={customRelief}
              onChange={(e) => setCustomRelief(e.target.value)}
              placeholder="e.g.&#10;Pay outstanding salary of Rs 3,00,000&#10;Issue experience certificate"
              rows={3}
              className="w-full px-4 py-3 bg-surface-container-low border border-outline-variant/20 rounded-xl text-sm text-on-surface placeholder:text-on-surface-variant/50 focus:ring-2 focus:ring-primary/10 focus:border-primary/30 transition resize-none"
            />
          </div>
        </div>
        </div>

        {/* Generate Button */}
        <div className="border-t border-outline-variant/70 px-6 py-5">
          {!isFormValid && validationError ? (
            <p className="mb-3 text-sm text-on-surface-variant">{validationError}</p>
          ) : null}
          <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={handleGenerate}
            disabled={!isFormValid || isLoading}
            className="primary-button min-w-52"
          >
            {isLoading ? (
              <>
                <Loader2 size={18} className="animate-spin" />
                Creating document...
              </>
            ) : (
              <>
                <ArrowRight size={18} />
                Create document
              </>
            )}
          </button>
          {result && (
            <button
              type="button"
              onClick={handleReset}
              className="neutral-button"
            >
              Reset and start new
            </button>
          )}
          </div>
        </div>
      </div>

      {/* RIGHT: Preview */}
      <div className="min-h-0 overflow-hidden">
        <div className="flex h-full flex-col overflow-hidden">
        <AnimatePresence mode="wait">
          {!result && !isLoading && !error ? (
            <motion.div
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="app-shell-panel flex-1 overflow-y-auto p-6"
            >
              <div className="mx-auto flex h-full max-w-3xl flex-col gap-6">
                <div>
                  <p className="section-kicker">Live preview</p>
                  <h3 className="mt-1 text-2xl font-semibold text-secondary">Review the notice structure as you fill the form</h3>
                  <p className="mt-2 text-sm leading-7 text-on-surface-variant">
                    This preview now uses the full right panel instead of leaving it empty. You can sanity-check the facts, parties, and requested relief before generating the final document.
                  </p>
                </div>

                <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
                  <div className="app-shell-panel bg-surface-container-low px-5 py-5">
                    <div className="mb-4 flex items-center gap-3">
                      <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                        <FileText size={20} />
                      </div>
                      <div>
                        <div className="text-sm font-medium text-on-surface">Draft overview</div>
                        <div className="text-sm text-on-surface-variant">{selectedTypeLabel}</div>
                      </div>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      {previewSections.map((section) => (
                        <div key={section.label} className="rounded-2xl border border-outline-variant/70 bg-surface-container-lowest px-4 py-3">
                          <div className="text-[11px] text-on-surface-variant">{section.label}</div>
                          <div className="mt-1 text-sm font-medium text-on-surface">{section.value}</div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="app-shell-panel bg-surface-container-low px-5 py-5">
                    <div className="mb-3 text-sm font-medium text-on-surface">Requested relief</div>
                    <div className="rounded-2xl border border-dashed border-outline-variant/70 bg-surface-container-lowest px-4 py-4 text-sm leading-7 text-on-surface-variant">
                      {customRelief.trim()
                        ? customRelief
                            .split('\n')
                            .map((line) => line.trim())
                            .filter(Boolean)
                            .map((line, index) => <div key={`${line}-${index}`}>{line}</div>)
                        : 'No custom relief entered yet. The generator will use your issue, facts, and notice type to shape the final demands.'}
                    </div>
                  </div>
                </div>

                <div className="app-shell-panel bg-surface-container-low px-5 py-5">
                  <div className="mb-3 flex items-center justify-between">
                    <div>
                      <div className="text-sm font-medium text-on-surface">Case facts preview</div>
                      <div className="text-sm text-on-surface-variant">These points become the narrative backbone of the final notice.</div>
                    </div>
                    <span className="status-pill">{previewFacts.length} fact{previewFacts.length === 1 ? '' : 's'}</span>
                  </div>
                  <div className="space-y-3">
                    {previewFacts.length > 0 ? (
                      previewFacts.map((fact, index) => (
                        <div key={`${fact}-${index}`} className="flex gap-3 rounded-2xl border border-outline-variant/70 bg-surface-container-lowest px-4 py-3">
                          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                            {index + 1}
                          </div>
                          <p className="text-sm leading-7 text-on-surface">{fact}</p>
                        </div>
                      ))
                    ) : (
                      <div className="rounded-2xl border border-dashed border-outline-variant/70 bg-surface-container-lowest px-4 py-5 text-sm text-on-surface-variant">
                        Add at least one fact to see the draft structure take shape here.
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </motion.div>
          ) : isLoading ? (
            <motion.div
              key="loading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="app-shell-panel flex flex-1 items-center justify-center p-8"
            >
              <div className="text-center space-y-6">
                <div className="relative w-20 h-20 mx-auto">
                  <div className="absolute inset-0 border-4 border-primary/10 rounded-full" />
                  <div className="absolute inset-0 border-4 border-primary border-t-transparent rounded-full animate-spin" />
                  <div className="absolute inset-3 border-4 border-primary/20 border-b-transparent rounded-full animate-spin" style={{ animationDirection: 'reverse', animationDuration: '1.5s' }} />
                </div>
                <div>
                  <h3 className="text-xl font-semibold text-secondary">Generating legal notice</h3>
                  <p className="text-sm text-on-surface-variant mt-2">
                    Pass 1: Drafting -> Pass 2: Refining legal language...
                  </p>
                </div>
              </div>
            </motion.div>
          ) : error ? (
            <motion.div
              key="error"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="app-shell-panel flex flex-1 items-center justify-center p-8"
            >
              <div className="max-w-md rounded-2xl border border-rose-200 bg-rose-50 p-8 text-center">
                <AlertCircle size={40} className="text-rose-500 mx-auto mb-4" />
                <h3 className="text-lg font-semibold text-rose-900">Generation failed</h3>
                <p className="text-sm text-rose-700 mt-2">{error}</p>
                <button
                  type="button"
                  onClick={() => setError('')}
                  className="mt-4 rounded-2xl bg-rose-100 px-6 py-2 text-sm font-semibold text-rose-800 transition hover:bg-rose-200"
                >
                  Dismiss
                </button>
              </div>
            </motion.div>
          ) : result ? (
            <motion.div
              key="result"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="app-shell-panel flex flex-1 flex-col overflow-hidden"
            >
              {/* Result Header */}
              <div className="flex flex-wrap items-center justify-between gap-4 border-b border-outline-variant/70 bg-surface-container-low px-6 py-5">
                <div className="flex flex-wrap items-center gap-3">
                  <div className={`px-3 py-1.5 rounded-full border text-xs font-bold ${CONFIDENCE_COLORS[result.confidence_label] || CONFIDENCE_COLORS.medium}`}>
                    Confidence: {Math.round(result.confidence * 100)}%
                  </div>
                  <span className="text-xs text-on-surface-variant">
                    Type: <strong className="text-on-surface">{result.notice_type_label}</strong>
                  </span>
                  <span className="text-xs text-on-surface-variant">
                    Laws: <strong className="text-on-surface">{result.laws_used.length}</strong>
                  </span>
                </div>
                <div className="relative flex items-center gap-2">
                  <button
                    type="button"
                    onClick={handleCopy}
                    className="neutral-button px-4 py-2 text-xs"
                  >
                    {copied ? <CheckCircle2 size={14} className="text-emerald-600" /> : <Copy size={14} />}
                    {copied ? 'Copied!' : 'Copy'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowDownloadChooser((prev) => !prev)}
                    aria-label="Open download options"
                    className="primary-button h-10 w-10 px-0 py-0"
                  >
                    <Download size={16} />
                  </button>

                  <AnimatePresence>
                    {showDownloadChooser && (
                      <>
                        <button
                          type="button"
                          aria-label="Close download options"
                          onClick={() => setShowDownloadChooser(false)}
                          className="fixed inset-0 z-20 bg-transparent"
                        />
                        <motion.div
                          initial={{ opacity: 0, x: 20 }}
                          animate={{ opacity: 1, x: 0 }}
                          exit={{ opacity: 0, x: 20 }}
                          transition={{ duration: 0.18 }}
                          className="app-shell-panel absolute right-0 top-12 z-30 min-w-44 p-2"
                        >
                          <div className="px-2 py-1 text-[11px] text-on-surface-variant">
                            Download as
                          </div>
                          <button
                            type="button"
                            onClick={handleDownloadPdf}
                            className="w-full rounded-2xl px-3 py-2.5 text-left text-sm font-medium text-on-surface transition hover:bg-surface-container-low"
                          >
                            PDF
                          </button>
                          <button
                            type="button"
                            onClick={handleDownloadWord}
                            className="w-full rounded-2xl px-3 py-2.5 text-left text-sm font-medium text-on-surface transition hover:bg-surface-container-low"
                          >
                            Word
                          </button>
                        </motion.div>
                      </>
                    )}
                  </AnimatePresence>
                </div>
              </div>

              {/* Notice Content */}
              <div className="flex-1 overflow-y-auto p-6 no-scrollbar">
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.1 }}
                  className="mx-auto max-w-3xl"
                >
                  {/* Notice Preview Card */}
                  <div className="overflow-hidden rounded-[24px] border border-outline-variant/70 bg-surface-container-lowest shadow-ambient">
                    <div className="border-b border-outline-variant/70 bg-primary/[.03] px-8 py-4">
                      <div className="flex items-center gap-3">
                        <FileText size={18} className="text-primary" />
                        <span className="text-sm font-medium text-primary">Generated legal notice</span>
                      </div>
                    </div>
                    <div className="px-8 py-6 text-on-surface text-sm leading-relaxed font-body markdown-body whitespace-pre-wrap">
                      <Markdown components={markdownComponents}>{normalizedNotice}</Markdown>
                    </div>
                  </div>

                  {/* Laws Used */}
                  {result.laws_used.length > 0 && (
                    <motion.div
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.2 }}
                      className="mt-6 rounded-[24px] border border-outline-variant/70 bg-surface-container-lowest p-6"
                    >
                      <div className="mb-3 text-sm font-medium text-primary">
                        Authorities relied upon
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {result.laws_used.map((law, i) => (
                          <span
                            key={i}
                            className="inline-block px-3 py-1.5 bg-surface-container-low rounded-lg text-xs font-semibold text-on-surface border border-outline-variant/10"
                          >
                            {law}
                          </span>
                        ))}
                      </div>
                    </motion.div>
                  )}

                  {/* Metadata */}
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.3 }}
                    className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-[11px] text-on-surface-variant/60 px-2"
                  >
                    <span>Tone: {result.meta?.tone as string || tone}</span>
                    <span>Deadline: {(result.meta?.deadline_days as number) || 15} days</span>
                    <span>Heuristics: {(result.meta?.heuristics_matched as number) || 0} matched</span>
                    <span>RAG: {result.meta?.has_retrieval_context ? 'Active' : 'None'}</span>
                  </motion.div>
                </motion.div>
              </div>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>
    </div>
    </div>
    </div>
  );
};
