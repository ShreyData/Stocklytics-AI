'use client';

import { useEffect, useRef, useState } from 'react';
import { v4 as uuidv4 } from 'uuid';
import {
  AlertTriangle,
  BarChart3,
  Bot,
  CheckCircle2,
  Package,
  RefreshCw,
  Search,
  Send,
  Sparkles,
  User,
  XCircle,
} from 'lucide-react';
import { AppLayout } from '@/components/app-layout';
import { FreshnessBadge } from '@/components/freshness-badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/components/auth-provider';
import { AI_CHAT_SESSIONS_KEY } from '@/lib/auth-storage';
import { apiService } from '@/lib/api-service';
import { Alert, Customer, DashboardSummary, FreshnessStatus, Product } from '@/lib/types';
import { getErrorMessage, normalizeApiError } from '@/lib/errors';
import { cn } from '@/lib/utils';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  grounding?: {
    analytics_used?: boolean;
    alerts_used?: string[];
    inventory_products_used?: string[];
    rag_products_used?: string[];
  };
  freshness?: { lastUpdatedAt: string; status: FreshnessStatus };
}

type SyncState = 'idle' | 'syncing' | 'success' | 'error';

const LEGACY_FRESHNESS_PATTERNS = [
  /\s*(?:⚠️\s*)?Note:\s*Analytics data may be slightly behind real-time activity\s*\(freshness status:\s*delayed\)\.?/gi,
  /\s*(?:⚠️\s*)?Note:\s*Analytics data is not current\s*\(freshness status:\s*stale\)\.\s*This answer uses the latest available snapshot and may miss recent changes\.?/gi,
  /\s*(?:⚠️\s*)?Note:\s*Analytics data is slightly delayed, so this answer uses the latest available snapshot\.?/gi,
  /\s*Please note this data is stale, last updated on\s+[^\n.]+\.?/gi,
  /\s*Freshness status:\s*(?:delayed|stale)\.?/gi,
];

function makeSessionId() { return `chat_${uuidv4()}`; }

function readSavedSessions(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(AI_CHAT_SESSIONS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === 'string') : [];
  } catch { return []; }
}

function persistSessions(ids: string[]) {
  if (typeof window !== 'undefined') localStorage.setItem(AI_CHAT_SESSIONS_KEY, JSON.stringify(ids));
}

function isMissingChatSessionError(error: unknown) {
  const n = normalizeApiError(error);
  return n.code === 'CHAT_SESSION_NOT_FOUND' || n.code === 'NOT_FOUND' || n.status === 404;
}

function isLowStock(p: Product) { return p.status === 'ACTIVE' && p.quantity_on_hand <= p.reorder_threshold; }

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(amount);
}

function includesAny(text: string, terms: string[]) { return terms.some((t) => text.includes(t)); }

function fallbackUsesAnalytics(query: string) {
  return includesAny(query.toLowerCase(), ['sale', 'sales', 'revenue', 'transaction', 'transactions', 'customer', 'customers', 'buyer', 'buyers']);
}

function normalizeAssistantText(text: string) {
  return LEGACY_FRESHNESS_PATTERNS
    .reduce((s, p) => s.replace(p, ''), text)
    .replace(/\n{3,}/g, '\n\n').replace(/[ \t]{2,}/g, ' ').trim();
}

function buildFallbackAnswer(query: string, summary: DashboardSummary | null, products: Product[], alerts: Alert[], customers: Customer[]) {
  const lowStock = products.filter(isLowStock).slice(0, 5);
  const active = alerts.filter((a) => a.status === 'ACTIVE');
  const top = [...customers].sort((a, b) => b.total_spend - a.total_spend).slice(0, 3);
  const lines: string[] = [];
  const q = query.toLowerCase();
  if (includesAny(q, ['sale', 'revenue', 'today', 'transaction'])) {
    lines.push(summary ? `Today's sales are ${formatCurrency(summary.today_sales)} across ${summary.today_transactions} transactions.` : "I couldn't confirm today's sales from the available snapshot.");
    if (summary?.top_selling_product) lines.push(`${summary.top_selling_product} is the current top seller.`);
  }
  if (includesAny(q, ['stock', 'inventory', 'product'])) {
    if (lowStock.length > 0) {
      lines.push(`${lowStock.length} low stock products need attention. Most urgent: ${lowStock[0].name} (${lowStock[0].quantity_on_hand} left, threshold ${lowStock[0].reorder_threshold}).`);
    } else {
      lines.push('No active low stock products found in current inventory data.');
    }
  }
  if (includesAny(q, ['alert', 'risk', 'issue'])) lines.push(`There are ${active.length} active alerts right now.`);
  if (includesAny(q, ['customer', 'buyer', 'loyal'])) {
    if (top.length > 0) lines.push(`Top customers: ${top.map((c) => `${c.name} (${formatCurrency(c.total_spend)})`).join(', ')}.`);
  }
  if (lines.length === 0 && summary) lines.push(`Store summary: ${formatCurrency(summary.today_sales)} in sales, ${summary.today_transactions} transactions today.`);
  lines.push('I answered from working store APIs because the AI service is currently unavailable.');
  return lines.join(' ');
}

async function buildAssistantFallback(storeId: string, query: string): Promise<Message> {
  const [dashboardResult, productsResult, alertsResult, customersResult] = await Promise.allSettled([
    apiService.getLiveDashboardSummary(storeId).catch(() => apiService.getDashboardSummary(storeId)),
    apiService.getProducts(storeId),
    apiService.getAlerts(storeId, { status: 'ACTIVE' }),
    apiService.getCustomers(),
  ]);
  const summary = dashboardResult.status === 'fulfilled' ? dashboardResult.value.summary ?? null : null;
  const freshness = dashboardResult.status === 'fulfilled'
    ? { lastUpdatedAt: dashboardResult.value.analytics_last_updated_at, status: dashboardResult.value.freshness_status }
    : { lastUpdatedAt: new Date().toISOString(), status: 'fresh' as FreshnessStatus };
  const products = productsResult.status === 'fulfilled' ? productsResult.value.items : [];
  const alerts = alertsResult.status === 'fulfilled' ? alertsResult.value.items : [];
  const customers = customersResult.status === 'fulfilled' ? customersResult.value.items : [];
  return {
    id: `fallback-${Date.now()}`,
    role: 'assistant',
    text: buildFallbackAnswer(query, summary, products, alerts, customers),
    grounding: {
      analytics_used: summary !== null && fallbackUsesAnalytics(query),
      alerts_used: alerts.slice(0, 5).map((a) => a.alert_id),
      inventory_products_used: products.filter(isLowStock).slice(0, 5).map((p) => p.product_id),
    },
    freshness,
  };
}

function GroundingChips({ grounding }: { grounding: Message['grounding'] }) {
  if (!grounding) return null;
  const hasRag = (grounding.rag_products_used?.length ?? 0) > 0;
  const hasInventory = (grounding.inventory_products_used?.length ?? 0) > 0;
  const hasAlerts = (grounding.alerts_used?.length ?? 0) > 0;
  if (!grounding.analytics_used && !hasAlerts && !hasInventory && !hasRag) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {grounding.analytics_used && (
        <span className="inline-flex items-center gap-1 rounded-full bg-blue-500/10 px-2 py-0.5 text-xs text-blue-600 dark:text-blue-400">
          <BarChart3 className="h-3 w-3" /> Analytics
        </span>
      )}
      {hasAlerts && (
        <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-xs text-amber-600 dark:text-amber-400">
          <AlertTriangle className="h-3 w-3" /> {grounding.alerts_used!.length} Alert{grounding.alerts_used!.length !== 1 ? 's' : ''}
        </span>
      )}
      {hasInventory && (
        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-600 dark:text-emerald-400">
          <Package className="h-3 w-3" /> {grounding.inventory_products_used!.length} Product{grounding.inventory_products_used!.length !== 1 ? 's' : ''}
        </span>
      )}
      {hasRag && (
        <span className="inline-flex items-center gap-1 rounded-full bg-purple-500/10 px-2 py-0.5 text-xs text-purple-600 dark:text-purple-400">
          <Search className="h-3 w-3" /> {grounding.rag_products_used!.length} Vector Match{grounding.rag_products_used!.length !== 1 ? 'es' : ''}
        </span>
      )}
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex max-w-[80%] gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted">
        <Bot className="h-4 w-4 text-muted-foreground" />
      </div>
      <div className="flex items-center gap-1.5 rounded-2xl rounded-tl-sm border border-border bg-muted/50 px-4 py-3">
        <span className="h-2 w-2 animate-bounce rounded-full bg-primary [animation-delay:0ms]" />
        <span className="h-2 w-2 animate-bounce rounded-full bg-primary [animation-delay:150ms]" />
        <span className="h-2 w-2 animate-bounce rounded-full bg-primary [animation-delay:300ms]" />
      </div>
    </div>
  );
}

export default function AIChat() {
  const { storeId } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionIds, setSessionIds] = useState<string[]>([]);
  const [chatSessionId, setChatSessionId] = useState('');
  const [historyLoading, setHistoryLoading] = useState(false);
  const [syncState, setSyncState] = useState<SyncState>('idle');
  const [syncResult, setSyncResult] = useState<{ embedded: number; product_count: number } | null>(null);
  const [syncError, setSyncError] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const localOnlyRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    const existing = readSavedSessions();
    if (existing.length > 0) { setSessionIds(existing); setChatSessionId(existing[0]); return; }
    const id = makeSessionId();
    localOnlyRef.current.add(id);
    setSessionIds([id]); setChatSessionId(id); persistSessions([id]);
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  useEffect(() => {
    if (!chatSessionId) return;
    if (localOnlyRef.current.has(chatSessionId)) { setMessages([]); setHistoryLoading(false); return; }
    async function load() {
      setHistoryLoading(true);
      try {
        const res = await apiService.getChatSessionHistory(chatSessionId);
        setMessages(res.messages.map((m, i) => ({
          id: `${chatSessionId}-${i}`,
          role: m.role,
          text: m.role === 'assistant' ? normalizeAssistantText(m.text) : m.text,
        })));
      } catch (err) {
        if (isMissingChatSessionError(err)) {
          setMessages([]); removeSession(chatSessionId);
          const remaining = readSavedSessions().filter((id) => id !== chatSessionId);
          if (remaining.length > 0) {
            setChatSessionId((cur) => cur === chatSessionId ? remaining[0] : cur);
          } else {
            const next = makeSessionId();
            localOnlyRef.current.add(next);
            persistSessions([next]); setSessionIds([next]);
            setChatSessionId((cur) => cur === chatSessionId ? next : cur);
          }
        } else {
          setMessages([{ id: `${chatSessionId}-err`, role: 'assistant', text: getErrorMessage(err, 'Failed to load chat history.') }]);
        }
      } finally { setHistoryLoading(false); }
    }
    void load();
  }, [chatSessionId]);

  function ensureRegistered(id: string) {
    setSessionIds((prev) => { if (prev.includes(id)) return prev; const next = [id, ...prev]; persistSessions(next); return next; });
  }
  function removeSession(id: string) {
    setSessionIds((prev) => { const next = prev.filter((s) => s !== id); persistSessions(next); return next; });
  }
  function handleNewSession() {
    const id = makeSessionId();
    localOnlyRef.current.add(id); ensureRegistered(id); setChatSessionId(id); setMessages([]);
  }

  async function handleSend() {
    if (!input.trim() || !storeId || !chatSessionId || isLoading) return;
    ensureRegistered(chatSessionId);
    const userMsg: Message = { id: `${chatSessionId}-${Date.now()}-user`, role: 'user', text: input.trim() };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);
    try {
      const res = await apiService.askAI(storeId, chatSessionId, userMsg.text);
      localOnlyRef.current.delete(chatSessionId);
      localOnlyRef.current.delete(res.chat_session_id);
      ensureRegistered(res.chat_session_id);
      setMessages((prev) => [...prev, {
        id: `${res.request_id}-assistant`,
        role: 'assistant',
        text: normalizeAssistantText(res.answer),
        grounding: res.grounding,
        freshness: { lastUpdatedAt: res.analytics_last_updated_at, status: res.freshness_status },
      }]);
    } catch (err) {
      try {
        const fb = await buildAssistantFallback(storeId, userMsg.text);
        setMessages((prev) => [...prev, fb]);
      } catch (fbErr) {
        setMessages((prev) => [...prev, { id: `${chatSessionId}-${Date.now()}-err`, role: 'assistant', text: getErrorMessage(fbErr, getErrorMessage(err, 'Sorry, an error occurred.')) }]);
      }
    } finally { setIsLoading(false); }
  }

  async function handleSyncEmbeddings() {
    if (!storeId || syncState === 'syncing') return;
    setSyncState('syncing'); setSyncResult(null); setSyncError('');
    try {
      const res = await apiService.syncEmbeddings(storeId);
      setSyncResult(res); setSyncState('success');
      setTimeout(() => setSyncState('idle'), 5000);
    } catch (err) {
      setSyncError(getErrorMessage(err, 'Embedding sync failed.')); setSyncState('error');
      setTimeout(() => setSyncState('idle'), 5000);
    }
  }

  const quickPrompts = [
    "What needs attention right now?",
    "Show current inventory status",
    "Any new products added recently?",
    "Summarize today's sales",
  ];

  return (
    <AppLayout>
      {/* Fixed-height grid — only the messages area scrolls */}
      <div className="grid h-[calc(100vh-4rem)] gap-4 overflow-hidden lg:grid-cols-[260px_1fr]">

        {/* ── Sidebar ── */}
        <Card className="flex flex-col overflow-hidden">
          <CardContent className="flex min-h-0 flex-1 flex-col gap-3 p-3">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold">Sessions</h2>
                <p className="text-xs text-muted-foreground">Chat history</p>
              </div>
              <Button size="sm" variant="outline" className="h-7 text-xs" onClick={handleNewSession}>
                New
              </Button>
            </div>

            {/* Session list */}
            <div className="min-h-0 flex-1 space-y-1 overflow-y-auto">
              {sessionIds.map((id) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setChatSessionId(id)}
                  className={cn(
                    'w-full truncate rounded-md border px-2.5 py-2 text-left text-xs transition-colors',
                    id === chatSessionId
                      ? 'border-primary bg-primary/10 font-medium text-foreground'
                      : 'border-transparent text-muted-foreground hover:border-border hover:bg-muted/40'
                  )}
                >
                  <span className="block truncate font-mono">{id.slice(0, 20)}…</span>
                </button>
              ))}
            </div>

            {/* ── Sync Embeddings button ── */}
            <div className="border-t border-border pt-3">
              <Button
                size="sm"
                variant="outline"
                className={cn(
                  'w-full gap-2 text-xs transition-colors',
                  syncState === 'success' && 'border-emerald-500 text-emerald-600 hover:bg-emerald-500/10',
                  syncState === 'error' && 'border-red-500 text-red-600 hover:bg-red-500/10',
                )}
                disabled={syncState === 'syncing' || !storeId}
                onClick={handleSyncEmbeddings}
              >
                {syncState === 'syncing' && <RefreshCw className="h-3 w-3 animate-spin" />}
                {syncState === 'success' && <CheckCircle2 className="h-3 w-3" />}
                {syncState === 'error' && <XCircle className="h-3 w-3" />}
                {syncState === 'idle' && <Sparkles className="h-3 w-3" />}
                {syncState === 'syncing' ? 'Updating…' : syncState === 'success' ? 'Updated!' : syncState === 'error' ? 'Failed' : 'Update RAG Context'}
              </Button>

              {syncState === 'success' && syncResult && (
                <p className="mt-1.5 text-center text-xs text-emerald-600 dark:text-emerald-400">
                  {syncResult.embedded} / {syncResult.product_count} products embedded
                </p>
              )}
              {syncState === 'error' && syncError && (
                <p className="mt-1.5 text-center text-xs text-red-500">{syncError}</p>
              )}
              <p className="mt-1.5 text-center text-xs text-muted-foreground">
                Rebuilds the AI vector search index for this store
              </p>
            </div>
          </CardContent>
        </Card>

        {/* ── Main chat column ── */}
        <div className="flex min-h-0 flex-col overflow-hidden">
          {/* Header */}
          <div className="mb-3 flex items-start justify-between gap-4 shrink-0">
            <div>
              <h1 className="text-2xl font-bold tracking-tight">AI Assistant</h1>
              <p className="text-sm text-muted-foreground">
                Ask about stock risks, sales trends, recent products, or next best actions.
              </p>
            </div>
            <Button variant="outline" size="sm" onClick={handleNewSession}>
              New Session
            </Button>
          </div>

          {/* Chat card — takes remaining height */}
          <Card className="flex min-h-0 flex-1 flex-col overflow-hidden">
            {/* Messages */}
            <div ref={messagesContainerRef} className="min-h-0 flex-1 overflow-y-auto p-4 space-y-4">
              {historyLoading ? (
                <div className="flex h-full items-center justify-center">
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <RefreshCw className="h-4 w-4 animate-spin" /> Loading history…
                  </div>
                </div>
              ) : messages.length === 0 ? (
                <div className="flex h-full flex-col items-center justify-center gap-6 text-muted-foreground">
                  <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10">
                    <Bot className="h-7 w-7 text-primary" />
                  </div>
                  <div className="space-y-1 text-center">
                    <p className="font-medium text-foreground">Ask your store copilot</p>
                    <p className="text-sm">Get priorities, stock risks, and sales insights.</p>
                  </div>
                  <div className="grid grid-cols-2 gap-2 w-full max-w-sm">
                    {quickPrompts.map((prompt) => (
                      <button
                        key={prompt}
                        type="button"
                        onClick={() => setInput(prompt)}
                        className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-left text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                      >
                        {prompt}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <>
                  {messages.map((msg) => (
                    <div
                      key={msg.id}
                      className={cn('flex gap-3', msg.role === 'user' ? 'flex-row-reverse' : '')}
                    >
                      <div className={cn(
                        'flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
                        msg.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted'
                      )}>
                        {msg.role === 'user' ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
                      </div>
                      <div className={cn('max-w-[78%] space-y-1.5', msg.role === 'user' && 'items-end')}>
                        <div className={cn(
                          'rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap',
                          msg.role === 'user'
                            ? 'rounded-tr-sm bg-primary text-primary-foreground'
                            : 'rounded-tl-sm border border-border bg-muted/50 text-foreground'
                        )}>
                          {msg.text}
                        </div>
                        {msg.role === 'assistant' && <GroundingChips grounding={msg.grounding} />}
                        {msg.role === 'assistant' && msg.freshness && msg.grounding?.analytics_used && (
                          <FreshnessBadge lastUpdatedAt={msg.freshness.lastUpdatedAt} status={msg.freshness.status} />
                        )}
                      </div>
                    </div>
                  ))}
                  {isLoading && <TypingIndicator />}
                </>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input bar */}
            <div className="shrink-0 border-t border-border bg-card p-3">
              <form
                onSubmit={(e) => { e.preventDefault(); void handleSend(); }}
                className="flex gap-2"
              >
                <Input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Ask what changed, what needs attention, or about a product…"
                  disabled={isLoading}
                  className="flex-1 text-sm"
                />
                <Button
                  type="submit"
                  size="icon"
                  disabled={isLoading || !input.trim() || !storeId || !chatSessionId}
                >
                  <Send className="h-4 w-4" />
                </Button>
              </form>
            </div>
          </Card>
        </div>
      </div>
    </AppLayout>
  );
}
