export type OrbitLanguage = 'en' | 'hi-deva' | 'hi-latn' | 'es' | 'fr';

export type OrbitIntent =
  | 'greeting'
  | 'identity'
  | 'language_switch'
  | 'memory_query'
  | 'summary'
  | 'business_query';

export type EvidenceState = 'SUPPORTED' | 'PARTIAL' | 'UNKNOWN';

export interface WidgetSettings {
  primaryColor: string;
  theme: 'dark' | 'light';
  position: 'bottom-right' | 'bottom-left';
  width: number;
  height: number;
  radius: number;
  inputPlaceholder: string;
  showBranding: boolean;
  suggestedQuestions: string[];
}

export interface KnowledgeDoc {
  id: string;
  clientId: string;
  filename: string;
  safeFilename: string;
  storagePath: string;
  format: 'PDF' | 'DOCX' | 'CSV' | 'MD' | 'TXT';
  fileSize: number;
  status: 'ready' | 'processing' | 'failed';
  activeVersion: number;
  chunkCount: number;
  chunks: string[];
  updatedAt: string;
}

export interface PromptVersion {
  versionNumber: number;
  systemPrompt: string;
  fallbackAnswer: string;
  welcomeMessage: string;
  note: string;
  createdAt: string;
}

export interface TenantClient {
  id: string;
  businessName: string;
  slug: string;
  enabled: boolean;
  assistantName: string;
  companyName: string;
  systemPrompt: string;
  fallbackAnswer: string;
  welcomeMessage: string;
  language: OrbitLanguage;
  temperature: number;
  topK: number;
  minSimilarity: number;
  leadCaptureEnabled: boolean;
  notificationEmail: string;
  domains: string[];
  apiKeyPrefix: string;
  apiKeyHash: string;
  widgetConfig: WidgetSettings;
  promptVersions: PromptVersion[];
  createdAt: string;
}

export interface ChatMessage {
  id: string;
  conversationId: string;
  clientId: string;
  role: 'user' | 'assistant';
  content: string;
  intent: OrbitIntent;
  language: OrbitLanguage;
  evidenceState: EvidenceState;
  sources: { filename: string; version: number; similarity: number; snippet: string }[];
  latencyMs: number;
  feedback?: 'like' | 'dislike';
  createdAt: string;
}

export interface ConversationThread {
  id: string;
  clientId: string;
  sessionId: string;
  preferredLanguage: OrbitLanguage | null;
  summary: string;
  messages: ChatMessage[];
  updatedAt: string;
}

export interface LeadItem {
  id: string;
  clientId: string;
  conversationId: string;
  idempotencyKey: string;
  name: string;
  email: string;
  phone: string;
  requirement: string;
  message: string;
  status: 'new' | 'contacted' | 'qualified' | 'won' | 'lost';
  assignee: string;
  notes: string;
  notificationStatus: 'sent' | 'pending' | 'failed';
  createdAt: string;
}

const DEVANAGARI_RE = /[\u0900-\u097F]/;

const ROMAN_HINDI_WORDS = new Set([
  'aap', 'kaun', 'ho', 'hain', 'hai', 'mein', 'likho', 'bolo', 'batao', 'bataiye',
  'tum', 'kya', 'karte', 'humne', 'tumse', 'pahle', 'pehle', 'pucha', 'puchha',
  'tha', 'mujhe', 'chahiye', 'kitna', 'kitne', 'kahan', 'kab', 'namaste', 'shukriya',
  'dhanyawad', 'uske', 'iske', 'baare', 'bare', 'jankari', 'madad', 'kimat', 'samay'
]);

const SPANISH_WORDS = new Set(['hola', 'qué', 'como', 'cómo', 'puedes', 'gracias', 'precio', 'horario', 'español']);
const FRENCH_WORDS = new Set(['bonjour', 'comment', 'merci', 'prix', 'horaires', 'français', 'pouvez']);

const MULTILINGUAL_SYNONYMS: Record<string, string[]> = {
  price: ['pricing', 'cost', 'fee', 'membership', 'plan', 'kimat', 'कीमत', 'फीस'],
  kimat: ['price', 'pricing', 'cost', 'fee', 'membership', 'plan'],
  'कीमत': ['price', 'pricing', 'cost', 'fee', 'membership', 'plan'],
  'सदस्यता': ['membership', 'plan', 'price', 'monthly'],
  hours: ['opening', 'timing', 'schedule', 'open', 'samay', 'समय'],
  samay: ['hours', 'opening', 'timing', 'schedule', 'open'],
  'समय': ['hours', 'opening', 'timing', 'schedule', 'open'],
  refund: ['return', 'cancellation', 'policy', 'रिफंड'],
  'रिफंड': ['refund', 'return', 'cancellation', 'policy'],
  delivery: ['shipping', 'dispatch', 'order', 'box', 'डिलीवरी'],
  'डिलीवरी': ['delivery', 'shipping', 'order', 'box'],
};

export function detectLanguageAndPreference(
  message: string,
  currentPreference: OrbitLanguage | null,
  tenantDefault: OrbitLanguage = 'en'
): { responseLanguage: OrbitLanguage; updatedPreference: OrbitLanguage | null } {
  const text = (message || '').trim();
  const lower = text.toLowerCase();

  if (/(?:hinglish\s+mein|in\s+hinglish|roman\s+hindi\s+mein)/i.test(text)) {
    return { responseLanguage: 'hi-latn', updatedPreference: 'hi-latn' };
  }
  if (
    /(?:hindi\s+mein\s+(?:likho|bolo|baat\s+karo|batao|reply)|reply\s+in\s+hindi|speak\s+in\s+hindi|हिंदी\s+में|हिन्दी\s+में)/i.test(
      text
    )
  ) {
    return { responseLanguage: 'hi-deva', updatedPreference: 'hi-deva' };
  }
  if (/(?:english\s+please|reply\s+in\s+english|speak\s+in\s+english|switch\s+to\s+english|अंग्रेजी\s+में)/i.test(text)) {
    return { responseLanguage: 'en', updatedPreference: 'en' };
  }
  if (/(?:reply\s+in\s+spanish|habla\s+en\s+español|en\s+español)/i.test(text)) {
    return { responseLanguage: 'es', updatedPreference: 'es' };
  }
  if (/(?:reply\s+in\s+french|en\s+français|parlez\s+français)/i.test(text)) {
    return { responseLanguage: 'fr', updatedPreference: 'fr' };
  }

  if (DEVANAGARI_RE.test(text)) {
    return { responseLanguage: 'hi-deva', updatedPreference: currentPreference || 'hi-deva' };
  }

  const words = lower.match(/[a-zà-ÿ]+/gi) || [];
  const hindiCount = words.filter((w) => ROMAN_HINDI_WORDS.has(w.toLowerCase())).length;
  if (hindiCount >= 2 || (hindiCount >= 1 && words.length <= 4)) {
    if (currentPreference === 'hi-deva') {
      return { responseLanguage: 'hi-deva', updatedPreference: 'hi-deva' };
    }
    return { responseLanguage: 'hi-latn', updatedPreference: currentPreference || 'hi-latn' };
  }

  if (words.some((w) => SPANISH_WORDS.has(w.toLowerCase()))) {
    return { responseLanguage: 'es', updatedPreference: currentPreference || 'es' };
  }
  if (words.some((w) => FRENCH_WORDS.has(w.toLowerCase()))) {
    return { responseLanguage: 'fr', updatedPreference: currentPreference || 'fr' };
  }

  if (currentPreference) {
    return { responseLanguage: currentPreference, updatedPreference: currentPreference };
  }
  return { responseLanguage: tenantDefault, updatedPreference: null };
}

export function classifyConversationIntent(message: string): OrbitIntent {
  const text = (message || '').trim();
  if (!text) return 'greeting';

  if (
    /(?:hindi\s+mein\s+(?:likho|bolo|baat\s+karo|batao|reply)|hinglish\s+mein|reply\s+in\s+(?:hindi|english|spanish|french)|english\s+please|हिंदी\s+में\s+(?:लिखो|बोलो|बात\s+करो))/i.test(
      text
    )
  ) {
    return 'language_switch';
  }

  if (
    /(?:summarize\s+(?:our\s+)?(?:chat|conversation|discussion)|give\s+me\s+a\s+summary|(?:baat-?cheet|chat|conversation)\s+ka\s+(?:summary|saransh)|सारांश)/i.test(
      text
    )
  ) {
    return 'summary';
  }

  if (
    /(?:what\s+did\s+i\s+ask\s+(?:earlier|before|previously)|what\s+was\s+my\s+(?:previous|first|last)\s+question|humne\s+(?:tumse\s+)?(?:pahle|pehle)\s+kya\s+(?:pucha|puchha)\s+tha|maine\s+(?:pahle|pehle)\s+kya\s+(?:pucha|puchha)\s+tha|हमने\s+(?:तुमसे\s+)?पहले\s+क्या\s+पूछा\s+था)/i.test(
      text
    )
  ) {
    return 'memory_query';
  }

  if (
    /\b(?:who\s+are\s+you|what\s+are\s+you|what\s+do\s+you\s+do|what\s+can\s+you\s+do|aap\s+kaun\s+(?:ho|hain)|tum\s+kaun\s+ho|tum\s+kya\s+karte\s+ho|aap\s+kya\s+karte\s+(?:ho|hain)|आप\s+कौन\s+(?:हो|हैं)|तुम\s+क्या\s+करते\s+हो)\b/i.test(
      text
    )
  ) {
    return 'identity';
  }

  if (
    /^\s*(?:hello|hi|hey|good\s+(?:morning|afternoon|evening)|namaste|namaskar|नमस्ते|नमस्कार|hola|bonjour|thanks|thank\s+you|shukriya|dhanyawad|धन्यवाद)[!.,\s]*$/i.test(
      text
    )
  ) {
    return 'greeting';
  }

  return 'business_query';
}

export function computeDeterministicEmbedding128(text: string): number[] {
  const dims = 128;
  const vec = new Array<number>(dims).fill(0);
  const clean = (text || '').trim().toLowerCase();
  if (!clean) {
    vec[0] = 1;
    return vec;
  }
  const tokens = clean.match(/[\w\u0900-\u097F]+/g) || [];
  for (const tok of tokens) {
    let h = 2166136261;
    for (let i = 0; i < tok.length; i++) {
      h ^= tok.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    const idx = Math.abs(h) % dims;
    const sign = (h & 1) === 0 ? 1 : -1;
    vec[idx] += sign * 2.0;
  }
  const norm = Math.sqrt(vec.reduce((acc, v) => acc + v * v, 0));
  if (norm > 1e-9) {
    return vec.map((v) => Number((v / norm).toFixed(6)));
  }
  vec[0] = 1;
  return vec;
}

export function cosineSimilarity(a: number[], b: number[]): number {
  if (a.length !== b.length || a.length === 0) return 0;
  let dot = 0;
  let na = 0;
  let nb = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  if (na <= 1e-9 || nb <= 1e-9) return 0;
  return dot / (Math.sqrt(na) * Math.sqrt(nb));
}

const STOPWORDS = new Set([
  'what', 'are', 'is', 'the', 'a', 'an', 'for', 'to', 'of', 'in', 'on', 'at',
  'do', 'you', 'have', 'can', 'please', 'tell', 'me', 'about', 'how', 'much',
  'does', 'it', 'that', 'this', 'your', 'and', 'or', 'kya', 'hai', 'hain',
  'ka', 'ki', 'ke', 'mein', 'se', 'ko', 'aur', 'batao', 'aap', 'uske', 'baare',
  'क्या', 'है', 'हैं', 'का', 'की', 'के', 'में'
]);

export function retrieveTenantEvidence(
  tenant: TenantClient,
  docs: KnowledgeDoc[],
  query: string,
  priorMessages: ChatMessage[]
): {
  evidenceState: EvidenceState;
  sources: { filename: string; version: number; similarity: number; snippet: string }[];
  matchedText: string;
} {
  const tenantDocs = docs.filter((d) => d.clientId === tenant.id && d.status === 'ready');
  if (tenantDocs.length === 0) {
    return { evidenceState: 'UNKNOWN', sources: [], matchedText: '' };
  }

  // Follow-up pronoun resolution
  let effectiveQuery = query;
  if (
    /\b(?:it|that|this|uske|iske|uska|iska|उसके|इसके)\b/i.test(query) &&
    priorMessages.length > 0
  ) {
    const lastUser = [...priorMessages].reverse().find((m) => m.role === 'user');
    if (lastUser) {
      effectiveQuery = `${query} ${lastUser.content}`;
    }
  }

  const rawTokens = (effectiveQuery.toLowerCase().match(/[\w\u0900-\u097F]+/g) || []).filter(
    (t) => t.length >= 2 && !STOPWORDS.has(t)
  );
  const expandedTerms = new Set<string>(rawTokens);
  for (const t of rawTokens) {
    if (MULTILINGUAL_SYNONYMS[t]) {
      MULTILINGUAL_SYNONYMS[t].forEach((s) => expandedTerms.add(s.toLowerCase()));
    }
  }

  const queryVec = computeDeterministicEmbedding128([...expandedTerms].join(' ') || effectiveQuery);
  const scored: {
    filename: string;
    version: number;
    chunk: string;
    score: number;
    coverage: number;
  }[] = [];

  for (const doc of tenantDocs) {
    for (const chunk of doc.chunks) {
      const chunkLower = chunk.toLowerCase();
      const chunkTokens = new Set(chunkLower.match(/[\w\u0900-\u097F]+/g) || []);
      let hits = 0;
      for (const qTerm of rawTokens) {
        const syns = [qTerm, ...(MULTILINGUAL_SYNONYMS[qTerm] || [])];
        if (syns.some((s) => chunkTokens.has(s.toLowerCase()) || chunkLower.includes(s.toLowerCase()))) {
          hits += 1;
        }
      }
      const coverage = rawTokens.length > 0 ? hits / rawTokens.length : 0;
      const denseSim = cosineSimilarity(queryVec, computeDeterministicEmbedding128(chunk));
      const combined = Number((0.45 * denseSim + 0.55 * coverage).toFixed(4));
      if (combined >= tenant.minSimilarity && coverage > 0) {
        scored.push({
          filename: doc.filename,
          version: doc.activeVersion,
          chunk,
          score: combined,
          coverage,
        });
      }
    }
  }

  scored.sort((a, b) => b.score - a.score);
  const top = scored.slice(0, tenant.topK);
  if (top.length === 0) {
    return { evidenceState: 'UNKNOWN', sources: [], matchedText: '' };
  }

  const bestCoverage = Math.max(...top.map((t) => t.coverage));
  const evidenceState: EvidenceState =
    bestCoverage >= 0.5 && top[0].score >= Math.max(tenant.minSimilarity, 0.28)
      ? 'SUPPORTED'
      : bestCoverage >= 0.25
      ? 'PARTIAL'
      : 'UNKNOWN';

  if (evidenceState === 'UNKNOWN') {
    return { evidenceState: 'UNKNOWN', sources: [], matchedText: '' };
  }

  return {
    evidenceState,
    sources: top.map((t) => ({
      filename: t.filename,
      version: t.version,
      similarity: t.score,
      snippet: t.chunk,
    })),
    matchedText: top.map((t) => t.chunk).join(' '),
  };
}

export function validateGroundingClaim(
  candidateAnswer: string,
  evidenceText: string,
  evidenceState: EvidenceState,
  fallbackAnswer: string
): { isGrounded: boolean; finalAnswer: string; violations: string[] } {
  if (evidenceState === 'UNKNOWN' || !evidenceText.trim()) {
    return { isGrounded: false, finalAnswer: fallbackAnswer, violations: ['insufficient_evidence'] };
  }
  const violations: string[] = [];
  const evNums = new Set(
    (evidenceText.match(/\b\d+(?:[.,]\d+)?\b/g) || []).map((n) => n.replace(/,/g, ''))
  );
  const ansNums = (candidateAnswer.match(/\b\d+(?:[.,]\d+)?\b/g) || []).map((n) =>
    n.replace(/,/g, '')
  );
  for (const num of ansNums) {
    if (!evNums.has(num) && num !== '1' && num !== '2') {
      violations.push(`unsupported_numeric_claim:${num}`);
    }
  }

  if (violations.length > 0) {
    return { isGrounded: false, finalAnswer: fallbackAnswer, violations };
  }
  return { isGrounded: true, finalAnswer: candidateAnswer, violations: [] };
}

export function orchestrateChatTurn(
  tenant: TenantClient,
  docs: KnowledgeDoc[],
  conversation: ConversationThread,
  userMessage: string
): {
  answer: string;
  intent: OrbitIntent;
  language: OrbitLanguage;
  preferredLanguage: OrbitLanguage | null;
  evidenceState: EvidenceState;
  sources: { filename: string; version: number; similarity: number; snippet: string }[];
} {
  const { responseLanguage, updatedPreference } = detectLanguageAndPreference(
    userMessage,
    conversation.preferredLanguage,
    tenant.language
  );
  const intent = classifyConversationIntent(userMessage);
  const priorUserQuestions = conversation.messages
    .filter((m) => m.role === 'user')
    .map((m) => m.content);

  if (intent === 'greeting') {
    const answerByLang: Record<OrbitLanguage, string> = {
      en: `Hello! I am ${tenant.assistantName} for ${tenant.companyName}. How can I help you today?`,
      'hi-deva': `नमस्ते! मैं ${tenant.assistantName} हूँ (${tenant.companyName})। आज मैं आपकी क्या सहायता कर सकता हूँ?`,
      'hi-latn': `Namaste! Main ${tenant.assistantName} hoon (${tenant.companyName} ki taraf se). Aaj main aapki kya madad kar sakta hoon?`,
      es: `¡Hola! Soy ${tenant.assistantName} de ${tenant.companyName}. ¿En qué puedo ayudarte hoy?`,
      fr: `Bonjour ! Je suis ${tenant.assistantName} de ${tenant.companyName}. Comment puis-je vous aider aujourd'hui ?`,
    };
    return {
      answer: answerByLang[responseLanguage],
      intent,
      language: responseLanguage,
      preferredLanguage: updatedPreference,
      evidenceState: 'SUPPORTED',
      sources: [],
    };
  }

  if (intent === 'identity') {
    const idByLang: Record<OrbitLanguage, string> = {
      en: `I am ${tenant.assistantName}, the AI support assistant for ${tenant.companyName}. I can answer questions using verified ${tenant.companyName} documentation, remember our conversation context, and connect you with our team.`,
      'hi-deva': `मैं ${tenant.assistantName} हूँ, ${tenant.companyName} का एआई सहायता सहायक। मैं ${tenant.companyName} की सत्यापित जानकारी के आधार पर आपके प्रश्नों का उत्तर दे सकता हूँ और सहायता टीम से जोड़ सकता हूँ।`,
      'hi-latn': `Main ${tenant.assistantName} hoon, ${tenant.companyName} ka AI support assistant. Main ${tenant.companyName} ke verified documents ke aadhar par aapke sawalon ka jawab de sakta hoon aur support team se connect kara sakta hoon.`,
      es: `Soy ${tenant.assistantName}, el asistente virtual de ${tenant.companyName}. Puedo responder preguntas verificadas sobre ${tenant.companyName} y conectarte con nuestro equipo.`,
      fr: `Je suis ${tenant.assistantName}, l'assistant virtuel de ${tenant.companyName}. Je réponds à vos questions à partir des documents vérifiés de ${tenant.companyName}.`,
    };
    return {
      answer: idByLang[responseLanguage],
      intent,
      language: responseLanguage,
      preferredLanguage: updatedPreference,
      evidenceState: 'SUPPORTED',
      sources: [],
    };
  }

  if (intent === 'language_switch') {
    const switchByLang: Record<OrbitLanguage, string> = {
      en: 'Certainly! I will reply in English from now on. How can I assist you?',
      'hi-deva': 'जी बिल्कुल, अब से मैं आपके सभी सवालों का जवाब हिंदी में दूँगा। बताइए, मैं आपकी क्या मदद कर सकता हूँ?',
      'hi-latn': 'Bilkul! Ab se main Hinglish mein baat karunga. Bataiye, main aapki kya madad kar sakta hoon?',
      es: '¡Por supuesto! A partir de ahora responderé en español. ¿En qué puedo ayudarte?',
      fr: 'Bien sûr ! Je répondrai désormais en français. Comment puis-je vous aider ?',
    };
    return {
      answer: switchByLang[responseLanguage],
      intent,
      language: responseLanguage,
      preferredLanguage: updatedPreference,
      evidenceState: 'SUPPORTED',
      sources: [],
    };
  }

  if (intent === 'memory_query') {
    if (priorUserQuestions.length === 0) {
      const emptyMem: Record<OrbitLanguage, string> = {
        en: 'You have not asked any earlier questions in this conversation yet.',
        'hi-deva': 'इस बातचीत में आपने इससे पहले कोई प्रश्न नहीं पूछा है।',
        'hi-latn': 'Is conversation mein aapne isse pehle koi sawal nahi pucha hai.',
        es: 'Aún no has hecho preguntas anteriores en esta conversación.',
        fr: "Vous n'avez pas encore posé de question dans cette conversation.",
      };
      return {
        answer: emptyMem[responseLanguage],
        intent,
        language: responseLanguage,
        preferredLanguage: updatedPreference,
        evidenceState: 'SUPPORTED',
        sources: [],
      };
    }
    const joined = priorUserQuestions.join(' ; ');
    const memByLang: Record<OrbitLanguage, string> = {
      en: `Earlier in this conversation, you asked: ${joined}`,
      'hi-deva': `इस बातचीत में आपने पहले यह पूछा था: ${joined}`,
      'hi-latn': `Is baat-cheet mein aapne pehle yeh pucha tha: ${joined}`,
      es: `Anteriormente en esta conversación preguntaste: ${joined}`,
      fr: `Plus tôt dans cette conversation, vous avez demandé : ${joined}`,
    };
    return {
      answer: memByLang[responseLanguage],
      intent,
      language: responseLanguage,
      preferredLanguage: updatedPreference,
      evidenceState: 'SUPPORTED',
      sources: [],
    };
  }

  if (intent === 'summary') {
    if (priorUserQuestions.length === 0) {
      return {
        answer:
          responseLanguage === 'hi-deva'
            ? 'अभी तक हमारी बातचीत में सारांश के लिए कोई पिछला संदेश नहीं है।'
            : 'There are no prior messages in this conversation to summarize yet.',
        intent,
        language: responseLanguage,
        preferredLanguage: updatedPreference,
        evidenceState: 'SUPPORTED',
        sources: [],
      };
    }
    const topics = priorUserQuestions.join(' | ');
    const sumByLang: Record<OrbitLanguage, string> = {
      en: `Conversation Summary: We discussed the following questions and topics — ${topics}`,
      'hi-deva': `हमारी बातचीत का सारांश: चर्चा किए गए मुख्य विषय — ${topics}`,
      'hi-latn': `Hamari baat-cheet ka summary: Aapne in vishayon par baat ki — ${topics}`,
      es: `Resumen de la conversación: Hablamos sobre — ${topics}`,
      fr: `Résumé de la conversation : Nous avons abordé — ${topics}`,
    };
    return {
      answer: sumByLang[responseLanguage],
      intent,
      language: responseLanguage,
      preferredLanguage: updatedPreference,
      evidenceState: 'SUPPORTED',
      sources: [],
    };
  }

  // Business query -> tenant-isolated RAG + Grounding
  const retrieval = retrieveTenantEvidence(tenant, docs, userMessage, conversation.messages);
  const localizedFallback: Record<OrbitLanguage, string> = {
    en: tenant.fallbackAnswer,
    'hi-deva': `क्षमा करें, मेरे पास ${tenant.companyName} के सत्यापित ज्ञानकोश में इस प्रश्न का सटीक उत्तर देने के लिए पर्याप्त जानकारी नहीं है। कृपया अपना संपर्क विवरण साझा करें ताकि हमारी टीम आपकी सहायता कर सके।`,
    'hi-latn': `Maaf kijiye, mere paas ${tenant.companyName} ke verified knowledge base mein is sawal ka sateek jawab dene ke liye paryapt jankari nahi hai. Kripya apni contact details share karein.`,
    es: `No tengo suficiente información verificada en la base de conocimientos de ${tenant.companyName} para responder con precisión.`,
    fr: `Je ne dispose pas d'informations vérifiées suffisantes pour répondre à cette question.`,
  };

  if (retrieval.evidenceState === 'UNKNOWN' || !retrieval.matchedText) {
    return {
      answer: localizedFallback[responseLanguage],
      intent,
      language: responseLanguage,
      preferredLanguage: updatedPreference,
      evidenceState: 'UNKNOWN',
      sources: [],
    };
  }

  const candidateByLang: Record<OrbitLanguage, string> = {
    en: `Based on verified ${tenant.companyName} information: ${retrieval.matchedText}`,
    'hi-deva': `${tenant.companyName} की सत्यापित जानकारी के अनुसार: ${retrieval.matchedText}`,
    'hi-latn': `${tenant.companyName} ki verified jankari ke anusar: ${retrieval.matchedText}`,
    es: `Según la información verificada de ${tenant.companyName}: ${retrieval.matchedText}`,
    fr: `Selon les informations vérifiées de ${tenant.companyName} : ${retrieval.matchedText}`,
  };

  const validation = validateGroundingClaim(
    candidateByLang[responseLanguage],
    retrieval.matchedText,
    retrieval.evidenceState,
    localizedFallback[responseLanguage]
  );

  return {
    answer: validation.finalAnswer,
    intent,
    language: responseLanguage,
    preferredLanguage: updatedPreference,
    evidenceState: validation.isGrounded ? retrieval.evidenceState : 'UNKNOWN',
    sources: validation.isGrounded ? retrieval.sources : [],
  };
}
