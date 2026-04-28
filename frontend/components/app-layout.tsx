'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import {
  LayoutDashboard,
  Package,
  Receipt,
  Users,
  Bell,
  BarChart3,
  MessageSquare,
  Moon,
  Sun,
  LogOut,
  ShieldCheck,
  Wrench,
} from 'lucide-react';
import { useTheme } from 'next-themes';
import { useAuth } from './auth-provider';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Input } from './ui/input';
import { getErrorMessage } from '@/lib/errors';
import { getFrontendRuntimeMode } from '@/lib/runtime';

const navItems = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Inventory', href: '/inventory', icon: Package },
  { name: 'Billing', href: '/billing', icon: Receipt },
  { name: 'Customers', href: '/customers', icon: Users },
  { name: 'Alerts', href: '/alerts', icon: Bell },
  { name: 'Analytics', href: '/analytics', icon: BarChart3 },
  { name: 'AI Assistant', href: '/ai-chat', icon: MessageSquare },
];

function LoginScreen() {
  const { loginWithDevMode, loginWithEmailPassword, authMode, isLoading } = useAuth();
  const runtimeMode = getFrontendRuntimeMode();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleLogin = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');

    try {
      if (authMode === 'mock') {
        await loginWithDevMode();
        return;
      }

      await loginWithEmailPassword(email, password);
    } catch (loginError) {
      setError(getErrorMessage(loginError, 'Login failed.'));
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {authMode === 'mock' ? <Wrench className="h-5 w-5" /> : <ShieldCheck className="h-5 w-5" />}
            {runtimeMode === 'mock_api' ? 'Local Preview Mode' : authMode === 'mock' ? 'Backend Stub Sign In' : 'Sign In'}
          </CardTitle>
          <CardDescription>
            {runtimeMode === 'mock_api'
              ? 'Frontend mock mode is active. Continue with the local demo store and shared mock data.'
              : authMode === 'mock'
                ? 'The frontend is connected to the real backend, using local stub auth (`dev-token`) until Firebase web auth is configured.'
              : 'Sign in with Firebase Auth so the frontend can use the same backend session contracts as production.'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleLogin} className="space-y-4">
            {authMode === 'mock' ? (
              <div className="rounded-md border border-dashed border-border bg-muted/30 p-4 text-sm text-muted-foreground">
                {runtimeMode === 'mock_api'
                  ? 'Mock mode uses the shared local store profile and does not require a live backend or Firebase login.'
                  : 'Backend-connected local mode uses the shared `dev-token` auth stub from the FastAPI backend.'}
              </div>
            ) : (
              <>
                <Input
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="Email"
                  type="email"
                  autoComplete="email"
                />
                <Input
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="Password"
                  type="password"
                  autoComplete="current-password"
                />
              </>
            )}
            {error ? <p className="text-sm text-destructive">{error}</p> : null}
            <Button
              type="submit"
              className="w-full"
              disabled={isLoading || (authMode === 'firebase' && (!email.trim() || !password.trim()))}
            >
              {isLoading
                ? 'Signing in...'
                : authMode === 'mock'
                  ? runtimeMode === 'mock_api'
                    ? 'Open Local Demo'
                    : 'Use Backend Stub Session'
                  : 'Sign In'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

export function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const runtimeMode = getFrontendRuntimeMode();
  const { theme, setTheme } = useTheme();
  const { logout, storeId, user, isAuthenticated, isLoading, authMode } = useAuth();

  if (isLoading && !isAuthenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center text-muted-foreground">
        Validating session...
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginScreen />;
  }

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <aside className="w-64 border-r border-border bg-card flex flex-col">
        <div className="p-6">
          <h1 className="text-2xl font-bold tracking-tighter uppercase">Stocklytics</h1>
          <p className="text-xs text-muted-foreground mt-1 font-mono uppercase tracking-widest">
            Store: {storeId}
          </p>
          <p className="text-xs text-muted-foreground mt-1 font-mono uppercase tracking-widest">
            Role: {user?.role || 'staff'}
          </p>
          <p className="text-xs text-muted-foreground mt-1 font-mono uppercase tracking-widest">
            Mode: {runtimeMode === 'mock_api' ? 'mock api' : runtimeMode === 'backend_stub_auth' ? 'backend stub auth' : authMode}
          </p>
        </div>

        <nav className="flex-1 px-4 space-y-1 overflow-y-auto">
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.name}
                href={item.href}
                className={cn(
                  'flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                )}
              >
                <item.icon className="w-4 h-4" />
                {item.name}
              </Link>
            );
          })}
        </nav>

        <div className="p-4 border-t border-border space-y-2">
          <Button
            variant="outline"
            className="w-full justify-start"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          >
            {theme === 'dark' ? <Sun className="w-4 h-4 mr-2" /> : <Moon className="w-4 h-4 mr-2" />}
            Toggle Theme
          </Button>
          <Button variant="ghost" className="w-full justify-start text-destructive" onClick={logout}>
            <LogOut className="w-4 h-4 mr-2" />
            Logout
          </Button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto bg-background">
        <div className="p-8 max-w-7xl mx-auto">{children}</div>
      </main>
    </div>
  );
}
