import React, { useEffect, useRef, useState } from 'react';
import {
  Check,
  Copy,
  MessageSquare,
  RotateCcw,
  Send,
  Share2,
  ThumbsDown,
  ThumbsUp,
  UserPlus,
  X,
} from 'lucide-react';
import type {
  ChatMessage,
  ConversationThread,
  KnowledgeDoc,
  TenantClient,
} from '../lib/orbitEngine';
import { orchestrateChatTurn } from '../lib/orbitEngine';

interface WidgetPreviewProps {
  tenant: TenantClient;
  docs: KnowledgeDoc[];
  conversation: ConversationThread;
  onUpdateConversation: (updated: ConversationThread) => void;
  onResetConversation: () => void;
  onFeedback: (messageId: string, rating: 'like' | 'dislike') => void;
  onCreateLead: (lead: {
    name: string;
    email: string;
    phone: string;
    requirement: string;
    message: string;
    conversationId: string;
  }) => { created: boolean };
}

export const WidgetPreview: React.FC<WidgetPreviewProps> = ({
  tenant,
  docs,
  conversation,
  onUpdateConversation,
  onResetConversation,
  onFeedback,
  onCreateLead,
}) => {
  const [inputValue, setInputValue] = useState('');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [sharedId, setSharedId] = useState<string | null>(null);
  const [showLeadForm, setShowLeadForm] = useState(false);
  const [leadSubmitted, setLeadSubmitted] = useState(false);
  const [leadName, setLeadName] = useState('');
  const [leadEmail, setLeadEmail] = useState('');
  const [leadPhone, setLeadPhone] = useState('');
  const [leadReq, setLeadReq] = useState('');
  const [leadError, setLeadError] = useState('');
  const messagesContainerRef = useRef<HTMLDivElement | null>(null);

  const cfg = tenant.widgetConfig;
  const isLight = cfg.theme === 'light';

  useEffect(() => {
    const el = messagesContainerRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [conversation.id, conversation.messages.length, showLeadForm]);

  const sendMessage = (rawText: string) => {
    const clean = rawText.trim();
    if (!clean) return;

    const userMsg: ChatMessage = {
      id: `msg_u_${Date.now()}`,
      conversationId: conversation.id,
      clientId: tenant.id,
      role: 'user',
      content: clean,
      intent: 'business_query',
      language: conversation.preferredLanguage || tenant.language,
      evidenceState: 'SUPPORTED',
      sources: [],
      latencyMs: 0,
      createdAt: new Date().toISOString(),
    };

    const result = orchestrateChatTurn(tenant, docs, conversation, clean);
    const assistantMsg: ChatMessage = {
      id: `msg_a_${Date.now() + 1}`,
      conversationId: conversation.id,
      clientId: tenant.id,
      role: 'assistant',
      content: result.answer,
      intent: result.intent,
      language: result.language,
      evidenceState: result.evidenceState,
      sources: result.sources,
      latencyMs: 14,
      createdAt: new Date().toISOString(),
    };

    const nextMessages = [...conversation.messages, userMsg, assistantMsg];
    const userTurns = nextMessages.filter((m) => m.role === 'user').map((m) => m.content);
    onUpdateConversation({
      ...conversation,
      preferredLanguage:
        result.preferredLanguage !== null ? result.preferredLanguage : conversation.preferredLanguage,
      summary: userTurns.slice(-6).join(' | '),
      messages: nextMessages,
      updatedAt: new Date().toISOString(),
    });

    if (result.evidenceState === 'UNKNOWN' && tenant.leadCaptureEnabled && !leadSubmitted) {
      setShowLeadForm(true);
    }
    setInputValue('');
  };

  const handleCopy = async (id: string, text: string) => {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
      }
    } catch {
      // Fallback handled silently
    }
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1500);
  };

  const handleShare = async (id: string, text: string) => {
    try {
      if (navigator.share) {
        await navigator.share({
          title: `${tenant.assistantName} Response`,
          text,
        });
      } else if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
      }
    } catch {
      // User cancelled or clipboard fallback
    }
    setSharedId(id);
    setTimeout(() => setSharedId(null), 1500);
  };

  const handleLeadSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setLeadError('');
    if (!leadName.trim()) {
      setLeadError('Name is required.');
      return;
    }
    if (!leadEmail.trim() && !leadPhone.trim()) {
      setLeadError('Provide an email or phone number.');
      return;
    }
    onCreateLead({
      name: leadName.trim(),
      email: leadEmail.trim(),
      phone: leadPhone.trim(),
      requirement: leadReq.trim() || 'Widget Support Inquiry',
      message: `Submitted from widget session ${conversation.sessionId}`,
      conversationId: conversation.id,
    });
    setLeadSubmitted(true);
    setShowLeadForm(false);
  };

  return (
    <div
      className={`flex flex-col border overflow-hidden transition-colors ${
        isLight
          ? 'bg-white text-slate-900 border-slate-200'
          : 'bg-slate-900 text-slate-100 border-slate-800'
      }`}
      style={{
        borderRadius: `${cfg.radius}px`,
        minHeight: '540px',
        maxHeight: '640px',
      }}
      data-testid="live-widget-container"
    >
      {/* Header */}
      <div
        className="px-4 py-3 text-white flex items-center justify-between gap-2 shrink-0"
        style={{ backgroundColor: cfg.primaryColor }}
      >
        <div className="min-w-0">
          <div className="font-semibold text-sm truncate">{tenant.assistantName}</div>
          <div className="text-xs opacity-90 truncate">
            {tenant.companyName} ({conversation.preferredLanguage || tenant.language})
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {tenant.leadCaptureEnabled && !leadSubmitted && (
            <button
              type="button"
              onClick={() => setShowLeadForm((v) => !v)}
              className="px-2 py-1 text-xs font-medium rounded bg-white/15 hover:bg-white/25 transition-colors flex items-center gap-1 whitespace-nowrap"
              aria-label="Open lead capture form"
            >
              <UserPlus className="w-3.5 h-3.5" />
              <span>Contact</span>
            </button>
          )}
          <button
            type="button"
            onClick={() => {
              setLeadSubmitted(false);
              setShowLeadForm(false);
              onResetConversation();
            }}
            className="px-2 py-1 text-xs font-medium rounded bg-white/15 hover:bg-white/25 transition-colors flex items-center gap-1 whitespace-nowrap"
            aria-label="Start new conversation"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Reset</span>
          </button>
        </div>
      </div>

      {/* Messages */}
      <div ref={messagesContainerRef} className="flex-1 overflow-y-auto p-4 space-y-3.5">
        {/* Welcome message */}
        <div className="flex flex-col items-start max-w-[90%]">
          <div
            className={`px-3.5 py-2.5 rounded-xl text-sm leading-relaxed ${
              isLight ? 'bg-slate-100 text-slate-900' : 'bg-slate-800 text-slate-100'
            }`}
          >
            {tenant.welcomeMessage}
          </div>
        </div>

        {conversation.messages.map((msg) => {
          const isUser = msg.role === 'user';
          return (
            <div
              key={msg.id}
              className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}
            >
              <div
                className={`max-w-[90%] px-3.5 py-2.5 rounded-xl text-sm leading-relaxed ${
                  isUser
                    ? 'text-white'
                    : isLight
                    ? 'bg-slate-100 text-slate-900'
                    : 'bg-slate-800 text-slate-100'
                }`}
                style={isUser ? { backgroundColor: cfg.primaryColor } : undefined}
              >
                <div>{msg.content}</div>
                {!isUser && msg.sources.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-slate-500/20 text-xs opacity-75">
                    Source: {msg.sources.map((s) => `${s.filename} (v${s.version})`).join(' · ')}
                  </div>
                )}
              </div>

              {/* Metadata + Assistant Action Controls (Like / Dislike / Copy / Share) */}
              {!isUser && (
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs">
                  <span className={isLight ? 'text-slate-500' : 'text-slate-400'}>
                    Intent: {msg.intent} · Evidence: {msg.evidenceState} · {msg.language}
                  </span>
                  <span className={isLight ? 'text-slate-300' : 'text-slate-700'}>·</span>
                  <button
                    type="button"
                    onClick={() => onFeedback(msg.id, 'like')}
                    aria-label="Like assistant message"
                    className={`px-2 py-1 rounded border text-xs flex items-center gap-1 transition-colors ${
                      msg.feedback === 'like'
                        ? 'border-emerald-500 bg-emerald-500/15 text-emerald-400 font-medium'
                        : isLight
                        ? 'border-slate-200 text-slate-600 hover:bg-slate-100'
                        : 'border-slate-700 text-slate-300 hover:bg-slate-800'
                    }`}
                  >
                    <ThumbsUp className="w-3 h-3" />
                    <span>Like</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => onFeedback(msg.id, 'dislike')}
                    aria-label="Dislike assistant message"
                    className={`px-2 py-1 rounded border text-xs flex items-center gap-1 transition-colors ${
                      msg.feedback === 'dislike'
                        ? 'border-amber-500 bg-amber-500/15 text-amber-400 font-medium'
                        : isLight
                        ? 'border-slate-200 text-slate-600 hover:bg-slate-100'
                        : 'border-slate-700 text-slate-300 hover:bg-slate-800'
                    }`}
                  >
                    <ThumbsDown className="w-3 h-3" />
                    <span>Dislike</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleCopy(msg.id, msg.content)}
                    aria-label="Copy assistant message"
                    className={`px-2 py-1 rounded border text-xs flex items-center gap-1 transition-colors ${
                      isLight
                        ? 'border-slate-200 text-slate-600 hover:bg-slate-100'
                        : 'border-slate-700 text-slate-300 hover:bg-slate-800'
                    }`}
                  >
                    {copiedId === msg.id ? (
                      <>
                        <Check className="w-3 h-3 text-emerald-400" />
                        <span>Copied</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3 h-3" />
                        <span>Copy</span>
                      </>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleShare(msg.id, msg.content)}
                    aria-label="Share assistant message"
                    className={`px-2 py-1 rounded border text-xs flex items-center gap-1 transition-colors ${
                      isLight
                        ? 'border-slate-200 text-slate-600 hover:bg-slate-100'
                        : 'border-slate-700 text-slate-300 hover:bg-slate-800'
                    }`}
                  >
                    <Share2 className="w-3 h-3" />
                    <span>{sharedId === msg.id ? 'Shared' : 'Share'}</span>
                  </button>
                </div>
              )}
            </div>
          );
        })}

        {leadSubmitted && (
          <div className="p-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 text-xs text-emerald-300">
            Thank you! Your contact details have been saved and queued in the tenant notification outbox.
          </div>
        )}
      </div>

      {/* Lead Capture Form Drawer */}
      {showLeadForm && !leadSubmitted && (
        <form
          onSubmit={handleLeadSubmit}
          className={`p-3.5 border-t space-y-2.5 ${
            isLight ? 'bg-slate-50 border-slate-200' : 'bg-slate-950/90 border-slate-800'
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold">Leave your contact details</span>
            <button
              type="button"
              onClick={() => setShowLeadForm(false)}
              aria-label="Close lead form"
              className="p-1 opacity-70 hover:opacity-100"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          {leadError && <div className="text-xs text-rose-400">{leadError}</div>}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <input
              type="text"
              placeholder="Your name *"
              aria-label="Lead Name"
              value={leadName}
              onChange={(e) => setLeadName(e.target.value)}
              className={`px-2.5 py-1.5 text-xs rounded border ${
                isLight
                  ? 'bg-white border-slate-300 text-slate-900'
                  : 'bg-slate-900 border-slate-700 text-slate-100'
              }`}
            />
            <input
              type="email"
              placeholder="Email address"
              aria-label="Lead Email"
              value={leadEmail}
              onChange={(e) => setLeadEmail(e.target.value)}
              className={`px-2.5 py-1.5 text-xs rounded border ${
                isLight
                  ? 'bg-white border-slate-300 text-slate-900'
                  : 'bg-slate-900 border-slate-700 text-slate-100'
              }`}
            />
            <input
              type="tel"
              placeholder="Phone number"
              aria-label="Lead Phone"
              value={leadPhone}
              onChange={(e) => setLeadPhone(e.target.value)}
              className={`px-2.5 py-1.5 text-xs rounded border ${
                isLight
                  ? 'bg-white border-slate-300 text-slate-900'
                  : 'bg-slate-900 border-slate-700 text-slate-100'
              }`}
            />
            <input
              type="text"
              placeholder="Requirement / topic"
              aria-label="Lead Requirement"
              value={leadReq}
              onChange={(e) => setLeadReq(e.target.value)}
              className={`px-2.5 py-1.5 text-xs rounded border ${
                isLight
                  ? 'bg-white border-slate-300 text-slate-900'
                  : 'bg-slate-900 border-slate-700 text-slate-100'
              }`}
            />
          </div>
          <button
            type="submit"
            className="w-full py-1.5 px-3 rounded text-xs font-semibold text-white transition-opacity hover:opacity-95"
            style={{ backgroundColor: cfg.primaryColor }}
          >
            Submit Contact Request
          </button>
        </form>
      )}

      {/* Suggested quick prompts */}
      <div
        className={`px-3.5 py-2 border-t flex flex-wrap items-center gap-1.5 shrink-0 ${
          isLight ? 'border-slate-200 bg-slate-50' : 'border-slate-800 bg-slate-950/50'
        }`}
      >
        {cfg.suggestedQuestions.map((q) => (
          <button
            key={q}
            type="button"
            onClick={() => sendMessage(q)}
            className={`px-2 py-1 rounded text-xs whitespace-nowrap shrink-0 border transition-colors ${
              isLight
                ? 'border-slate-300 bg-white text-slate-700 hover:bg-slate-100'
                : 'border-slate-700 bg-slate-900 text-slate-300 hover:bg-slate-800'
            }`}
          >
            {q}
          </button>
        ))}
      </div>

      {/* Input Composer */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          sendMessage(inputValue);
        }}
        className={`p-3 border-t flex items-center gap-2 shrink-0 ${
          isLight ? 'border-slate-200 bg-white' : 'border-slate-800 bg-slate-900'
        }`}
      >
        <input
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          placeholder={cfg.inputPlaceholder}
          aria-label="Chat message input"
          className={`flex-1 px-3 py-2 text-sm rounded-lg border focus:outline-none ${
            isLight
              ? 'bg-slate-50 border-slate-300 text-slate-900'
              : 'bg-slate-950 border-slate-700 text-slate-100'
          }`}
        />
        <button
          type="submit"
          aria-label="Send chat message"
          className="px-3.5 py-2 rounded-lg text-white text-sm font-medium flex items-center gap-1.5 shrink-0 transition-opacity hover:opacity-95"
          style={{ backgroundColor: cfg.primaryColor }}
        >
          <Send className="w-4 h-4" />
          <span>Send</span>
        </button>
      </form>

      {cfg.showBranding && (
        <div
          className={`py-1.5 px-3 text-center text-[11px] border-t ${
            isLight
              ? 'border-slate-100 text-slate-400 bg-slate-50'
              : 'border-slate-800/80 text-slate-400 bg-slate-950'
          }`}
        >
          <MessageSquare className="w-3 h-3 inline mr-1" />
          Secured by Orbit AI Grounded RAG
        </div>
      )}
    </div>
  );
};
