'use client';

import { useState, useRef, useEffect } from 'react';
import { AppLayout } from '@/components/app-layout';
import { apiService } from '@/lib/api-service';
import { useAuth } from '@/components/auth-provider';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { FreshnessBadge } from '@/components/freshness-badge';
import { Send, Bot, User, AlertTriangle, Package, BarChart3 } from 'lucide-react';
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
    status: 'fresh' | 'delayed' | 'stale';
  };
}

export default function AIChat() {
  const { storeId } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim()) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      text: input,
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);

    try {
      const res = await apiService.askAI(storeId, userMsg.text);
      const aiMsg: Message = {
        id: res.request_id,
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
      const errorMsg: Message = {
        id: Date.now().toString(),
        role: 'assistant',
        text: 'Sorry, I encountered an error while processing your request.',
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AppLayout>
      <div className="flex flex-col h-[calc(100vh-4rem)] max-w-4xl mx-auto">
        <div className="mb-6">
          <h1 className="text-3xl font-bold tracking-tight">AI Assistant</h1>
          <p className="text-muted-foreground">Ask questions about your store&apos;s performance and inventory.</p>
        </div>

        <Card className="flex-1 flex flex-col overflow-hidden">
          <CardContent className="flex-1 overflow-y-auto p-6 space-y-6">
            {messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-muted-foreground space-y-4">
                <Bot className="w-12 h-12 opacity-20" />
                <p>How can I help you manage your store today?</p>
              </div>
            ) : (
              messages.map((msg) => (
                <div
                  key={msg.id}
                  className={cn(
                    'flex gap-4 max-w-[80%]',
                    msg.role === 'user' ? 'ml-auto flex-row-reverse' : ''
                  )}
                >
                  <div
                    className={cn(
                      'w-8 h-8 rounded-full flex items-center justify-center shrink-0',
                      msg.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted'
                    )}
                  >
                    {msg.role === 'user' ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
                  </div>
                  <div className="space-y-2">
                    <div
                      className={cn(
                        'p-4 rounded-lg',
                        msg.role === 'user'
                          ? 'bg-primary text-primary-foreground'
                          : 'bg-muted/50 border border-border'
                      )}
                    >
                      {msg.text}
                    </div>

                    {/* Grounding Footer */}
                    {msg.role === 'assistant' && msg.grounding && (
                      <div className="flex flex-wrap gap-2 mt-2">
                        {msg.grounding.analytics_used && (
                          <div className="flex items-center gap-1 text-xs text-muted-foreground bg-muted px-2 py-1 rounded">
                            <BarChart3 className="w-3 h-3" /> Analytics
                          </div>
                        )}
                        {msg.grounding.alerts_used && msg.grounding.alerts_used.length > 0 && (
                          <div className="flex items-center gap-1 text-xs text-muted-foreground bg-muted px-2 py-1 rounded">
                            <AlertTriangle className="w-3 h-3" /> {msg.grounding.alerts_used.length} Alerts
                          </div>
                        )}
                        {msg.grounding.inventory_products_used && msg.grounding.inventory_products_used.length > 0 && (
                          <div className="flex items-center gap-1 text-xs text-muted-foreground bg-muted px-2 py-1 rounded">
                            <Package className="w-3 h-3" /> {msg.grounding.inventory_products_used.length} Products
                          </div>
                        )}
                      </div>
                    )}

                    {/* Freshness Warning */}
                    {msg.role === 'assistant' && msg.freshness && msg.freshness.status !== 'fresh' && (
                      <div className="mt-2">
                        <FreshnessBadge
                          lastUpdatedAt={msg.freshness.lastUpdatedAt}
                          status={msg.freshness.status}
                        />
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}
            {isLoading && (
              <div className="flex gap-4 max-w-[80%]">
                <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center shrink-0">
                  <Bot className="w-4 h-4" />
                </div>
                <div className="p-4 rounded-lg bg-muted/50 border border-border flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-primary animate-bounce" />
                  <div className="w-2 h-2 rounded-full bg-primary animate-bounce [animation-delay:0.2s]" />
                  <div className="w-2 h-2 rounded-full bg-primary animate-bounce [animation-delay:0.4s]" />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </CardContent>
          <div className="p-4 border-t border-border bg-card">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSend();
              }}
              className="flex gap-2"
            >
              <Input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask about sales, low stock, or alerts..."
                disabled={isLoading}
                className="flex-1"
              />
              <Button type="submit" disabled={isLoading || !input.trim()}>
                <Send className="w-4 h-4" />
              </Button>
            </form>
          </div>
        </Card>
      </div>
    </AppLayout>
  );
}
