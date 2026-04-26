'use client';

import { useEffect, useState } from 'react';
import { AppLayout } from '@/components/app-layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { apiService } from '@/lib/api-service';
import { useAuth } from '@/components/auth-provider';
import { AlertsSummary, DashboardSummary } from '@/lib/types';
import { FreshnessBadge } from '@/components/freshness-badge';
import { DollarSign, ShoppingCart, Bell, PackageX, CheckCircle2, ArrowRight } from 'lucide-react';
import { toast } from 'sonner';
import { getErrorMessage } from '@/lib/errors';
import Link from 'next/link';

export default function Dashboard() {
  const { storeId } = useAuth();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [alertSummary, setAlertSummary] = useState<AlertsSummary | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string>('');
  const [freshness, setFreshness] = useState<'fresh' | 'delayed' | 'stale'>('fresh');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!storeId) return;

    const fetchDashboard = async () => {
      setLoading(true);
      try {
        const [dashboardRes, alertsRes] = await Promise.all([
          apiService.getDashboardSummary(storeId),
          apiService.getAlertsSummary(storeId),
        ]);

        setSummary(dashboardRes.summary || null);
        setAlertSummary(alertsRes.summary || null);
        setLastUpdated(dashboardRes.analytics_last_updated_at);
        setFreshness(dashboardRes.freshness_status);
      } catch (error) {
        toast.error(getErrorMessage(error, 'Failed to load dashboard.'));
      } finally {
        setLoading(false);
      }
    };

    fetchDashboard();
  }, [storeId]);

  if (loading) {
    return (
      <AppLayout>
        <div className="flex items-center justify-center h-full">
          <div className="animate-pulse text-muted-foreground font-mono">Loading Dashboard...</div>
        </div>
      </AppLayout>
    );
  }

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
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Today&apos;s Sales</CardTitle>
              <DollarSign className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">${(summary?.today_sales || 0).toLocaleString()}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Transactions</CardTitle>
              <ShoppingCart className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{summary?.today_transactions || 0}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Active Alerts</CardTitle>
              <Bell className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-destructive">{summary?.active_alert_count || 0}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Low Stock Items</CardTitle>
              <PackageX className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-yellow-500">{summary?.low_stock_count || 0}</div>
            </CardContent>
          </Card>
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
              <Link href="/inventory?low_stock_only=true">
                <Button variant="outline" className="w-full justify-between">
                  Open Low Stock Products
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
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
              <Link href="/alerts">
                <Button variant="outline" className="w-full justify-between">
                  Open Active Alerts
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
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
              <Link href="/ai-chat">
                <Button variant="outline" className="w-full justify-between">
                  Open AI Chat
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
            </CardContent>
          </Card>
        </div>
      </div>
    </AppLayout>
  );
}
