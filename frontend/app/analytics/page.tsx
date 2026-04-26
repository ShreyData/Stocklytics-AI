'use client';

import { useEffect, useState } from 'react';
import { AppLayout } from '@/components/app-layout';
import { apiService } from '@/lib/api-service';
import { useAuth } from '@/components/auth-provider';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { FreshnessBadge } from '@/components/freshness-badge';
import { FreshnessNote } from '@/components/freshness-note';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { DashboardSummary, ProductPerformanceItem, SalesTrendPoint, CustomerInsight } from '@/lib/types';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { getErrorMessage } from '@/lib/errors';
import { toast } from 'sonner';

export default function Analytics() {
  const { storeId } = useAuth();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [salesPoints, setSalesPoints] = useState<SalesTrendPoint[]>([]);
  const [productItems, setProductItems] = useState<ProductPerformanceItem[]>([]);
  const [topCustomers, setTopCustomers] = useState<CustomerInsight[]>([]);
  const [lastUpdated, setLastUpdated] = useState<string>('');
  const [freshness, setFreshness] = useState<'fresh' | 'delayed' | 'stale'>('fresh');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!storeId) return;

    const fetchAnalytics = async () => {
      try {
        setLoading(true);
        const [dashboardRes, salesRes, productRes, customerRes] = await Promise.all([
          apiService.getDashboardSummary(storeId),
          apiService.getSalesTrends(storeId),
          apiService.getProductPerformance(storeId),
          apiService.getCustomerInsights(storeId),
        ]);

        setSummary(dashboardRes.summary || null);
        setSalesPoints(salesRes.points || []);
        setProductItems(productRes.items || []);
        setTopCustomers(customerRes.top_customers || []);
        setLastUpdated(dashboardRes.analytics_last_updated_at);
        setFreshness(dashboardRes.freshness_status);
      } catch (error) {
        toast.error(getErrorMessage(error, 'Failed to load analytics.'));
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
        <FreshnessNote status={freshness} />

        {summary ? (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Today&apos;s Sales</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">${summary.today_sales.toLocaleString()}</div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Transactions</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{summary.today_transactions}</div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Top Selling Product</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-lg font-semibold">{summary.top_selling_product || '—'}</div>
              </CardContent>
            </Card>
          </div>
        ) : null}

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
                  <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                    <CardTitle>Sales Trends</CardTitle>
                    {lastUpdated ? <FreshnessBadge lastUpdatedAt={lastUpdated} status={freshness} /> : null}
                  </div>
                </CardHeader>
                <CardContent>
                  <FreshnessNote status={freshness} className="mb-4" />
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Period</TableHead>
                        <TableHead>Sales</TableHead>
                        <TableHead>Transactions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {salesPoints.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={3} className="text-center text-muted-foreground py-8">
                            No trend data available.
                          </TableCell>
                        </TableRow>
                      ) : (
                        salesPoints.map((point) => (
                          <TableRow key={point.label}>
                            <TableCell>{point.label}</TableCell>
                            <TableCell>${point.sales_amount.toLocaleString()}</TableCell>
                            <TableCell>{point.transactions}</TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </TabsContent>
            <TabsContent value="products" className="mt-6">
              <Card>
                <CardHeader>
                  <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                    <CardTitle>Product Performance</CardTitle>
                    {lastUpdated ? <FreshnessBadge lastUpdatedAt={lastUpdated} status={freshness} /> : null}
                  </div>
                </CardHeader>
                <CardContent>
                  <FreshnessNote status={freshness} className="mb-4" />
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Product</TableHead>
                        <TableHead>Quantity Sold</TableHead>
                        <TableHead>Revenue</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {productItems.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={3} className="text-center text-muted-foreground py-8">
                            No product performance data available.
                          </TableCell>
                        </TableRow>
                      ) : (
                        productItems.map((item) => (
                          <TableRow key={item.product_id}>
                            <TableCell>{item.product_name}</TableCell>
                            <TableCell>{item.quantity_sold}</TableCell>
                            <TableCell>${item.revenue.toLocaleString()}</TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </TabsContent>
            <TabsContent value="customers" className="mt-6">
              <Card>
                <CardHeader>
                  <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                    <CardTitle>Customer Insights</CardTitle>
                    {lastUpdated ? <FreshnessBadge lastUpdatedAt={lastUpdated} status={freshness} /> : null}
                  </div>
                </CardHeader>
                <CardContent>
                  <FreshnessNote status={freshness} className="mb-4" />
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Customer</TableHead>
                        <TableHead>Lifetime Spend</TableHead>
                        <TableHead>Visits</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {topCustomers.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={3} className="text-center text-muted-foreground py-8">
                            No customer insight data available.
                          </TableCell>
                        </TableRow>
                      ) : (
                        topCustomers.map((customer) => (
                          <TableRow key={customer.customer_id}>
                            <TableCell>{customer.name}</TableCell>
                            <TableCell>${customer.lifetime_spend.toLocaleString()}</TableCell>
                            <TableCell>{customer.visit_count}</TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        )}
      </div>
    </AppLayout>
  );
}
