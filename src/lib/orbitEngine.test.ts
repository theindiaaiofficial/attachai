import test from 'node:test';
import assert from 'node:assert/strict';
import {
  classifyConversationIntent,
  computeDeterministicEmbedding128,
  detectLanguageAndPreference,
  orchestrateChatTurn,
  validateGroundingClaim,
  type ConversationThread,
  type KnowledgeDoc,
  type TenantClient,
} from './orbitEngine';

const sampleTenant: TenantClient = {
  id: 'tenant-puregym-01',
  businessName: 'PureGym Central',
  slug: 'puregym-central',
  enabled: true,
  assistantName: 'PureGym Coach AI',
  companyName: 'PureGym Central',
  systemPrompt: 'You are PureGym Coach AI.',
  fallbackAnswer: 'I do not have enough verified information in our knowledge base to answer that accurately.',
  welcomeMessage: 'Hello! How can I help you today?',
  language: 'en',
  temperature: 0.2,
  topK: 5,
  minSimilarity: 0.25,
  leadCaptureEnabled: true,
  notificationEmail: 'ops@puregym.example.com',
  domains: ['puregym.example.com', 'localhost'],
  apiKeyPrefix: 'orb_live_pg991',
  apiKeyHash: '8f9d2a1b4c3e',
  widgetConfig: {
    primaryColor: '#4f46e5',
    theme: 'dark',
    position: 'bottom-right',
    width: 380,
    height: 580,
    radius: 16,
    inputPlaceholder: 'Ask a question...',
    showBranding: true,
    suggestedQuestions: ['What are your membership prices?', 'What are your opening hours?'],
  },
  promptVersions: [],
  createdAt: '2026-10-30T10:00:00Z',
};

const sampleDocs: KnowledgeDoc[] = [
  {
    id: 'doc-1',
    clientId: 'tenant-puregym-01',
    filename: 'puregym_membership_pricing.pdf',
    safeFilename: 'puregym_membership_pricing.pdf',
    storagePath: 'tenant-puregym-01/doc-1/puregym_membership_pricing.pdf',
    format: 'PDF',
    fileSize: 18420,
    status: 'ready',
    activeVersion: 2,
    chunkCount: 2,
    chunks: [
      'Core Membership costs $29 per month with 24/7 gym access and freeze options.',
      'Plus Membership costs $49 per month including multi-gym access, classes, and guest passes. Opening hours: 24 hours a day, 7 days a week.',
    ],
    updatedAt: '2026-10-31T08:00:00Z',
  },
];

test('128-dimensional deterministic embedding contract', () => {
  const vec = computeDeterministicEmbedding128('PureGym membership pricing $29');
  assert.equal(vec.length, 128);
});

test('intent classification separates greetings, identity, language switches, memory, and business queries', () => {
  assert.equal(classifyConversationIntent('Hello'), 'greeting');
  assert.equal(classifyConversationIntent('Aap kaun ho?'), 'identity');
  assert.equal(classifyConversationIntent('Tum kya karte ho?'), 'identity');
  assert.equal(classifyConversationIntent('Hindi mein likho'), 'language_switch');
  assert.equal(classifyConversationIntent('Humne tumse pahle kya pucha tha?'), 'memory_query');
  assert.equal(classifyConversationIntent('Summarize our chat'), 'summary');
  assert.equal(classifyConversationIntent('What are your opening hours?'), 'business_query');
});

test('dynamic multilingual detection and language switching work across Hindi, Hinglish, and English', () => {
  const s1 = detectLanguageAndPreference('Hindi mein likho', null, 'en');
  assert.equal(s1.responseLanguage, 'hi-deva');
  assert.equal(s1.updatedPreference, 'hi-deva');

  const s2 = detectLanguageAndPreference('Reply in English', s1.updatedPreference, 'en');
  assert.equal(s2.responseLanguage, 'en');
  assert.equal(s2.updatedPreference, 'en');
});

test('orchestrateChatTurn handles grounded RAG and blocks unverified claims', () => {
  const conv: ConversationThread = {
    id: 'conv-1',
    clientId: sampleTenant.id,
    sessionId: 'sess-1',
    preferredLanguage: null,
    summary: '',
    messages: [],
    updatedAt: '2026-10-31T09:00:00Z',
  };

  const turn1 = orchestrateChatTurn(sampleTenant, sampleDocs, conv, 'What is the Core Membership price?');
  assert.equal(turn1.evidenceState, 'SUPPORTED');
  assert.equal(turn1.answer.includes('$29'), true);

  const turnUnk = orchestrateChatTurn(sampleTenant, sampleDocs, conv, 'Do you sell spacecraft insurance?');
  assert.equal(turnUnk.evidenceState, 'UNKNOWN');

  const groundFail = validateGroundingClaim(
    'Core Membership costs $12 per month.',
    sampleDocs[0].chunks[0],
    'SUPPORTED',
    sampleTenant.fallbackAnswer
  );
  assert.equal(groundFail.isGrounded, false);
});
