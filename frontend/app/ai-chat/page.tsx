'use client';

import { useEffect, useRef, useState } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { AlertTriangle, BarChart3, Bot, Package, Send, User } from 'lucide-react';
import { AppLayout } from '@/components/app-layout';
import { FreshnessBadge } from '@/components/freshness-badge';
import { FreshnessNote } from '@/components/freshness-note';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/components/auth-provider';
import { AI_CHAT_SESSIONS_KEY } from '@/lib/auth-storage';
import { apiService } from '@/lib/api-service';
import { FreshnessStatus } from '@/lib/types';
import { getErrorMessage } from '@/lib/errors';
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

export default function AIChat() {
  const { storeId } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionIds, setSessionIds] = useState<string[]>([]);
  const [chatSessionId, setChatSessionId] = useState<string>('');
  const [historyLoading, setHistoryLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const existing = readSavedSessions();
    if (existing.length > 0) {
      setSessionIds(existing);
      setChatSessionId(existing[0]);
      return;
    }

    const nextSessionId = makeSessionId();
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

    async function loadHistory() {
      setHistoryLoading(true);
      try {
        const res = await apiService.getChatSessionHistory(chatSessionId);
        setMessages(
          res.messages.map((message, index) => ({
            id: `${chatSessionId}-${index}`,
            role: message.role,
            text: message.text,
          }))
        );
      } catch (error) {
        const code = typeof error === 'object' && error && 'code' in error ? String(error.code) : '';
        if (code === 'CHAT_SESSION_NOT_FOUND') {
          setMessages([]);
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

  function handleNewSession() {
    const nextSessionId = makeSessionId();
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
      const aiMsg: Message = {
        id: `${res.request_id}-assistant`,
        role: 'assistant',
        text: res.answer,
        grounding: res.grounding,
        freshness: {
          lastUpdatedAt: res.analytics_last_updated_at,
          status: res.freshness_status,
        },
      };
      setMessages((prev) => [...prev, aiMsg]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          id: `${chatSessionId}-${Date.now()}-error`,
          role: 'assistant',
          text: getErrorMessage(error, 'Sorry, I encountered an error while processing your request.'),
        },
      ]);
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
                Ask grounded questions about analytics, alerts, and inventory using the current backend contract.
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
                  <p>How can I help you manage your store today?</p>
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

                      {msg.role === 'assistant' && msg.freshness ? (
                        <div className="space-y-2">
                          <FreshnessBadge
                            lastUpdatedAt={msg.freshness.lastUpdatedAt}
                            status={msg.freshness.status}
                          />
                          <FreshnessNote status={msg.freshness.status} />
                        </div>
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
                  placeholder="Ask about sales, low stock, or alerts..."
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
