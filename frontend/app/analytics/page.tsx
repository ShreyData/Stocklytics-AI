'use client';

import { useEffect, useState } from 'react';
import { AppLayout } from '@/components/app-layout';
import { apiService } from '@/lib/api-service';
import { useAuth } from '@/components/auth-provider';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { FreshnessBadge } from '@/components/freshness-badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

export default function Analytics() {
  const { storeId } = useAuth();
  const [lastUpdated, setLastUpdated] = useState<string>('');
  const [freshness, setFreshness] = useState<'fresh' | 'delayed' | 'stale'>('fresh');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchAnalytics = async () => {
      try {
        const res = await apiService.getDashboardSummary(storeId);
        setLastUpdated(res.analytics_last_updated_at);
        setFreshness(res.freshness_status);
      } catch (error) {
        console.error('Failed to fetch analytics', error);
      } finally {
        setLoading(false);
      }
    };
    fetchAnalytics();
  }, [storeId]);

  return (
    <AppLayout>
      <div className="space-y-8">
        <div className="flex items-center justify-between">
          <h1 className="text-3xl font-bold tracking-tight">Analytics</h1>
          {lastUpdated && (
            <FreshnessBadge lastUpdatedAt={lastUpdated} status={freshness} />
          )}
        </div>

        {loading ? (
          <div className="text-center py-12 text-muted-foreground">Loading analytics...</div>
        ) : (
          <Tabs defaultValue="sales" className="w-full">
            <TabsList>
              <TabsTrigger value="sales">Sales Trends</TabsTrigger>
              <TabsTrigger value="products">Product Performance</TabsTrigger>
              <TabsTrigger value="customers">Customer Insights</TabsTrigger>
            </TabsList>
            <TabsContent value="sales" className="mt-6">
              <Card>
                <CardHeader>
                  <CardTitle>Sales Trends</CardTitle>
                </CardHeader>
                <CardContent className="h-[400px] flex items-center justify-center text-muted-foreground">
                  {/* Placeholder for actual chart */}
                  Chart visualization would go here.
                </CardContent>
              </Card>
            </TabsContent>
            <TabsContent value="products" className="mt-6">
              <Card>
                <CardHeader>
                  <CardTitle>Product Performance</CardTitle>
                </CardHeader>
                <CardContent className="h-[400px] flex items-center justify-center text-muted-foreground">
                  Chart visualization would go here.
                </CardContent>
              </Card>
            </TabsContent>
            <TabsContent value="customers" className="mt-6">
              <Card>
                <CardHeader>
                  <CardTitle>Customer Insights</CardTitle>
                </CardHeader>
                <CardContent className="h-[400px] flex items-center justify-center text-muted-foreground">
                  Chart visualization would go here.
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        )}
      </div>
    </AppLayout>
  );
}
