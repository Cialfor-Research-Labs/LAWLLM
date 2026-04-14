import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import Markdown from 'react-markdown';
import type { Components } from 'react-markdown';
import { 
  CheckCircle2, 
  Loader2, 
  RotateCcw, 
  Scale, 
  Send, 
  Sparkles, 
  User, 
  FileText, 
  TrendingUp 
} from 'lucide-react';

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

const RESET_GREETING = 'Legal Interview reset. Describe your situation to begin a new case assessment.';

interface LegalChatProps {
    authToken: string;
    openSessionRequest?: { sessionId: string; nonce: number } | null;
    onChatSessionsChange?: (sessions: ChatSessionSummary[]) => void;
    onActiveSessionChange?: (sessionId: string | null) => void;
}

function getApiBase(): string {
  const configured = import.meta.env.VITE_API_BASE_URL?.trim();
  if (configured) {
    return configured.replace(/\/$/, '');
  }
  return '/api';
}

function formatInterviewResponse(data: InterviewChatResponse) {
    const out = data.legal_output;
    
    if (!out) {
        const lines = [
            `**Status**: ⚠️ ${data.status.replace('_', ' ').toUpperCase()}`,
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
        `**Status**: ${data.is_complete ? '✅ Case Complete' : '📝 Interviewing...'}`,
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
        lines.push('**📁 Evidence & Proof Checklist**');
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
        lines.push('💼 **Legal Notice Ready**: You can view the full draft in the "Document Generator" tab.');
    }
    
    return lines.join('\n').trim();
}


export const LegalChat = ({
    authToken,
    openSessionRequest,
    onChatSessionsChange,
    onActiveSessionChange,
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
                content: RESET_GREETING,
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
                setMessages((prev) => [...prev, { role: 'assistant', content: formatInterviewResponse(data) }]);
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

    const sendToGenerator = () => {
        if (!legalOutput?.notice_draft) return;
        localStorage.setItem('pending_legal_notice', legalOutput.notice_draft);
        alert('Legal Notice draft sent to Document Generator tab!');
    };

    return (
        <div className="flex-1 flex flex-col h-full bg-surface-container-low overflow-hidden">
            <div className="px-8 py-6 border-b border-outline-variant/10 bg-surface">
                <div className="flex items-center justify-between gap-4">
                    <div>
                        <h2 className="text-2xl font-headline font-bold text-primary">Vidhi AI: Intelligent Interviewer</h2>
                        <p className="text-sm text-on-surface-variant">
                            Unified Legal Case Engine · Factual Extraction · FIRAC Analysis
                        </p>
                    </div>
                    <div className="flex items-center gap-3">
                        <div className="flex flex-col items-end mr-4">
                            <span className="text-[10px] font-bold uppercase text-on-surface-variant">
                                {status === "clarification_required" ? "⚠️ Signal Low" : status === "complete" ? "✅ Factual Certainty" : "🔍 Analyzing Situation"}
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
                        <button
                            onClick={resetConversation}
                            className="inline-flex items-center gap-2 rounded-xl border border-outline-variant/30 bg-white px-4 py-2 text-xs font-semibold uppercase tracking-wide text-on-surface hover:bg-surface-container-low"
                        >
                            <RotateCcw size={14} />
                            New Session
                        </button>
                    </div>
                </div>
            </div>

            <div ref={scrollRef} className="flex-1 overflow-y-auto p-8 space-y-8 no-scrollbar">
                <AnimatePresence initial={false}>
                    {messages.map((msg, idx) => (
                        <motion.div
                            key={`${msg.role}-${idx}`}
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                        >
                            <div className={`flex max-w-[85%] space-x-4 ${msg.role === 'user' ? 'flex-row-reverse space-x-reverse' : ''}`}>
                                <div
                                    className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 ${
                                        msg.role === 'user' ? 'bg-secondary-container text-on-secondary-container' : 'bg-primary text-white'
                                    }`}
                                >
                                    {msg.role === 'user' ? <User size={18} /> : <Sparkles size={18} />}
                                </div>
                                <div
                                    className={`rounded-2xl border px-6 py-5 shadow-sm ${
                                        msg.role === 'user'
                                            ? 'bg-primary text-white border-primary/20'
                                            : 'bg-white text-on-surface border-outline-variant/10'
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
                        <div className="flex items-center gap-4 rounded-2xl border border-outline-variant/10 bg-white px-5 py-4 shadow-sm">
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
                                        <div key={evt.sequence} className="flex gap-3 text-xs bg-white/50 p-3 rounded-lg border border-amber-200/50">
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
                                        <div key={p.id} className="p-3 bg-white/50 rounded-lg border border-amber-200/50 text-xs">
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
                                                <div key={i} className="flex justify-between items-center p-2 bg-white/80 rounded border border-amber-200/50 text-xs text-amber-900">
                                                    <span>{f.context}</span>
                                                    <span className="font-bold">₹{f.amount.toLocaleString()}</span>
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
                                            setMessages((prev) => [...prev, { role: 'assistant', content: formatInterviewResponse(data) }]);
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
                                className="flex-1 bg-primary text-white py-3 rounded-xl font-bold text-xs uppercase tracking-widest hover:opacity-90 shadow-lg shadow-primary/20"
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
                                        <div key={idx} className="px-3 py-1.5 bg-white border border-outline-variant/30 rounded-lg text-[10px] font-bold text-primary flex items-center gap-2 shadow-sm">
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
                                        <div key={idx} className="p-4 bg-white rounded-xl border border-outline-variant/30 relative overflow-hidden group">
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
                                            <span key={opt} className="px-3 py-1 bg-white border border-outline-variant/30 rounded-lg text-xs font-medium">
                                                {opt}
                                            </span>
                                        ))}
                                    </div>
                                </div>
                                <div>
                                    <h4 className="text-sm font-bold text-on-surface mb-2">Applicable Laws</h4>
                                    <div className="space-y-2">
                                        {legalOutput.applicable_laws.map(law => (
                                            <div key={law} className="text-xs text-on-surface-variant bg-white/50 p-2 rounded-lg border border-outline-variant/10">
                                                ⚖️ {law}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>
                            
                            <div className="bg-white rounded-xl p-4 border border-outline-variant/20 shadow-inner">
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
                                
                                {legalOutput.notice_draft && (
                                    <button
                                        onClick={sendToGenerator}
                                        className="w-full mt-6 flex items-center justify-center gap-2 bg-primary text-white py-3 rounded-lg text-xs font-bold hover:opacity-90 transition shadow-lg shadow-primary/20"
                                    >
                                        <FileText size={16} />
                                        Sync with Document Generator
                                    </button>
                                )}
                            </div>
                        </div>
                    </motion.div>
                )}
            </div>

            <div className="p-8 bg-surface border-t border-outline-variant/10">
                <div className="max-w-4xl mx-auto relative">
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
                        className="w-full bg-surface-container-low border-2 border-transparent rounded-2xl p-6 pr-16 text-on-surface placeholder:text-on-surface-variant focus:ring-4 focus:ring-primary/10 focus:border-primary/20 transition-all resize-none h-28 shadow-inner disabled:opacity-70"
                    />
                    <button
                        onClick={handleSend}
                        disabled={isLoading || !input.trim()}
                        className="absolute right-5 bottom-5 p-4 bg-primary text-white rounded-xl hover:scale-105 active:scale-95 disabled:opacity-50 transition-all shadow-xl shadow-primary/30"
                    >
                        <Send size={22} />
                    </button>
                </div>
            </div>
        </div>
    );
};
