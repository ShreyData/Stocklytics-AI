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
  ArrowRight,
  LineChart,
  Sparkles,
  Store,
  Activity,
  ChevronRight,
} from 'lucide-react';
import { useTheme } from 'next-themes';
import { useAuth } from './auth-provider';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Input } from './ui/input';
import { getErrorMessage } from '@/lib/errors';
import { getFrontendRuntimeMode } from '@/lib/runtime';
import { EvaluatorDemoLoginNote } from './evaluator-demo-login-note';

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
  const isMockMode = authMode === 'mock';
  const isLocalPreview = runtimeMode === 'mock_api';
  const title = isLocalPreview ? 'Local Preview Mode' : isMockMode ? 'Backend Stub Sign In' : 'Welcome back';
  const subtitle = isLocalPreview
    ? 'Explore the workspace with shared preview data and zero setup.'
    : isMockMode
      ? 'The app is connected to the real backend, using local stub auth until Firebase web auth is fully configured.'
      : 'Sign in to access your retail operations workspace.';

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
    <div className="relative min-h-screen overflow-hidden bg-[radial-gradient(circle_at_top_left,_rgba(245,158,11,0.14),_transparent_24%),radial-gradient(circle_at_bottom_right,_rgba(14,165,233,0.14),_transparent_26%),linear-gradient(135deg,_#0b0b0c_0%,_#121315_50%,_#151516_100%)] text-white">
      <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.03)_1px,transparent_1px)] bg-[size:88px_88px] opacity-25" />
      <div className="absolute left-[10%] top-[12%] h-28 w-28 rounded-full bg-amber-400/10 blur-3xl" />
      <div className="absolute bottom-[10%] right-[12%] h-36 w-36 rounded-full bg-sky-400/10 blur-3xl" />
      <div className="relative mx-auto flex min-h-screen max-w-7xl items-center px-6 py-10 lg:px-10">
        <div className="grid w-full gap-10 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
          <section className="max-w-xl space-y-7">
            <div className="inline-flex items-center gap-3 rounded-full border border-white/12 bg-white/[0.06] px-4 py-2 backdrop-blur">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-white text-black">
                <Store className="h-4 w-4" />
              </div>
              <div>
                <p className="text-sm font-medium text-white">Stocklytics AI</p>
                <p className="text-xs tracking-[0.18em] text-white/45 uppercase">Retail Ops Platform</p>
              </div>
            </div>
            <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/8 px-4 py-1.5 text-sm text-white/80 backdrop-blur">
              <Sparkles className="h-4 w-4 text-amber-300" />
              Retail intelligence for fast-moving stores
            </div>
            <div className="space-y-4">
              <h1 className="max-w-lg text-4xl font-semibold tracking-tight text-white sm:text-5xl">
                Run your store from one clear, modern workspace.
              </h1>
              <p className="max-w-lg text-lg leading-8 text-white/68">
                Inventory, billing, alerts, analytics, and grounded AI guidance designed for everyday retail operations.
              </p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="rounded-3xl border border-white/10 bg-white/[0.05] p-5 backdrop-blur-sm">
                <LineChart className="mb-4 h-5 w-5 text-emerald-300" />
                <p className="text-sm font-medium text-white">Live business pulse</p>
                <p className="mt-2 text-sm leading-6 text-white/62">Track sales, stock health, and top movers without switching tools.</p>
              </div>
              <div className="rounded-3xl border border-white/10 bg-white/[0.05] p-5 backdrop-blur-sm">
                <ShieldCheck className="mb-4 h-5 w-5 text-amber-300" />
                <p className="text-sm font-medium text-white">Secure operator access</p>
                <p className="mt-2 text-sm leading-6 text-white/62">Production-ready sign-in with role-scoped backend verification.</p>
              </div>
            </div>
          </section>

          <Card className="mx-auto w-full max-w-md rounded-[2rem] border border-white/10 bg-[#171717]/88 py-0 text-white shadow-2xl shadow-black/30 ring-1 ring-white/10 backdrop-blur-xl">
            <CardHeader className="space-y-4 px-7 pt-7">
              <div className="flex items-center justify-between gap-4">
                <div className="inline-flex h-12 w-12 items-center justify-center rounded-2xl border border-white/10 bg-white/8">
                  {isMockMode ? <Wrench className="h-5 w-5 text-amber-300" /> : <ShieldCheck className="h-5 w-5 text-emerald-300" />}
                </div>
                <div className="inline-flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1 text-xs font-medium text-emerald-200">
                  <span className="h-2 w-2 rounded-full bg-emerald-300" />
                  Secure workspace
                </div>
              </div>
              <div className="space-y-2">
                <CardTitle className="text-2xl font-semibold text-white">{title}</CardTitle>
                <CardDescription className="max-w-md text-[15px] leading-7 text-white/65">
                  {subtitle}
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent className="space-y-6 px-7 pb-7">
              <EvaluatorDemoLoginNote />

              <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="text-sm font-medium text-white/90">Workspace access</p>
                    <p className="mt-1 text-sm text-white/55">
                      {isLocalPreview
                        ? 'Preview dataset with zero setup'
                        : isMockMode
                          ? 'Real backend with temporary stub auth'
                          : 'Production Firebase authentication'}
                    </p>
                  </div>
                  <span className="rounded-full border border-white/10 bg-white/8 px-3 py-1 text-xs uppercase tracking-[0.18em] text-white/65">
                    {isLocalPreview ? 'preview' : isMockMode ? 'stub' : 'secure'}
                  </span>
                </div>
              </div>

              <form onSubmit={handleLogin} className="space-y-4">
                {isMockMode ? (
                  <div className="rounded-2xl border border-dashed border-white/15 bg-white/[0.03] p-4 text-sm leading-6 text-white/65">
                    {isLocalPreview
                      ? 'Mock mode uses the shared demo store profile and does not require a live backend or Firebase login.'
                      : 'Backend-connected local mode uses the shared dev-token auth stub from the FastAPI backend.'}
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="space-y-2">
                      <label className="text-sm font-medium text-white/80">Work email</label>
                      <Input
                        value={email}
                        onChange={(event) => setEmail(event.target.value)}
                        placeholder="you@company.com"
                        type="email"
                        autoComplete="email"
                        className="h-12 rounded-2xl border-white/10 bg-white/[0.05] px-4 text-base text-white placeholder:text-white/35"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-sm font-medium text-white/80">Password</label>
                      <Input
                        value={password}
                        onChange={(event) => setPassword(event.target.value)}
                        placeholder="Enter your password"
                        type="password"
                        autoComplete="current-password"
                        className="h-12 rounded-2xl border-white/10 bg-white/[0.05] px-4 text-base text-white placeholder:text-white/35"
                      />
                    </div>
                  </div>
                )}
                {error ? (
                  <div className="rounded-2xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">
                    {error}
                  </div>
                ) : null}
                <Button
                  type="submit"
                  className="h-12 w-full rounded-2xl bg-white text-base font-semibold text-black hover:bg-white/90"
                  disabled={isLoading || (authMode === 'firebase' && (!email.trim() || !password.trim()))}
                >
                  {isLoading
                    ? 'Signing in...'
                    : isMockMode
                      ? isLocalPreview
                        ? 'Open preview workspace'
                        : 'Use backend stub session'
                      : 'Enter workspace'}
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
                {!isMockMode ? (
                  <p className="text-center text-xs leading-6 text-white/45">
                    Protected by Firebase Authentication and backend role checks.
                  </p>
                ) : null}
              </form>
            </CardContent>
          </Card>
        </div>
      </div>
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
      <aside className="flex w-68 flex-col border-r border-border/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.98)_0%,rgba(248,248,248,0.94)_100%)] dark:bg-[linear-gradient(180deg,rgba(22,22,23,0.98)_0%,rgba(15,15,16,0.98)_100%)]">
        <div className="border-b border-border/60 p-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-sm">
              <Store className="h-4 w-4" />
            </div>
            <div>
              <h1 className="text-base font-semibold tracking-tight">Stocklytics AI</h1>
              <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Retail command center</p>
            </div>
          </div>

          <div className="mt-4 rounded-2xl border border-border/70 bg-background/80 p-3.5 shadow-sm">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Workspace</p>
                <p className="mt-1.5 text-sm font-semibold">{storeId}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Signed in as {user?.email || user?.user_id || 'team member'}
                </p>
              </div>
              <div className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.18em] text-emerald-600 dark:text-emerald-400">
                Live
              </div>
            </div>

            <div className="mt-3 flex gap-2">
              <div className="min-w-0 flex-1 rounded-xl bg-muted/60 px-3 py-2">
                <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Role</p>
                <p className="mt-1 text-sm font-medium capitalize">{user?.role || 'staff'}</p>
              </div>
              <div className="min-w-0 flex-1 rounded-xl bg-muted/60 px-3 py-2">
                <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Mode</p>
                <p className="mt-1 truncate text-sm font-medium capitalize">
                  {runtimeMode === 'mock_api' ? 'Mock API' : runtimeMode === 'backend_stub_auth' ? 'Stub Auth' : authMode}
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="px-4 pt-3">
          <div className="flex items-center gap-2 rounded-2xl border border-border/70 bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
            <Activity className="h-4 w-4 text-sky-500" />
            Monitor store performance in real time
          </div>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto px-4 py-3">
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.name}
                href={item.href}
                className={cn(
                  'flex items-center gap-3 rounded-2xl px-3.5 py-3 text-sm font-medium transition-all',
                  isActive
                    ? 'bg-primary text-primary-foreground shadow-sm'
                    : 'text-muted-foreground hover:bg-accent/80 hover:text-accent-foreground'
                )}
              >
                <div
                  className={cn(
                    'flex h-9 w-9 items-center justify-center rounded-xl border transition-colors',
                    isActive
                      ? 'border-primary-foreground/15 bg-primary-foreground/10'
                      : 'border-border/70 bg-background/70'
                  )}
                >
                  <item.icon className="h-4 w-4" />
                </div>
                <span className="flex-1">{item.name}</span>
                <ChevronRight
                  className={cn(
                    'h-4 w-4 transition-opacity',
                    isActive ? 'opacity-100' : 'opacity-0'
                  )}
                />
              </Link>
            );
          })}
        </nav>

        <div className="space-y-2 border-t border-border/60 p-4">
          <Button
            variant="outline"
            className="h-11 w-full justify-start rounded-2xl bg-background/80"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          >
            {theme === 'dark' ? <Sun className="w-4 h-4 mr-2" /> : <Moon className="w-4 h-4 mr-2" />}
            Toggle Theme
          </Button>
          <Button variant="ghost" className="h-11 w-full justify-start rounded-2xl text-destructive" onClick={logout}>
            <LogOut className="w-4 h-4 mr-2" />
            Logout
          </Button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto bg-background">
        <div className="border-b border-border/60 bg-background/85 px-8 py-5 backdrop-blur">
          <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Operations workspace</p>
              <h2 className="mt-1 text-2xl font-semibold tracking-tight">Store intelligence overview</h2>
            </div>
            <div className="hidden rounded-2xl border border-border/70 bg-muted/40 px-4 py-3 text-sm text-muted-foreground md:block">
              {user?.role === 'admin' ? 'Admin controls enabled' : 'Staff workspace active'}
            </div>
          </div>
        </div>
        <div className="mx-auto max-w-7xl p-8">{children}</div>
      </main>
    </div>
  );
}
