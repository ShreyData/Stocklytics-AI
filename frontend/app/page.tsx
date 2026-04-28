'use client';

import { useCallback, useEffect, useState } from 'react';
import { AppLayout } from '@/components/app-layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { apiService } from '@/lib/api-service';
import { useAuth } from '@/components/auth-provider';
import { AlertsSummary, DashboardSummary } from '@/lib/types';
import { FreshnessBadge } from '@/components/freshness-badge';
import { IndianRupee, ShoppingCart, Bell, PackageX, CheckCircle2, ArrowRight } from 'lucide-react';
import { toast } from 'sonner';
import { getErrorMessage } from '@/lib/errors';
import Link from 'next/link';
import { subscribeToDataChanged } from '@/lib/data-events';

const DASHBOARD_REFRESH_INTERVAL_MS = 60000;

export default function Dashboard() {
  const { storeId } = useAuth();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [alertSummary, setAlertSummary] = useState<AlertsSummary | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string>('');
  const [freshness, setFreshness] = useState<'fresh' | 'delayed' | 'stale'>('fresh');
  const [loading, setLoading] = useState(true);

  const fetchDashboard = useCallback(
    async (showLoader = false) => {
      if (!storeId) return;
      if (showLoader) {
        setLoading(true);
      }
      try {
        let nextSummary: DashboardSummary | null = null;
        let nextAlertSummary: AlertsSummary | null = null;
        let nextLastUpdated = '';
        let nextFreshness: 'fresh' | 'delayed' | 'stale' = 'fresh';

        try {
          const dashboardRes = await apiService.getLiveDashboardSummary(storeId);
          nextSummary = dashboardRes.summary || null;
          nextLastUpdated = dashboardRes.analytics_last_updated_at;
          nextFreshness = dashboardRes.freshness_status;
        } catch (error) {
          const fallbackDashboardRes = await apiService.getDashboardSummary(storeId);
          nextSummary = fallbackDashboardRes.summary || null;
          nextLastUpdated = fallbackDashboardRes.analytics_last_updated_at;
          nextFreshness = fallbackDashboardRes.freshness_status;

          const message = getErrorMessage(error, '');
          if (showLoader && message && message !== 'Not Found') {
            toast.error(message);
          }
        }

        try {
          const alertsRes = await apiService.getAlertsSummary(storeId);
          nextAlertSummary = alertsRes.summary || null;
        } catch (error) {
          const alertsRes = await apiService.getAlerts(storeId, { status: 'ALL' });
          const today = new Date().toISOString().slice(0, 10);
          const fallbackItems = alertsRes.items || [];

          nextAlertSummary = {
            active: fallbackItems.filter((alert) => alert.status === 'ACTIVE').length,
            acknowledged: fallbackItems.filter((alert) => alert.status === 'ACKNOWLEDGED').length,
            resolved_today: fallbackItems.filter(
              (alert) => alert.status === 'RESOLVED' && alert.resolved_at?.slice(0, 10) === today
            ).length,
          };

          const message = getErrorMessage(error, '');
          if (showLoader && message && message !== 'Not Found') {
            toast.error(message);
          }
        }

        setSummary(nextSummary);
        setAlertSummary(nextAlertSummary);
        setLastUpdated(nextLastUpdated);
        setFreshness(nextFreshness);
      } catch (error) {
        if (showLoader) {
          const message = getErrorMessage(error, 'Failed to load dashboard.');
          toast.error(message === 'Not Found' ? 'Failed to load dashboard.' : message);
        }
      } finally {
        if (showLoader) {
          setLoading(false);
        }
      }
    },
    [storeId]
  );

  useEffect(() => {
    if (!storeId) return;

    void fetchDashboard(true);
    const unsubscribe = subscribeToDataChanged(() => {
      void fetchDashboard(false);
    });
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void fetchDashboard(false);
      }
    };
    const intervalId = window.setInterval(() => {
      if (document.visibilityState === 'visible') {
        void fetchDashboard(false);
      }
    }, DASHBOARD_REFRESH_INTERVAL_MS);
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      unsubscribe();
      window.clearInterval(intervalId);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [fetchDashboard, storeId]);

  if (loading) {
    return (
      <AppLayout>
        <div className="flex items-center justify-center h-full">
          <div className="animate-pulse text-muted-foreground font-mono">Loading Dashboard...</div>
        </div>
      </AppLayout>
    );
  }

  const statsCards = [
    {
      title: "Today's Sales",
      value: `₹${(summary?.today_sales || 0).toLocaleString()}`,
      icon: IndianRupee,
      valueClassName: 'text-2xl font-bold',
    },
    {
      title: 'Transactions',
      value: summary?.today_transactions || 0,
      icon: ShoppingCart,
      valueClassName: 'text-2xl font-bold',
    },
    {
      title: 'Active Alerts',
      value: summary?.active_alert_count || 0,
      icon: Bell,
      valueClassName: 'text-2xl font-bold text-destructive',
    },
    {
      title: 'Low Stock Items',
      value: summary?.low_stock_count || 0,
      icon: PackageX,
      valueClassName: 'text-2xl font-bold text-yellow-500',
    },
  ];

  return (
    <AppLayout>
      <div className="space-y-8">
        <div className="flex items-center justify-between">
          <h1 className="text-3xl font-bold tracking-tight">Command Center</h1>
          {lastUpdated ? (
            <FreshnessBadge lastUpdatedAt={lastUpdated} status={freshness} />
          ) : null}
        </div>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {statsCards.map((card) => (
            <Card key={card.title}>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">{card.title}</CardTitle>
                <card.icon className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className={card.valueClassName}>{card.value}</div>
              </CardContent>
            </Card>
          ))}
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Alerts Active</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-xl font-bold">{alertSummary?.active || 0}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Alerts Acknowledged</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-xl font-bold">{alertSummary?.acknowledged || 0}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Resolved Today</CardTitle>
            </CardHeader>
            <CardContent className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-green-500" />
              <div className="text-xl font-bold">{alertSummary?.resolved_today || 0}</div>
            </CardContent>
          </Card>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Low Stock Queue</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Review products that need replenishment before the next billing rush.
              </p>
              <Button
                variant="outline"
                className="w-full justify-between"
                nativeButton={false}
                render={<Link href="/inventory?low_stock_only=true" />}
              >
                Open Low Stock Products
                <ArrowRight className="h-4 w-4" />
              </Button>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Alert Workflow</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Triage active alerts and keep resolved alerts visible in history.
              </p>
              <Button
                variant="outline"
                className="w-full justify-between"
                nativeButton={false}
                render={<Link href="/alerts" />}
              >
                Open Active Alerts
                <ArrowRight className="h-4 w-4" />
              </Button>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Grounded AI</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Ask the AI assistant about sales, low stock, and fresh vs stale analytics.
              </p>
              <Button
                variant="outline"
                className="w-full justify-between"
                nativeButton={false}
                render={<Link href="/ai-chat" />}
              >
                Open AI Chat
                <ArrowRight className="h-4 w-4" />
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </AppLayout>
  );
}
