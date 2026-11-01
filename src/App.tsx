import React, { useMemo, useState } from 'react';
import {
  Activity,
  BookOpen,
  Building2,
  Check,
  Code2,
  Copy,
  Download,
  FileText,
  KeyRound,
  LayoutDashboard,
  MessageSquare,
  Moon,
  Plus,
  RefreshCw,
  Search,
  Settings,
  Sliders,
  Sun,
  Trash2,
  Upload,
  Users,
} from 'lucide-react';
import type {
  ConversationThread,
  KnowledgeDoc,
  LeadItem,
  TenantClient,
} from './lib/orbitEngine';
import { chunk_text_browser } from './lib/chunkHelper';
import {
  INITIAL_CONVERSATIONS,
  INITIAL_DOCS,
  INITIAL_LEADS,
  INITIAL_TENANTS,
} from './lib/seedData';
import { WidgetPreview } from './components/WidgetPreview';
import { SqlAndRepoView } from './components/SqlAndRepoView';

type AdminTab =
  | 'overview'
  | 'tenants'
  | 'knowledge'
  | 'conversations'
  | 'leads'
  | 'prompts'
  | 'widget'
  | 'sql';

export function App() {
  const [darkMode, setDarkMode] = useState(true);
  const [activeTab, setActiveTab] = useState<AdminTab>('overview');

  const [tenants, setTenants] = useState<TenantClient[]>(INITIAL_TENANTS);
  const [selectedTenantId, setSelectedTenantId] = useState<string>(INITIAL_TENANTS[0].id);
  const [docs, setDocs] = useState<KnowledgeDoc[]>(INITIAL_DOCS);
  const [conversations, setConversations] = useState<ConversationThread[]>(INITIAL_CONVERSATIONS);
  const [leads, setLeads] = useState<LeadItem[]>(INITIAL_LEADS);

  // Tenant creation / key rotation notice
  const [newTenantName, setNewTenantName] = useState('');
  const [newTenantSlug, setNewTenantSlug] = useState('');
  const [newTenantAssistant, setNewTenantAssistant] = useState('');
  const [newTenantDomain, setNewTenantDomain] = useState('');
  const [generatedKeyBanner, setGeneratedKeyBanner] = useState<string | null>(null);
  const [domainInput, setDomainInput] = useState('');

  // Knowledge upload state
  const [docFilename, setDocFilename] = useState('');
  const [docContent, setDocContent] = useState('');
  const [uploadNotice, setUploadNotice] = useState('');

  // Prompt editor state
  const [promptDraft, setPromptDraft] = useState('');
  const [fallbackDraft, setFallbackDraft] = useState('');
  const [promptNote, setPromptNote] = useState('');

  // Lead filter state
  const [leadStatusFilter, setLeadStatusFilter] = useState<string>('all');
  const [leadSearch, setLeadSearch] = useState<string>('');
  const [copiedEmbed, setCopiedEmbed] = useState(false);

  const selectedTenant = useMemo(
    () => tenants.find((t) => t.id === selectedTenantId) || tenants[0],
    [tenants, selectedTenantId]
  );

  const tenantDocs = useMemo(
    () => docs.filter((d) => d.clientId === selectedTenant.id),
    [docs, selectedTenant.id]
  );

  const activeConversation = useMemo(() => {
    const found = conversations.find((c) => c.clientId === selectedTenant.id);
    if (found) return found;
    return {
      id: `conv_${selectedTenant.id}`,
      clientId: selectedTenant.id,
      sessionId: `sess_${selectedTenant.slug}_live`,
      preferredLanguage: null,
      summary: '',
      messages: [],
      updatedAt: new Date().toISOString(),
    };
  }, [conversations, selectedTenant]);

  // Aggregate metrics from persisted state
  const metrics = useMemo(() => {
    const allMsgs = conversations.flatMap((c) => c.messages);
    const likes = allMsgs.filter((m) => m.feedback === 'like').length;
    const dislikes = allMsgs.filter((m) => m.feedback === 'dislike').length;
    const totalChunks = docs
      .filter((d) => d.status === 'ready')
      .reduce((acc, d) => acc + d.chunkCount, 0);
    return {
      totalTenants: tenants.length,
      activeTenants: tenants.filter((t) => t.enabled).length,
      totalConversations: conversations.length,
      totalMessages: allMsgs.length,
      totalLeads: leads.length,
      readyFiles: docs.filter((d) => d.status === 'ready').length,
      totalChunks,
      likes,
      dislikes,
    };
  }, [tenants, conversations, leads, docs]);

  const toggleTheme = () => {
    const next = !darkMode;
    setDarkMode(next);
    document.documentElement.classList.toggle('dark', next);
  };

  const handleSelectTenant = (id: string) => {
    setSelectedTenantId(id);
    const t = tenants.find((item) => item.id === id);
    if (t) {
      setPromptDraft(t.systemPrompt);
      setFallbackDraft(t.fallbackAnswer);
    }
  };

  const handleCreateTenant = (e: React.FormEvent) => {
    e.preventDefault();
    const name = newTenantName.trim();
    if (!name) return;
    const slug = (newTenantSlug.trim() || name.toLowerCase().replace(/[^a-z0-9]+/g, '-')).replace(
      /^-|-$/g,
      ''
    );
    const id = `tenant-${slug}-${Date.now().toString().slice(-4)}`;
    const randomToken = Math.random().toString(36).slice(2, 12) + Math.random().toString(36).slice(2, 12);
    const rawKey = `orb_live_${randomToken}`;
    const assistant = newTenantAssistant.trim() || `${name} AI`;

    const created: TenantClient = {
      id,
      businessName: name,
      slug,
      enabled: true,
      assistantName: assistant,
      companyName: name,
      systemPrompt: `You are ${assistant}, the customer support assistant for ${name}. Answer accurately using verified company documents.`,
      fallbackAnswer: `I do not have enough verified information in ${name}'s knowledge base to answer that accurately. Please leave your contact details.`,
      welcomeMessage: `Hello! I am ${assistant} from ${name}. How can I help you today?`,
      language: 'en',
      temperature: 0.2,
      topK: 5,
      minSimilarity: 0.25,
      leadCaptureEnabled: true,
      notificationEmail: `support@${slug}.example.com`,
      domains: newTenantDomain.trim() ? [newTenantDomain.trim().toLowerCase()] : ['example.com'],
      apiKeyPrefix: rawKey.slice(0, 14),
      apiKeyHash: `sha256_${randomToken}`,
      widgetConfig: {
        primaryColor: '#4f46e5',
        theme: 'dark',
        position: 'bottom-right',
        width: 380,
        height: 580,
        radius: 16,
        inputPlaceholder: 'Ask a question...',
        showBranding: true,
        suggestedQuestions: ['What services do you offer?', 'Hindi mein likho', 'Who are you?'],
      },
      promptVersions: [
        {
          versionNumber: 1,
          systemPrompt: `You are ${assistant}, the customer support assistant for ${name}.`,
          fallbackAnswer: `I do not have enough verified information in ${name}'s knowledge base to answer that accurately.`,
          welcomeMessage: `Hello! I am ${assistant} from ${name}. How can I help you today?`,
          note: 'Initial tenant prompt configuration',
          createdAt: new Date().toISOString(),
        },
      ],
      createdAt: new Date().toISOString(),
    };

    setTenants((prev) => [created, ...prev]);
    setSelectedTenantId(created.id);
    setGeneratedKeyBanner(rawKey);
    setNewTenantName('');
    setNewTenantSlug('');
    setNewTenantAssistant('');
    setNewTenantDomain('');
  };

  const handleRotateApiKey = (tenantId: string) => {
    const token = Math.random().toString(36).slice(2, 12) + Math.random().toString(36).slice(2, 12);
    const rawKey = `orb_live_${token}`;
    setTenants((prev) =>
      prev.map((t) =>
        t.id === tenantId
          ? { ...t, apiKeyPrefix: rawKey.slice(0, 14), apiKeyHash: `sha256_${token}` }
          : t
      )
    );
    setGeneratedKeyBanner(rawKey);
  };

  const handleDuplicateTenant = (tenant: TenantClient) => {
    const copySlug = `${tenant.slug}-copy-${Math.floor(100 + Math.random() * 899)}`;
    const rawKey = `orb_live_${Math.random().toString(36).slice(2, 14)}`;
    const dup: TenantClient = {
      ...tenant,
      id: `tenant-${copySlug}`,
      businessName: `${tenant.businessName} (Copy)`,
      slug: copySlug,
      apiKeyPrefix: rawKey.slice(0, 14),
      createdAt: new Date().toISOString(),
    };
    setTenants((prev) => [dup, ...prev]);
    setSelectedTenantId(dup.id);
    setGeneratedKeyBanner(rawKey);
  };

  const handleToggleTenant = (tenantId: string) => {
    setTenants((prev) =>
      prev.map((t) => (t.id === tenantId ? { ...t, enabled: !t.enabled } : t))
    );
  };

  const handleDeleteTenant = (tenantId: string) => {
    if (tenants.length <= 1) return;
    const remaining = tenants.filter((t) => t.id !== tenantId);
    setTenants(remaining);
    setDocs((prev) => prev.filter((d) => d.clientId !== tenantId));
    setConversations((prev) => prev.filter((c) => c.clientId !== tenantId));
    setLeads((prev) => prev.filter((l) => l.clientId !== tenantId));
    if (selectedTenantId === tenantId) {
      setSelectedTenantId(remaining[0].id);
    }
  };

  const handleIngestDocument = (e: React.FormEvent) => {
    e.preventDefault();
    setUploadNotice('');
    const fname = docFilename.trim();
    const body = docContent.trim();
    if (!fname || !body) {
      setUploadNotice('Provide both a valid filename (.txt, .md, .csv, .docx, .pdf) and document content.');
      return;
    }
    const ext = fname.includes('.') ? fname.split('.').pop()!.toUpperCase() : 'TXT';
    const allowed = ['PDF', 'DOCX', 'CSV', 'MD', 'TXT'];
    if (!allowed.includes(ext)) {
      setUploadNotice(`Unsupported extension .${ext}. Allowed: PDF, DOCX, CSV, MD, TXT.`);
      return;
    }

    const chunks = chunk_text_browser(body, 900, 120);
    const existing = docs.find((d) => d.clientId === selectedTenant.id && d.filename === fname);

    if (existing) {
      const nextVersion = existing.activeVersion + 1;
      setDocs((prev) =>
        prev.map((d) =>
          d.id === existing.id
            ? {
                ...d,
                activeVersion: nextVersion,
                chunkCount: chunks.length,
                chunks,
                fileSize: new Blob([body]).size,
                status: 'ready',
                updatedAt: new Date().toISOString(),
              }
            : d
        )
      );
      setUploadNotice(`Activated staged index version v${nextVersion} for ${fname} (${chunks.length} chunks).`);
    } else {
      const docId = `doc-${Date.now()}`;
      const newDoc: KnowledgeDoc = {
        id: docId,
        clientId: selectedTenant.id,
        filename: fname,
        safeFilename: fname.replace(/[^a-zA-Z0-9._-]/g, '_'),
        storagePath: `${selectedTenant.id}/${docId}/${fname.replace(/[^a-zA-Z0-9._-]/g, '_')}`,
        format: ext as KnowledgeDoc['format'],
        fileSize: new Blob([body]).size,
        status: 'ready',
        activeVersion: 1,
        chunkCount: chunks.length,
        chunks,
        updatedAt: new Date().toISOString(),
      };
      setDocs((prev) => [newDoc, ...prev]);
      setUploadNotice(`Ingested ${fname} into private bucket knowledge/${newDoc.storagePath} (${chunks.length} chunks).`);
    }
    setDocFilename('');
    setDocContent('');
  };

  const handleRebuildDoc = (docId: string) => {
    setDocs((prev) =>
      prev.map((d) =>
        d.id === docId
          ? { ...d, activeVersion: d.activeVersion + 1, updatedAt: new Date().toISOString() }
          : d
      )
    );
  };

  const handleUpdateConversation = (updated: ConversationThread) => {
    setConversations((prev) => {
      const exists = prev.some((c) => c.id === updated.id);
      if (exists) {
        return prev.map((c) => (c.id === updated.id ? updated : c));
      }
      return [updated, ...prev];
    });
  };

  const handleResetConversation = () => {
    const fresh: ConversationThread = {
      id: `conv_${selectedTenant.id}_${Date.now()}`,
      clientId: selectedTenant.id,
      sessionId: `sess_${Math.random().toString(36).slice(2, 9)}`,
      preferredLanguage: null,
      summary: '',
      messages: [],
      updatedAt: new Date().toISOString(),
    };
    setConversations((prev) => [fresh, ...prev.filter((c) => c.clientId !== selectedTenant.id)]);
  };

  const handleMessageFeedback = (messageId: string, rating: 'like' | 'dislike') => {
    setConversations((prev) =>
      prev.map((c) =>
        c.clientId === selectedTenant.id
          ? {
              ...c,
              messages: c.messages.map((m) =>
                m.id === messageId ? { ...m, feedback: rating } : m
              ),
            }
          : c
      )
    );
  };

  const handleCreateLead = (payload: {
    name: string;
    email: string;
    phone: string;
    requirement: string;
    message: string;
    conversationId: string;
  }) => {
    const idemKey = `${selectedTenant.id}|${payload.email.toLowerCase()}|${payload.phone}|${payload.requirement.toLowerCase()}`;
    const existing = leads.find(
      (l) => l.clientId === selectedTenant.id && l.idempotencyKey === idemKey
    );
    if (existing) {
      return { created: false };
    }
    const item: LeadItem = {
      id: `lead-${Date.now()}`,
      clientId: selectedTenant.id,
      conversationId: payload.conversationId,
      idempotencyKey: idemKey,
      name: payload.name,
      email: payload.email,
      phone: payload.phone,
      requirement: payload.requirement,
      message: payload.message,
      status: 'new',
      assignee: selectedTenant.notificationEmail,
      notes: 'Captured via embedded widget; notification stored in outbox.',
      notificationStatus: 'sent',
      createdAt: new Date().toISOString(),
    };
    setLeads((prev) => [item, ...prev]);
    return { created: true };
  };

  const handleExportLeadsCsv = () => {
    const rows = [
      ['id', 'client_id', 'name', 'email', 'phone', 'requirement', 'status', 'assignee', 'created_at'],
      ...leads.map((l) => [
        l.id,
        l.clientId,
        l.name,
        l.email,
        l.phone,
        l.requirement,
        l.status,
        l.assignee,
        l.createdAt,
      ]),
    ];
    const csvContent = rows
      .map((r) => r.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(','))
      .join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `orbit_leads_${selectedTenant.slug}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const embedScriptTag = `<script
  src="https://orbit-ai.onrender.com/static/js/widget.js"
  data-client-id="${selectedTenant.id}"
  data-api-key="${selectedTenant.apiKeyPrefix}..."
  defer>
</script>`;

  const filteredLeads = useMemo(() => {
    return leads.filter((l) => {
      if (leadStatusFilter !== 'all' && l.status !== leadStatusFilter) return false;
      if (leadSearch.trim()) {
        const q = leadSearch.toLowerCase();
        return (
          l.name.toLowerCase().includes(q) ||
          l.email.toLowerCase().includes(q) ||
          l.requirement.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [leads, leadStatusFilter, leadSearch]);

  return (
    <div className={darkMode ? 'dark' : ''}>
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 flex flex-col">
        {/* Top Bar Contract: Zone 1 Brand Wordmark | Zone 2 Nav Links | Zone 3 Primary Action */}
        <header className="flex items-center justify-between gap-8 px-6 py-3.5 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shrink-0">
          <a
            href="#overview"
            onClick={(e) => {
              e.preventDefault();
              setActiveTab('overview');
            }}
            className="text-lg font-bold tracking-tight text-slate-900 dark:text-slate-100 whitespace-nowrap shrink-0"
          >
            Orbit AI
          </a>

          <nav
            aria-label="Primary sections"
            className="hidden md:flex items-center gap-6 text-sm font-medium text-slate-600 dark:text-slate-300"
          >
            <button
              type="button"
              onClick={() => setActiveTab('overview')}
              className={`hover:text-slate-900 dark:hover:text-white transition-colors whitespace-nowrap shrink-0 ${
                activeTab === 'overview' ? 'text-indigo-600 dark:text-indigo-400 font-semibold' : ''
              }`}
            >
              Overview
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('tenants')}
              className={`hover:text-slate-900 dark:hover:text-white transition-colors whitespace-nowrap shrink-0 ${
                activeTab === 'tenants' ? 'text-indigo-600 dark:text-indigo-400 font-semibold' : ''
              }`}
            >
              Tenants
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('knowledge')}
              className={`hover:text-slate-900 dark:hover:text-white transition-colors whitespace-nowrap shrink-0 ${
                activeTab === 'knowledge' ? 'text-indigo-600 dark:text-indigo-400 font-semibold' : ''
              }`}
            >
              Knowledge Base
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('widget')}
              className={`hover:text-slate-900 dark:hover:text-white transition-colors whitespace-nowrap shrink-0 ${
                activeTab === 'widget' ? 'text-indigo-600 dark:text-indigo-400 font-semibold' : ''
              }`}
            >
              Widget Studio
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('sql')}
              className={`hover:text-slate-900 dark:hover:text-white transition-colors whitespace-nowrap shrink-0 ${
                activeTab === 'sql' ? 'text-indigo-600 dark:text-indigo-400 font-semibold' : ''
              }`}
            >
              SQL & Tests
            </button>
          </nav>

          <div className="flex items-center gap-2.5 shrink-0">
            <a
              href="/orbit-ai-final.zip"
              download="orbit-ai-final.zip"
              className="px-3.5 py-2 text-xs font-semibold text-slate-700 dark:text-slate-200 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700 rounded-lg transition-colors flex items-center gap-1.5 whitespace-nowrap shrink-0"
              title="Download complete project ZIP archive"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download ZIP</span>
            </a>
            <button
              type="button"
              onClick={() => setActiveTab('widget')}
              className="px-3.5 py-2 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 rounded-lg transition-colors whitespace-nowrap shrink-0"
            >
              Test Live Widget
            </button>
          </div>
        </header>

        {/* Main Workspace Canvas: Sidebar + Content Viewport + Live Multilingual Widget Dock */}
        <div className="flex-1 flex flex-col lg:flex-row">
          {/* Sidebar Navigation (260px on desktop, compact bar on mobile) */}
          <aside className="w-full lg:w-64 border-b lg:border-b-0 lg:border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 p-3.5 lg:p-4 flex flex-col justify-between gap-3 lg:gap-6 shrink-0">
            <div className="space-y-3 lg:space-y-5">
              {/* Active Tenant Selector */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label
                    htmlFor="active-tenant-select"
                    className="block text-xs font-medium text-slate-500 dark:text-slate-400"
                  >
                    Active Tenant Scope
                  </label>
                  <span className="text-[11px] text-slate-500 dark:text-slate-400 lg:hidden font-mono">
                    {selectedTenant.apiKeyPrefix}...
                  </span>
                </div>
                <select
                  id="active-tenant-select"
                  value={selectedTenant.id}
                  onChange={(e) => handleSelectTenant(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-slate-100"
                >
                  {tenants.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.businessName} ({t.slug})
                    </option>
                  ))}
                </select>
                <div className="hidden lg:block mt-1.5 text-xs text-slate-500 dark:text-slate-400">
                  Key: <span className="font-mono">{selectedTenant.apiKeyPrefix}...</span> ·{' '}
                  {selectedTenant.enabled ? 'Active' : 'Disabled'}
                </div>
              </div>

              {/* Workspace Views */}
              <div className="flex lg:flex-col gap-1.5 lg:gap-1 overflow-x-auto pb-1 lg:pb-0">
                {(
                  [
                    { id: 'overview', label: 'Dashboard Overview', icon: LayoutDashboard },
                    { id: 'tenants', label: 'Tenants & API Keys', icon: Building2 },
                    { id: 'knowledge', label: 'Knowledge & RAG Index', icon: BookOpen },
                    { id: 'conversations', label: 'Conversations & Feedback', icon: MessageSquare },
                    { id: 'leads', label: 'Leads & Outbox', icon: Users },
                    { id: 'prompts', label: 'Prompt Versioning', icon: FileText },
                    { id: 'widget', label: 'Widget Theme & Embed', icon: Sliders },
                    { id: 'sql', label: 'SQL & 87 Python Tests', icon: Code2 },
                  ] as const
                ).map((item) => {
                  const Icon = item.icon;
                  const active = activeTab === item.id;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setActiveTab(item.id)}
                      className={`shrink-0 lg:w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs lg:text-sm font-medium transition-colors whitespace-nowrap ${
                        active
                          ? 'bg-indigo-600/10 text-indigo-600 dark:bg-indigo-500/15 dark:text-indigo-300'
                          : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800/70'
                      }`}
                    >
                      <Icon className="w-4 h-4 shrink-0" />
                      <span>{item.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Theme toggle & runtime summary in sidebar footer */}
            <div className="hidden lg:flex pt-4 border-t border-slate-200 dark:border-slate-800 items-center justify-between text-xs text-slate-500 dark:text-slate-400">
              <span>Python 3.12 · vector(128)</span>
              <button
                type="button"
                onClick={toggleTheme}
                aria-label="Toggle color theme"
                className="p-2 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              >
                {darkMode ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
              </button>
            </div>
          </aside>

          {/* Center Main Viewport */}
          <main className="flex-1 p-6 overflow-y-auto space-y-6">
            {generatedKeyBanner && (
              <div className="p-4 rounded-xl border border-amber-500/40 bg-amber-500/10 flex flex-wrap items-center justify-between gap-4">
                <div>
                  <div className="text-sm font-semibold text-amber-600 dark:text-amber-300">
                    New Tenant API Key Generated (Displayed Once)
                  </div>
                  <div className="text-xs text-slate-600 dark:text-slate-300 mt-0.5">
                    Copy this raw key now. Only its SHA-256 hash is stored in the database:{' '}
                    <code className="font-mono font-semibold select-all px-1.5 py-0.5 rounded bg-slate-900 text-amber-300">
                      {generatedKeyBanner}
                    </code>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setGeneratedKeyBanner(null)}
                  className="px-3 py-1.5 text-xs font-medium rounded-lg border border-amber-500/40 hover:bg-amber-500/20"
                >
                  Dismiss
                </button>
              </div>
            )}

            {/* TAB 1: OVERVIEW */}
            {activeTab === 'overview' && (
              <div className="space-y-6">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">
                      Multi-Tenant SaaS Control Panel
                    </h1>
                    <p className="text-sm text-slate-600 dark:text-slate-400">
                      Tenant-isolated conversational AI, 128-dim pgvector hybrid RAG, persistent memory, and lead workflow.
                    </p>
                  </div>
                </div>

                {/* KPI Strip with tabular-nums */}
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                  <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
                    <div className="text-xs text-slate-500 dark:text-slate-400">Active Tenants</div>
                    <div className="mt-1 text-2xl font-bold tabular-nums">
                      {metrics.activeTenants} / {metrics.totalTenants}
                    </div>
                    <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                      Isolated credentials & domains
                    </div>
                  </div>

                  <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
                    <div className="text-xs text-slate-500 dark:text-slate-400">Indexed Knowledge</div>
                    <div className="mt-1 text-2xl font-bold tabular-nums">
                      {metrics.readyFiles} files · {metrics.totalChunks} chunks
                    </div>
                    <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                      128-dim staged pgvector index
                    </div>
                  </div>

                  <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
                    <div className="text-xs text-slate-500 dark:text-slate-400">Conversations & Feedback</div>
                    <div className="mt-1 text-2xl font-bold tabular-nums">
                      {metrics.totalMessages} msgs
                    </div>
                    <div className="mt-1 text-xs text-slate-500 dark:text-slate-400 tabular-nums">
                      {metrics.likes} Likes · {metrics.dislikes} Dislikes
                    </div>
                  </div>

                  <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
                    <div className="text-xs text-slate-500 dark:text-slate-400">Captured Leads</div>
                    <div className="mt-1 text-2xl font-bold tabular-nums">{metrics.totalLeads}</div>
                    <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                      Idempotent outbox persistence
                    </div>
                  </div>
                </div>

                {/* Provider Diagnostics Table */}
                <div className="border border-slate-200 dark:border-slate-800 rounded-xl bg-white dark:bg-slate-900 overflow-hidden">
                  <div className="px-5 py-3.5 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
                    <h2 className="text-sm font-semibold">Provider Readiness & Contract Diagnostics</h2>
                    <span className="text-xs text-slate-500 dark:text-slate-400">
                      GET /ready · HTTP 200
                    </span>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <thead className="text-xs text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/40">
                        <tr>
                          <th className="py-2.5 px-4 font-medium">Subsystem</th>
                          <th className="py-2.5 px-4 font-medium">Adapter</th>
                          <th className="py-2.5 px-4 font-medium">Contract / Details</th>
                          <th className="py-2.5 px-4 font-medium text-right">State</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-200 dark:divide-slate-800 text-xs">
                        <tr>
                          <td className="py-3 px-4 font-medium">Origin & CORS Policy</td>
                          <td className="py-3 px-4 font-mono">ALLOWED_ORIGINS · CORS_ORIGINS</td>
                          <td className="py-3 px-4 text-slate-600 dark:text-slate-400">
                            Only required env vars; all external API keys are optional
                          </td>
                          <td className="py-3 px-4 text-right font-medium text-emerald-600 dark:text-emerald-400">
                            Active
                          </td>
                        </tr>
                        <tr>
                          <td className="py-3 px-4 font-medium">Database & Storage</td>
                          <td className="py-3 px-4 font-mono">SQLite / Local (Supabase Optional)</td>
                          <td className="py-3 px-4 text-slate-600 dark:text-slate-400">
                            15 tables · auto-fallback to SQLite & local storage when Supabase keys omitted
                          </td>
                          <td className="py-3 px-4 text-right font-medium text-emerald-600 dark:text-emerald-400">
                            Verified
                          </td>
                        </tr>
                        <tr>
                          <td className="py-3 px-4 font-medium">Vector & Embeddings</td>
                          <td className="py-3 px-4 font-mono">Local 128-Dim (pgvector Optional)</td>
                          <td className="py-3 px-4 text-slate-600 dark:text-slate-400 tabular-nums">
                            vector(128) · RRF + Lexical + Reranking + Evidence Check (Zero-Key Ready)
                          </td>
                          <td className="py-3 px-4 text-right font-medium text-emerald-600 dark:text-emerald-400">
                            128-Dim Matched
                          </td>
                        </tr>
                        <tr>
                          <td className="py-3 px-4 font-medium">Conversational LLM</td>
                          <td className="py-3 px-4 font-mono">Local Built-In (OpenAI Optional)</td>
                          <td className="py-3 px-4 text-slate-600 dark:text-slate-400">
                            Dynamic Multilingual (EN, हिंदी, Hinglish, ES, FR) + Auto-Fallback
                          </td>
                          <td className="py-3 px-4 text-right font-medium text-emerald-600 dark:text-emerald-400">
                            Ready
                          </td>
                        </tr>
                        <tr>
                          <td className="py-3 px-4 font-medium">Optional Integrations</td>
                          <td className="py-3 px-4 font-mono">Supabase · LLM · Qdrant · SMTP · TTS</td>
                          <td className="py-3 px-4 text-slate-600 dark:text-slate-400">
                            100% optional; never causes errors or blocks deployment when unconfigured
                          </td>
                          <td className="py-3 px-4 text-right font-medium text-slate-500">
                            Optional (Safe)
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}

            {/* TAB 2: TENANTS & API KEYS */}
            {activeTab === 'tenants' && (
              <div className="space-y-6">
                <div className="border border-slate-200 dark:border-slate-800 rounded-xl bg-white dark:bg-slate-900 p-5">
                  <h2 className="text-base font-semibold mb-3">Create New Tenant</h2>
                  <form onSubmit={handleCreateTenant} className="grid grid-cols-1 md:grid-cols-4 gap-3">
                    <input
                      type="text"
                      placeholder="Business name (e.g. Urban Dental)"
                      aria-label="New tenant business name"
                      value={newTenantName}
                      onChange={(e) => setNewTenantName(e.target.value)}
                      required
                      className="px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-950"
                    />
                    <input
                      type="text"
                      placeholder="Slug (e.g. urban-dental)"
                      aria-label="New tenant slug"
                      value={newTenantSlug}
                      onChange={(e) => setNewTenantSlug(e.target.value)}
                      className="px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-950"
                    />
                    <input
                      type="text"
                      placeholder="Assistant name (e.g. Dental Care AI)"
                      aria-label="New tenant assistant name"
                      value={newTenantAssistant}
                      onChange={(e) => setNewTenantAssistant(e.target.value)}
                      className="px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-950"
                    />
                    <div className="flex gap-2">
                      <input
                        type="text"
                        placeholder="Allowed domain (example.com)"
                        aria-label="New tenant domain"
                        value={newTenantDomain}
                        onChange={(e) => setNewTenantDomain(e.target.value)}
                        className="flex-1 px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-950"
                      />
                      <button
                        type="submit"
                        className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold flex items-center gap-1.5 whitespace-nowrap shrink-0"
                      >
                        <Plus className="w-4 h-4" />
                        <span>Create Tenant</span>
                      </button>
                    </div>
                  </form>
                </div>

                {/* Tenant List */}
                <div className="border border-slate-200 dark:border-slate-800 rounded-xl bg-white dark:bg-slate-900 overflow-hidden">
                  <div className="px-5 py-3.5 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
                    <h2 className="text-sm font-semibold">Configured Tenants ({tenants.length})</h2>
                  </div>
                  <div className="divide-y divide-slate-200 dark:divide-slate-800">
                    {tenants.map((t) => (
                      <div
                        key={t.id}
                        className="p-4 flex flex-wrap items-center justify-between gap-4 hover:bg-slate-50/60 dark:hover:bg-slate-800/30"
                      >
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-sm">{t.businessName}</span>
                            <span className="text-xs text-slate-400">·</span>
                            <span className="font-mono text-xs text-slate-500">{t.slug}</span>
                            <span className="text-xs text-slate-400">·</span>
                            <span
                              className={`text-xs font-medium ${
                                t.enabled ? 'text-emerald-500' : 'text-rose-400'
                              }`}
                            >
                              {t.enabled ? 'Enabled' : 'Disabled'}
                            </span>
                          </div>
                          <div className="text-xs text-slate-500 dark:text-slate-400">
                            Assistant: {t.assistantName} · Key Prefix:{' '}
                            <code className="font-mono">{t.apiKeyPrefix}...</code> · Domains:{' '}
                            {t.domains.join(', ')}
                          </div>
                        </div>

                        <div className="flex flex-wrap items-center gap-2">
                          <button
                            type="button"
                            onClick={() => handleSelectTenant(t.id)}
                            className="px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 text-xs font-medium hover:bg-slate-100 dark:hover:bg-slate-800"
                          >
                            Select
                          </button>
                          <button
                            type="button"
                            onClick={() => handleRotateApiKey(t.id)}
                            className="px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 text-xs font-medium flex items-center gap-1 hover:bg-slate-100 dark:hover:bg-slate-800"
                          >
                            <KeyRound className="w-3.5 h-3.5" />
                            <span>Rotate Key</span>
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDuplicateTenant(t)}
                            className="px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 text-xs font-medium hover:bg-slate-100 dark:hover:bg-slate-800"
                          >
                            Duplicate
                          </button>
                          <button
                            type="button"
                            onClick={() => handleToggleTenant(t.id)}
                            className="px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 text-xs font-medium hover:bg-slate-100 dark:hover:bg-slate-800"
                          >
                            {t.enabled ? 'Disable' : 'Enable'}
                          </button>
                          {tenants.length > 1 && (
                            <button
                              type="button"
                              onClick={() => handleDeleteTenant(t.id)}
                              aria-label={`Delete ${t.businessName}`}
                              className="p-1.5 rounded-lg border border-rose-500/30 text-rose-400 hover:bg-rose-500/10"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Domain Allowlist Manager for Selected Tenant */}
                <div className="border border-slate-200 dark:border-slate-800 rounded-xl bg-white dark:bg-slate-900 p-5 space-y-3">
                  <h3 className="text-sm font-semibold">
                    Domain Allowlist for {selectedTenant.businessName}
                  </h3>
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    {selectedTenant.domains.map((dom) => (
                      <div
                        key={dom}
                        className="flex items-center gap-1.5 px-2.5 py-1 rounded border border-slate-300 dark:border-slate-700 font-mono"
                      >
                        <span>{dom}</span>
                        <button
                          type="button"
                          onClick={() =>
                            setTenants((prev) =>
                              prev.map((t) =>
                                t.id === selectedTenant.id
                                  ? { ...t, domains: t.domains.filter((d) => d !== dom) }
                                  : t
                              )
                            )
                          }
                          className="text-rose-400 hover:text-rose-300"
                          aria-label={`Remove domain ${dom}`}
                        >
                          ✕
                        </button>
                      </div>
                    ))}
                  </div>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      const clean = domainInput.trim().toLowerCase();
                      if (!clean) return;
                      setTenants((prev) =>
                        prev.map((t) =>
                          t.id === selectedTenant.id && !t.domains.includes(clean)
                            ? { ...t, domains: [...t.domains, clean] }
                            : t
                        )
                      );
                      setDomainInput('');
                    }}
                    className="flex gap-2 max-w-md"
                  >
                    <input
                      type="text"
                      value={domainInput}
                      onChange={(e) => setDomainInput(e.target.value)}
                      placeholder="Add allowed domain (e.g. app.customer.com)"
                      aria-label="Allowed domain input"
                      className="flex-1 px-3 py-1.5 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-950"
                    />
                    <button
                      type="submit"
                      className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-xs font-medium"
                    >
                      Add Domain
                    </button>
                  </form>
                </div>
              </div>
            )}

            {/* TAB 3: KNOWLEDGE BASE */}
            {activeTab === 'knowledge' && (
              <div className="space-y-6">
                <div className="border border-slate-200 dark:border-slate-800 rounded-xl bg-white dark:bg-slate-900 p-5">
                  <h2 className="text-base font-semibold mb-1">
                    Safe Versioned Knowledge Ingestion — {selectedTenant.businessName}
                  </h2>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mb-4">
                    Supports PDF, DOCX, CSV, Markdown, and TXT. Stages vectors first and activates the new index version only after verification.
                  </p>
                  {uploadNotice && (
                    <div className="mb-3 p-3 rounded-lg border border-indigo-500/30 bg-indigo-500/10 text-xs text-indigo-300">
                      {uploadNotice}
                    </div>
                  )}
                  <form onSubmit={handleIngestDocument} className="space-y-3">
                    <input
                      type="text"
                      placeholder="Document filename (e.g. membership_faq.pdf or pricing.csv)"
                      aria-label="Document filename"
                      value={docFilename}
                      onChange={(e) => setDocFilename(e.target.value)}
                      className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-950"
                    />
                    <textarea
                      rows={4}
                      placeholder="Paste verified business content to chunk and embed (128 dimensions)..."
                      aria-label="Document text content"
                      value={docContent}
                      onChange={(e) => setDocContent(e.target.value)}
                      className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-950"
                    />
                    <button
                      type="submit"
                      className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold flex items-center gap-1.5"
                    >
                      <Upload className="w-4 h-4" />
                      <span>Upload & Stage Vector Index</span>
                    </button>
                  </form>
                </div>

                <div className="border border-slate-200 dark:border-slate-800 rounded-xl bg-white dark:bg-slate-900 overflow-hidden">
                  <div className="px-5 py-3.5 border-b border-slate-200 dark:border-slate-800">
                    <h3 className="text-sm font-semibold">
                      Active Knowledge Documents ({tenantDocs.length})
                    </h3>
                  </div>
                  <div className="divide-y divide-slate-200 dark:divide-slate-800">
                    {tenantDocs.map((doc) => (
                      <div
                        key={doc.id}
                        className="p-4 flex flex-wrap items-center justify-between gap-4 text-xs"
                      >
                        <div className="space-y-1">
                          <div className="font-semibold text-sm text-slate-900 dark:text-slate-100">
                            {doc.filename}
                          </div>
                          <div className="text-slate-500 dark:text-slate-400 tabular-nums">
                            Path: <code className="font-mono">{doc.storagePath}</code> · Version: v
                            {doc.activeVersion} · {doc.chunkCount} chunks · {doc.fileSize} bytes · Status:{' '}
                            <span className="text-emerald-500 font-medium">{doc.status}</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => handleRebuildDoc(doc.id)}
                            className="px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 flex items-center gap-1 hover:bg-slate-100 dark:hover:bg-slate-800"
                          >
                            <RefreshCw className="w-3.5 h-3.5" />
                            <span>Rebuild Index</span>
                          </button>
                          <button
                            type="button"
                            onClick={() =>
                              setDocs((prev) => prev.filter((item) => item.id !== doc.id))
                            }
                            aria-label={`Delete ${doc.filename}`}
                            className="p-1.5 rounded-lg border border-rose-500/30 text-rose-400 hover:bg-rose-500/10"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* TAB 4: CONVERSATIONS & FEEDBACK */}
            {activeTab === 'conversations' && (
              <div className="space-y-6">
                <div className="border border-slate-200 dark:border-slate-800 rounded-xl bg-white dark:bg-slate-900 p-5 space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <h2 className="text-base font-semibold">
                        Conversation Memory & Message Feedback — {selectedTenant.businessName}
                      </h2>
                      <p className="text-xs text-slate-500 dark:text-slate-400">
                        Session ID: <code className="font-mono">{activeConversation.sessionId}</code> ·
                        Preferred Language: {activeConversation.preferredLanguage || 'auto'}
                      </p>
                    </div>
                  </div>

                  {activeConversation.summary && (
                    <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 text-xs">
                      <span className="font-semibold">Rolling Memory Summary: </span>
                      <span>{activeConversation.summary}</span>
                    </div>
                  )}

                  <div className="space-y-2.5">
                    {activeConversation.messages.length === 0 ? (
                      <p className="text-xs text-slate-500">
                        No messages yet for this tenant session. Send a message in the Live Widget panel on the right!
                      </p>
                    ) : (
                      activeConversation.messages.map((m) => (
                        <div
                          key={m.id}
                          className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 text-xs space-y-1"
                        >
                          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400">
                            <span>
                              Role: <strong className="text-slate-900 dark:text-slate-100">{m.role}</strong> · Intent: {m.intent} · Lang: {m.language} · Evidence: {m.evidenceState}
                            </span>
                            {m.feedback && (
                              <span className="font-medium text-indigo-400">
                                Feedback: {m.feedback.toUpperCase()}
                              </span>
                            )}
                          </div>
                          <div className="text-sm text-slate-900 dark:text-slate-100">{m.content}</div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* TAB 5: LEADS & WORKFLOW */}
            {activeTab === 'leads' && (
              <div className="space-y-6">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="relative">
                      <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-400" />
                      <input
                        type="text"
                        value={leadSearch}
                        onChange={(e) => setLeadSearch(e.target.value)}
                        placeholder="Search leads..."
                        aria-label="Search leads"
                        className="pl-8 pr-3 py-1.5 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                      />
                    </div>
                    {(['all', 'new', 'contacted', 'qualified', 'won', 'lost'] as const).map((st) => (
                      <button
                        key={st}
                        type="button"
                        onClick={() => setLeadStatusFilter(st)}
                        className={`px-2.5 py-1.5 rounded-lg text-xs font-medium capitalize ${
                          leadStatusFilter === st
                            ? 'bg-indigo-600 text-white'
                            : 'border border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-300'
                        }`}
                      >
                        {st}
                      </button>
                    ))}
                  </div>
                  <button
                    type="button"
                    onClick={handleExportLeadsCsv}
                    className="px-3.5 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 text-xs font-medium flex items-center gap-1.5 hover:bg-slate-100 dark:hover:bg-slate-800"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Export CSV</span>
                  </button>
                </div>

                <div className="border border-slate-200 dark:border-slate-800 rounded-xl bg-white dark:bg-slate-900 overflow-hidden">
                  <table className="w-full text-left text-xs">
                    <thead className="border-b border-slate-200 dark:border-slate-800 text-slate-500 bg-slate-50/50 dark:bg-slate-950/40">
                      <tr>
                        <th className="py-2.5 px-4 font-medium">Contact</th>
                        <th className="py-2.5 px-4 font-medium">Requirement</th>
                        <th className="py-2.5 px-4 font-medium">Workflow Status</th>
                        <th className="py-2.5 px-4 font-medium">Outbox</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                      {filteredLeads.map((lead) => (
                        <tr key={lead.id}>
                          <td className="py-3 px-4">
                            <div className="font-semibold text-slate-900 dark:text-slate-100">
                              {lead.name}
                            </div>
                            <div className="text-slate-500">
                              {lead.email} · {lead.phone}
                            </div>
                          </td>
                          <td className="py-3 px-4">
                            <div>{lead.requirement}</div>
                            <div className="text-slate-500">{lead.notes}</div>
                          </td>
                          <td className="py-3 px-4">
                            <select
                              aria-label={`Lead status for ${lead.name}`}
                              value={lead.status}
                              onChange={(e) =>
                                setLeads((prev) =>
                                  prev.map((item) =>
                                    item.id === lead.id
                                      ? {
                                          ...item,
                                          status: e.target.value as LeadItem['status'],
                                        }
                                      : item
                                  )
                                )
                              }
                              className="px-2 py-1 rounded border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-950"
                            >
                              <option value="new">new</option>
                              <option value="contacted">contacted</option>
                              <option value="qualified">qualified</option>
                              <option value="won">won</option>
                              <option value="lost">lost</option>
                            </select>
                          </td>
                          <td className="py-3 px-4 text-emerald-500 font-medium">
                            {lead.notificationStatus}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* TAB 6: PROMPT VERSIONING */}
            {activeTab === 'prompts' && (
              <div className="space-y-6">
                <div className="border border-slate-200 dark:border-slate-800 rounded-xl bg-white dark:bg-slate-900 p-5 space-y-4">
                  <h2 className="text-base font-semibold">
                    Prompt Version Control — {selectedTenant.businessName}
                  </h2>
                  <div className="space-y-3">
                    <div>
                      <label className="block text-xs font-medium text-slate-500 mb-1">
                        System Prompt
                      </label>
                      <textarea
                        rows={3}
                        value={promptDraft || selectedTenant.systemPrompt}
                        onChange={(e) => setPromptDraft(e.target.value)}
                        className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-950"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-500 mb-1">
                        Fallback Answer (Used when Evidence = UNKNOWN)
                      </label>
                      <textarea
                        rows={2}
                        value={fallbackDraft || selectedTenant.fallbackAnswer}
                        onChange={(e) => setFallbackDraft(e.target.value)}
                        className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-950"
                      />
                    </div>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        placeholder="Version note (e.g. Tuned Hindi tone)"
                        value={promptNote}
                        onChange={(e) => setPromptNote(e.target.value)}
                        className="flex-1 px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-950"
                      />
                      <button
                        type="button"
                        onClick={() => {
                          const nextVer = (selectedTenant.promptVersions[0]?.versionNumber || 1) + 1;
                          const sys = (promptDraft || selectedTenant.systemPrompt).trim();
                          const fb = (fallbackDraft || selectedTenant.fallbackAnswer).trim();
                          setTenants((prev) =>
                            prev.map((t) =>
                              t.id === selectedTenant.id
                                ? {
                                    ...t,
                                    systemPrompt: sys,
                                    fallbackAnswer: fb,
                                    promptVersions: [
                                      {
                                        versionNumber: nextVer,
                                        systemPrompt: sys,
                                        fallbackAnswer: fb,
                                        welcomeMessage: t.welcomeMessage,
                                        note: promptNote.trim() || `Saved v${nextVer}`,
                                        createdAt: new Date().toISOString(),
                                      },
                                      ...t.promptVersions,
                                    ],
                                  }
                                : t
                            )
                          );
                          setPromptNote('');
                        }}
                        className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-xs font-semibold whitespace-nowrap"
                      >
                        Save New Version
                      </button>
                    </div>
                  </div>

                  <div className="pt-4 border-t border-slate-200 dark:border-slate-800 space-y-2">
                    <div className="text-xs font-semibold text-slate-500">Saved Versions</div>
                    {selectedTenant.promptVersions.map((pv) => (
                      <div
                        key={pv.versionNumber}
                        className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 flex items-center justify-between gap-4 text-xs"
                      >
                        <div>
                          <div className="font-semibold">
                            v{pv.versionNumber} · {pv.note}
                          </div>
                          <div className="text-slate-500 truncate max-w-xl">{pv.systemPrompt}</div>
                        </div>
                        <button
                          type="button"
                          onClick={() => {
                            setPromptDraft(pv.systemPrompt);
                            setFallbackDraft(pv.fallbackAnswer);
                            setTenants((prev) =>
                              prev.map((t) =>
                                t.id === selectedTenant.id
                                  ? {
                                      ...t,
                                      systemPrompt: pv.systemPrompt,
                                      fallbackAnswer: pv.fallbackAnswer,
                                    }
                                  : t
                              )
                            );
                          }}
                          className="px-3 py-1 rounded border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800"
                        >
                          Restore v{pv.versionNumber}
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* TAB 7: WIDGET STUDIO & EMBED CODE */}
            {activeTab === 'widget' && (
              <div className="space-y-6">
                <div className="border border-slate-200 dark:border-slate-800 rounded-xl bg-white dark:bg-slate-900 p-5 space-y-4">
                  <h2 className="text-base font-semibold">
                    Widget Appearance & Embed Code — {selectedTenant.businessName}
                  </h2>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
                    <div>
                      <label className="block text-slate-500 mb-1">Primary Accent Color</label>
                      <input
                        type="color"
                        aria-label="Widget primary color"
                        value={selectedTenant.widgetConfig.primaryColor}
                        onChange={(e) =>
                          setTenants((prev) =>
                            prev.map((t) =>
                              t.id === selectedTenant.id
                                ? {
                                    ...t,
                                    widgetConfig: { ...t.widgetConfig, primaryColor: e.target.value },
                                  }
                                : t
                            )
                          )
                        }
                        className="w-full h-9 rounded border border-slate-300 dark:border-slate-700 cursor-pointer"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-500 mb-1">Widget Theme</label>
                      <select
                        aria-label="Widget theme mode"
                        value={selectedTenant.widgetConfig.theme}
                        onChange={(e) =>
                          setTenants((prev) =>
                            prev.map((t) =>
                              t.id === selectedTenant.id
                                ? {
                                    ...t,
                                    widgetConfig: {
                                      ...t.widgetConfig,
                                      theme: e.target.value as 'dark' | 'light',
                                    },
                                  }
                                : t
                            )
                          )
                        }
                        className="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-950"
                      >
                        <option value="dark">Dark Mode</option>
                        <option value="light">Light Mode</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-slate-500 mb-1">Placement</label>
                      <select
                        aria-label="Widget position"
                        value={selectedTenant.widgetConfig.position}
                        onChange={(e) =>
                          setTenants((prev) =>
                            prev.map((t) =>
                              t.id === selectedTenant.id
                                ? {
                                    ...t,
                                    widgetConfig: {
                                      ...t.widgetConfig,
                                      position: e.target.value as 'bottom-right' | 'bottom-left',
                                    },
                                  }
                                : t
                            )
                          )
                        }
                        className="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-950"
                      >
                        <option value="bottom-right">Bottom Right</option>
                        <option value="bottom-left">Bottom Left</option>
                      </select>
                    </div>
                  </div>

                  <div className="pt-4 border-t border-slate-200 dark:border-slate-800">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-semibold">Single-Script-Tag Website Embed Code</span>
                      <button
                        type="button"
                        onClick={() => {
                          if (navigator.clipboard && navigator.clipboard.writeText) {
                            navigator.clipboard.writeText(embedScriptTag);
                          }
                          setCopiedEmbed(true);
                          setTimeout(() => setCopiedEmbed(false), 1500);
                        }}
                        className="px-3 py-1 rounded border border-slate-300 dark:border-slate-700 text-xs flex items-center gap-1"
                      >
                        {copiedEmbed ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                        <span>{copiedEmbed ? 'Copied' : 'Copy Embed Tag'}</span>
                      </button>
                    </div>
                    <pre className="p-3 rounded-lg bg-slate-950 text-slate-200 font-mono text-xs overflow-x-auto">
                      {embedScriptTag}
                    </pre>
                  </div>
                </div>
              </div>
            )}

            {/* TAB 8: SQL MIGRATIONS & PYTHON TEST SUITE */}
            {activeTab === 'sql' && <SqlAndRepoView />}
          </main>

          {/* Right Column: Live Interactive Customer Widget (Always Accessible for Testing) */}
          <aside className="w-full lg:w-[410px] border-t lg:border-t-0 lg:border-l border-slate-200 dark:border-slate-800 bg-white/50 dark:bg-slate-900/40 p-4 shrink-0 flex flex-col justify-between">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                    Live Embedded Widget Preview
                  </h2>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    Try English, हिंदी, or Hinglish + Like/Dislike/Copy/Share
                  </p>
                </div>
              </div>

              <WidgetPreview
                tenant={selectedTenant}
                docs={docs}
                conversation={activeConversation}
                onUpdateConversation={handleUpdateConversation}
                onResetConversation={handleResetConversation}
                onFeedback={handleMessageFeedback}
                onCreateLead={handleCreateLead}
              />
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}

export default App;
