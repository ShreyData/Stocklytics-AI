'use client';

import { useEffect, useRef, useState } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { AlertTriangle, BarChart3, Bot, Package, Send, User } from 'lucide-react';
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
  };
  freshness?: {
    lastUpdatedAt: string;
    status: FreshnessStatus;
  };
}

const LEGACY_FRESHNESS_PATTERNS = [
  /\s*(?:⚠️\s*)?Note:\s*Analytics data may be slightly behind real-time activity\s*\(freshness status:\s*delayed\)\.?/gi,
  /\s*(?:⚠️\s*)?Note:\s*Analytics data is not current\s*\(freshness status:\s*stale\)\.\s*This answer uses the latest available snapshot and may miss recent changes\.?/gi,
  /\s*(?:⚠️\s*)?Note:\s*Analytics data is slightly delayed, so this answer uses the latest available snapshot\.?/gi,
  /\s*Please note this data is stale, last updated on\s+[^\n.]+\.?/gi,
  /\s*Freshness status:\s*(?:delayed|stale)\.?/gi,
];

function makeSessionId() {
  return `chat_${uuidv4()}`;
}

function readSavedSessions() {
  if (typeof window === 'undefined') {
    return [] as string[];
  }
  try {
    const raw = localStorage.getItem(AI_CHAT_SESSIONS_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((value): value is string => typeof value === 'string') : [];
  } catch {
    return [];
  }
}

function persistSessions(sessionIds: string[]) {
  if (typeof window !== 'undefined') {
    localStorage.setItem(AI_CHAT_SESSIONS_KEY, JSON.stringify(sessionIds));
  }
}

function isMissingChatSessionError(error: unknown) {
  const normalized = normalizeApiError(error);
  return (
    normalized.code === 'CHAT_SESSION_NOT_FOUND' ||
    normalized.code === 'NOT_FOUND' ||
    normalized.status === 404
  );
}

function isLowStock(product: Product) {
  return product.status === 'ACTIVE' && product.quantity_on_hand <= product.reorder_threshold;
}

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(amount);
}

function includesAny(text: string, terms: string[]) {
  return terms.some((term) => text.includes(term));
}

function fallbackUsesAnalytics(query: string) {
  const lowered = query.toLowerCase();
  return includesAny(lowered, [
    'sale',
    'sales',
    'revenue',
    'transaction',
    'transactions',
    'customer',
    'customers',
    'buyer',
    'buyers',
  ]);
}

function normalizeAssistantText(text: string) {
  return LEGACY_FRESHNESS_PATTERNS
    .reduce((cleaned, pattern) => cleaned.replace(pattern, ''), text)
    .replace(/\n{3,}/g, '\n\n')
    .replace(/[ \t]{2,}/g, ' ')
    .trim();
}

function buildFallbackAnswer(
  query: string,
  summary: DashboardSummary | null,
  products: Product[],
  alerts: Alert[],
  customers: Customer[]
) {
  const lowStockProducts = products.filter(isLowStock).slice(0, 5);
  const activeAlerts = alerts.filter((alert) => alert.status === 'ACTIVE');
  const topCustomers = [...customers]
    .sort((left, right) => {
      if (right.total_spend !== left.total_spend) {
        return right.total_spend - left.total_spend;
      }
      return right.visit_count - left.visit_count;
    })
    .slice(0, 3);
  const lines: string[] = [];
  const lowered = query.toLowerCase();
  const asksAboutSales = includesAny(lowered, ['sale', 'sales', 'revenue', 'today', 'transaction']);
  const asksAboutStock = includesAny(lowered, ['stock', 'inventory', 'product', 'products']);
  const asksAboutAlerts = includesAny(lowered, ['alert', 'alerts', 'risk', 'issue']);
  const asksAboutCustomers = includesAny(lowered, ['customer', 'customers', 'buyer', 'buyers', 'loyal', 'repeat']);

  if (asksAboutSales) {
    if (summary) {
      lines.push(
        `Today's sales are ${formatCurrency(summary.today_sales)} across ${summary.today_transactions} transactions.`
      );
    } else {
      lines.push("I couldn't confirm today's sales from the currently available analytics snapshot.");
    }
    if (summary?.top_selling_product) {
      lines.push(`${summary.top_selling_product} is the current top-selling product.`);
    }
    if (summary?.low_stock_count) {
      lines.push(`${summary.low_stock_count} products are already at or below their reorder threshold.`);
    }
  }

  if (asksAboutStock) {
    if (lowStockProducts.length > 0) {
      const mostUrgent = lowStockProducts[0];
      lines.push(
        `${lowStockProducts.length} low stock products need attention. Most urgent: ${mostUrgent.name} with ${mostUrgent.quantity_on_hand} units left versus a threshold of ${mostUrgent.reorder_threshold}.`
      );
      lines.push(
        `Priority list: ${lowStockProducts
          .map((product) => `${product.name} (${product.quantity_on_hand} left, threshold ${product.reorder_threshold})`)
          .join(', ')}.`
      );
    } else {
      lines.push('I could not confirm any active low stock products from the current inventory data.');
    }
  }

  if (asksAboutAlerts) {
    lines.push(`There are ${activeAlerts.length} active alerts right now.`);
    if (activeAlerts.length > 0) {
      lines.push(`Most relevant alerts: ${activeAlerts.slice(0, 3).map((alert) => alert.title).join(', ')}.`);
    }
  }

  if (asksAboutCustomers) {
    if (topCustomers.length > 0) {
      lines.push(
        `Top customers by spend are ${topCustomers
          .map((customer) => `${customer.name} (${formatCurrency(customer.total_spend)}, ${customer.visit_count} visits)`)
          .join(', ')}.`
      );
    } else {
      lines.push("I couldn't load customer insights from the currently available data.");
    }
  }

  if (lines.length === 0) {
    if (summary) {
      lines.push(
        `Quick store summary: ${formatCurrency(summary.today_sales)} in sales across ${summary.today_transactions} transactions today.`
      );
    } else {
      lines.push('I am using the latest operational data I could load from the app right now.');
    }
    if (lowStockProducts.length > 0) {
      lines.push(`Low stock focus: ${lowStockProducts.slice(0, 3).map((product) => product.name).join(', ')}.`);
    }
    if (activeAlerts.length > 0) {
      lines.push(`Active alerts: ${activeAlerts.length}.`);
    }
  }

  if (asksAboutStock && lowStockProducts.length > 0) {
    lines.push('Recommended next step: reorder or transfer stock for the first two items before they fall further below threshold.');
  } else if (asksAboutSales && summary) {
    lines.push('Recommended next step: compare this with your low stock list so strong sellers do not run out.');
  } else if (asksAboutCustomers && topCustomers.length > 0) {
    lines.push('Recommended next step: target your top repeat customers with availability updates or bundle offers.');
  } else if (activeAlerts.length > 0) {
    lines.push('Recommended next step: review the active alerts first because they are the clearest operational risks right now.');
  }

  lines.push('I answered from the working store APIs because the AI chat service is currently unavailable.');
  return lines.join(' ');
}

async function buildAssistantFallback(storeId: string, query: string): Promise<Message> {
  const dashboardPromise = apiService
    .getLiveDashboardSummary(storeId)
    .catch(() => apiService.getDashboardSummary(storeId));
  const productsPromise = apiService.getProducts(storeId);
  const alertsPromise = apiService.getAlerts(storeId, { status: 'ACTIVE' });
  const customersPromise = apiService.getCustomers();

  const [dashboardResult, productsResult, alertsResult, customersResult] = await Promise.allSettled([
    dashboardPromise,
    productsPromise,
    alertsPromise,
    customersPromise,
  ]);

  const summary = dashboardResult.status === 'fulfilled' ? dashboardResult.value.summary ?? null : null;
  const freshness =
    dashboardResult.status === 'fulfilled'
      ? {
          lastUpdatedAt: dashboardResult.value.analytics_last_updated_at,
          status: dashboardResult.value.freshness_status,
        }
      : {
          lastUpdatedAt: new Date().toISOString(),
          status: 'fresh' as FreshnessStatus,
        };
  const products = productsResult.status === 'fulfilled' ? productsResult.value.items : [];
  const alerts = alertsResult.status === 'fulfilled' ? alertsResult.value.items : [];
  const customers = customersResult.status === 'fulfilled' ? customersResult.value.items : [];

  return {
    id: `fallback-${Date.now()}`,
    role: 'assistant',
    text: buildFallbackAnswer(query, summary, products, alerts, customers),
    grounding: {
      analytics_used: summary !== null && fallbackUsesAnalytics(query),
      alerts_used: alerts.slice(0, 5).map((alert) => alert.alert_id),
      inventory_products_used: products.filter(isLowStock).slice(0, 5).map((product) => product.product_id),
    },
    freshness,
  };
}

export default function AIChat() {
  const { storeId } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionIds, setSessionIds] = useState<string[]>([]);
  const [chatSessionId, setChatSessionId] = useState<string>('');
  const [historyLoading, setHistoryLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const localOnlySessionIdsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    const existing = readSavedSessions();
    if (existing.length > 0) {
      setSessionIds(existing);
      setChatSessionId(existing[0]);
      return;
    }

    const nextSessionId = makeSessionId();
    localOnlySessionIdsRef.current.add(nextSessionId);
    setSessionIds([nextSessionId]);
    setChatSessionId(nextSessionId);
    persistSessions([nextSessionId]);
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (!chatSessionId) {
      return;
    }

    if (localOnlySessionIdsRef.current.has(chatSessionId)) {
      setMessages([]);
      setHistoryLoading(false);
      return;
    }

    async function loadHistory() {
      setHistoryLoading(true);
      try {
        const res = await apiService.getChatSessionHistory(chatSessionId);
        setMessages(
          res.messages.map((message, index) => ({
            id: `${chatSessionId}-${index}`,
            role: message.role,
            text: message.role === 'assistant' ? normalizeAssistantText(message.text) : message.text,
          }))
        );
      } catch (error) {
        if (isMissingChatSessionError(error)) {
          setMessages([]);
          removeSession(chatSessionId);

          const remainingSessions = readSavedSessions().filter((sessionId) => sessionId !== chatSessionId);
          if (remainingSessions.length > 0) {
            setChatSessionId((currentSessionId) =>
              currentSessionId === chatSessionId ? remainingSessions[0] : currentSessionId
            );
          } else {
            const nextSessionId = makeSessionId();
            localOnlySessionIdsRef.current.add(nextSessionId);
            persistSessions([nextSessionId]);
            setSessionIds([nextSessionId]);
            setChatSessionId((currentSessionId) =>
              currentSessionId === chatSessionId ? nextSessionId : currentSessionId
            );
          }
        } else {
          setMessages([
            {
              id: `${chatSessionId}-error`,
              role: 'assistant',
              text: getErrorMessage(error, 'Failed to load chat session history.'),
            },
          ]);
        }
      } finally {
        setHistoryLoading(false);
      }
    }

    void loadHistory();
  }, [chatSessionId]);

  function ensureSessionRegistered(sessionId: string) {
    setSessionIds((prev) => {
      if (prev.includes(sessionId)) {
        return prev;
      }
      const next = [sessionId, ...prev];
      persistSessions(next);
      return next;
    });
  }

  function removeSession(sessionId: string) {
    setSessionIds((prev) => {
      const next = prev.filter((value) => value !== sessionId);
      persistSessions(next);
      return next;
    });
  }

  function handleNewSession() {
    const nextSessionId = makeSessionId();
    localOnlySessionIdsRef.current.add(nextSessionId);
    ensureSessionRegistered(nextSessionId);
    setChatSessionId(nextSessionId);
    setMessages([]);
  }

  async function handleSend() {
    if (!input.trim() || !storeId || !chatSessionId) {
      return;
    }

    ensureSessionRegistered(chatSessionId);

    const userMsg: Message = {
      id: `${chatSessionId}-${Date.now()}-user`,
      role: 'user',
      text: input.trim(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);

    try {
      const res = await apiService.askAI(storeId, chatSessionId, userMsg.text);
      localOnlySessionIdsRef.current.delete(chatSessionId);
      localOnlySessionIdsRef.current.delete(res.chat_session_id);
      ensureSessionRegistered(res.chat_session_id);
      const aiMsg: Message = {
        id: `${res.request_id}-assistant`,
        role: 'assistant',
        text: normalizeAssistantText(res.answer),
        grounding: res.grounding,
        freshness: {
          lastUpdatedAt: res.analytics_last_updated_at,
          status: res.freshness_status,
        },
      };
      setMessages((prev) => [...prev, aiMsg]);
    } catch (error) {
      try {
        const fallbackMessage = await buildAssistantFallback(storeId, userMsg.text);
        setMessages((prev) => [...prev, fallbackMessage]);
      } catch (fallbackError) {
        setMessages((prev) => [
          ...prev,
          {
            id: `${chatSessionId}-${Date.now()}-error`,
            role: 'assistant',
            text: getErrorMessage(
              fallbackError,
              getErrorMessage(error, 'Sorry, I encountered an error while processing your request.')
            ),
          },
        ]);
      }
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <AppLayout>
      <div className="grid h-[calc(100vh-4rem)] gap-6 lg:grid-cols-[280px_1fr]">
        <Card className="overflow-hidden">
          <CardContent className="flex h-full flex-col gap-4 p-4">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-lg font-semibold">AI Sessions</h1>
                <p className="text-sm text-muted-foreground">Stored chat history from the backend contract.</p>
              </div>
              <Button size="sm" variant="outline" onClick={handleNewSession}>
                New
              </Button>
            </div>

            <div className="space-y-2 overflow-y-auto">
              {sessionIds.map((sessionId) => (
                <button
                  key={sessionId}
                  type="button"
                  onClick={() => setChatSessionId(sessionId)}
                  className={cn(
                    'w-full rounded-md border px-3 py-2 text-left text-sm transition-colors',
                    sessionId === chatSessionId
                      ? 'border-primary bg-primary/10 text-foreground'
                      : 'border-border text-muted-foreground hover:bg-muted/40'
                  )}
                >
                  <div className="font-medium">{sessionId}</div>
                  <div className="text-xs">GET /api/v1/ai/chat/sessions/{'{chat_session_id}'}</div>
                </button>
              ))}
            </div>
          </CardContent>
        </Card>

        <div className="flex flex-col">
          <div className="mb-6 flex items-start justify-between gap-4">
            <div>
              <h1 className="text-3xl font-bold tracking-tight">AI Assistant</h1>
              <p className="text-muted-foreground">
                Use it like a store copilot for priorities, stock risks, recent product additions, and sales follow-up.
              </p>
            </div>
            <Button variant="outline" onClick={handleNewSession}>
              New Session
            </Button>
          </div>

          <Card className="flex flex-1 flex-col overflow-hidden">
            <CardContent className="flex-1 space-y-6 overflow-y-auto p-6">
              {historyLoading ? (
                <div className="text-sm text-muted-foreground">Loading chat history...</div>
              ) : messages.length === 0 ? (
                <div className="flex h-full flex-col items-center justify-center space-y-4 text-muted-foreground">
                  <Bot className="h-12 w-12 opacity-20" />
                  <div className="space-y-2 text-center">
                    <p>Ask for the next best action, not just raw numbers.</p>
                    <p className="text-sm">
                      Try: &quot;What needs attention right now?&quot;, &quot;Tell current inventory status&quot;, or &quot;Tell about new product added in inventory&quot;.
                    </p>
                  </div>
                </div>
              ) : (
                messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={cn('flex max-w-[80%] gap-4', msg.role === 'user' ? 'ml-auto flex-row-reverse' : '')}
                  >
                    <div
                      className={cn(
                        'flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
                        msg.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted'
                      )}
                    >
                      {msg.role === 'user' ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
                    </div>
                    <div className="space-y-2">
                      <div
                        className={cn(
                          'rounded-lg p-4',
                          msg.role === 'user'
                            ? 'bg-primary text-primary-foreground'
                            : 'border border-border bg-muted/50'
                        )}
                      >
                        {msg.text}
                      </div>

                      {msg.role === 'assistant' && msg.grounding ? (
                        <div className="mt-2 flex flex-wrap gap-2">
                          {msg.grounding.analytics_used ? (
                            <div className="flex items-center gap-1 rounded bg-muted px-2 py-1 text-xs text-muted-foreground">
                              <BarChart3 className="h-3 w-3" />
                              Analytics
                            </div>
                          ) : null}
                          {msg.grounding.alerts_used && msg.grounding.alerts_used.length > 0 ? (
                            <div className="flex items-center gap-1 rounded bg-muted px-2 py-1 text-xs text-muted-foreground">
                              <AlertTriangle className="h-3 w-3" />
                              {msg.grounding.alerts_used.length} Alerts
                            </div>
                          ) : null}
                          {msg.grounding.inventory_products_used && msg.grounding.inventory_products_used.length > 0 ? (
                            <div className="flex items-center gap-1 rounded bg-muted px-2 py-1 text-xs text-muted-foreground">
                              <Package className="h-3 w-3" />
                              {msg.grounding.inventory_products_used.length} Products
                            </div>
                          ) : null}
                        </div>
                      ) : null}

                      {msg.role === 'assistant' && msg.freshness && msg.grounding?.analytics_used ? (
                        <FreshnessBadge
                          lastUpdatedAt={msg.freshness.lastUpdatedAt}
                          status={msg.freshness.status}
                        />
                      ) : null}
                    </div>
                  </div>
                ))
              )}
              {isLoading ? (
                <div className="flex max-w-[80%] gap-4">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted">
                    <Bot className="h-4 w-4" />
                  </div>
                  <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/50 p-4">
                    <div className="h-2 w-2 animate-bounce rounded-full bg-primary" />
                    <div className="h-2 w-2 animate-bounce rounded-full bg-primary [animation-delay:0.2s]" />
                    <div className="h-2 w-2 animate-bounce rounded-full bg-primary [animation-delay:0.4s]" />
                  </div>
                </div>
              ) : null}
              <div ref={messagesEndRef} />
            </CardContent>

            <div className="border-t border-border bg-card p-4">
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void handleSend();
                }}
                className="flex gap-2"
              >
                <Input
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  placeholder="Ask what changed, what needs attention, or which new product was added..."
                  disabled={isLoading}
                  className="flex-1"
                />
                <Button type="submit" disabled={isLoading || !input.trim() || !storeId || !chatSessionId}>
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
