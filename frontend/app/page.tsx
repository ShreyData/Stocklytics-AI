'use client';

import { useEffect, useState } from 'react';
import { AppLayout } from '@/components/app-layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { apiService } from '@/lib/api-service';
import { useAuth } from '@/components/auth-provider';
import { DashboardSummary } from '@/lib/types';
import { FreshnessBadge } from '@/components/freshness-badge';
import { DollarSign, ShoppingCart, Bell, PackageX } from 'lucide-react';

export default function Dashboard() {
  const { storeId } = useAuth();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string>('');
  const [freshness, setFreshness] = useState<'fresh' | 'delayed' | 'stale'>('fresh');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchDashboard = async () => {
      try {
        const res = await apiService.getDashboardSummary(storeId);
        setSummary(res.summary || null);
        setLastUpdated(res.analytics_last_updated_at);
        setFreshness(res.freshness_status);
      } catch (error) {
        console.error('Failed to fetch dashboard', error);
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
          {lastUpdated && (
            <FreshnessBadge lastUpdatedAt={lastUpdated} status={freshness} />
          )}
        </div>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Today&apos;s Sales</CardTitle>
              <DollarSign className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">${summary?.today_sales.toLocaleString()}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Transactions</CardTitle>
              <ShoppingCart className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{summary?.today_transactions}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Active Alerts</CardTitle>
              <Bell className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-destructive">{summary?.active_alert_count}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Low Stock Items</CardTitle>
              <PackageX className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-yellow-500">{summary?.low_stock_count}</div>
            </CardContent>
          </Card>
        </div>
      </div>
    </AppLayout>
  );
}
