'use client';

import { useEffect, useState } from 'react';
import { format } from 'date-fns';
import { AlertTriangle } from 'lucide-react';
import { AppLayout } from '@/components/app-layout';
import { AlertActionButtons } from '@/components/alert-action-buttons';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { useAuth } from '@/components/auth-provider';
import { apiService } from '@/lib/api-service';
import { Alert, AlertFilters } from '@/lib/types';
import { getErrorMessage } from '@/lib/errors';
import { toast } from 'sonner';

const defaultFilters: AlertFilters = {
  status: 'ALL',
  alert_type: 'ALL',
  severity: 'ALL',
};

export default function Alerts() {
  const { storeId } = useAuth();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({});
  const [filters, setFilters] = useState<AlertFilters>(defaultFilters);

  useEffect(() => {
    if (!storeId) {
      return;
    }

    async function loadAlerts() {
      setLoading(true);
      try {
        const res = await apiService.getAlerts(storeId, filters);
        setAlerts(res.items);
      } catch (error) {
        toast.error(getErrorMessage(error, 'Failed to load alerts.'));
      } finally {
        setLoading(false);
      }
    }

    void loadAlerts();
  }, [storeId, filters]);

  async function withActionLoading(alertId: string, action: () => Promise<void>) {
    setActionLoading((prev) => ({ ...prev, [alertId]: true }));
    try {
      await action();
      const res = await apiService.getAlerts(storeId, filters);
      setAlerts(res.items);
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to update alert.'));
    } finally {
      setActionLoading((prev) => ({ ...prev, [alertId]: false }));
    }
  }

  async function handleAcknowledge(alertId: string) {
    if (!storeId) {
      return;
    }
    await withActionLoading(alertId, async () => {
      await apiService.acknowledgeAlert(alertId, { store_id: storeId });
      toast.success('Alert acknowledged.');
    });
  }

  async function handleResolve(alertId: string) {
    if (!storeId) {
      return;
    }
    await withActionLoading(alertId, async () => {
      await apiService.resolveAlert(alertId, { store_id: storeId });
      toast.success('Alert resolved.');
    });
  }

  return (
    <AppLayout>
      <div className="space-y-8">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Alerts</h1>
            <p className="text-sm text-muted-foreground">
              Filter by lifecycle state, alert type, and severity while keeping resolved alerts visible in history.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <label className="space-y-2 text-sm">
              <span className="font-medium">Status</span>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm"
                value={filters.status ?? 'ALL'}
                onChange={(event) =>
                  setFilters((prev) => ({ ...prev, status: event.target.value as AlertFilters['status'] }))
                }
              >
                <option value="ALL">All</option>
                <option value="ACTIVE">ACTIVE</option>
                <option value="ACKNOWLEDGED">ACKNOWLEDGED</option>
                <option value="RESOLVED">RESOLVED</option>
              </select>
            </label>
            <label className="space-y-2 text-sm">
              <span className="font-medium">Alert Type</span>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm"
                value={filters.alert_type ?? 'ALL'}
                onChange={(event) =>
                  setFilters((prev) => ({ ...prev, alert_type: event.target.value as AlertFilters['alert_type'] }))
                }
              >
                <option value="ALL">All</option>
                <option value="LOW_STOCK">LOW_STOCK</option>
                <option value="EXPIRY_SOON">EXPIRY_SOON</option>
                <option value="NOT_SELLING">NOT_SELLING</option>
                <option value="HIGH_DEMAND">HIGH_DEMAND</option>
              </select>
            </label>
            <label className="space-y-2 text-sm">
              <span className="font-medium">Severity</span>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm"
                value={filters.severity ?? 'ALL'}
                onChange={(event) =>
                  setFilters((prev) => ({ ...prev, severity: event.target.value as AlertFilters['severity'] }))
                }
              >
                <option value="ALL">All</option>
                <option value="LOW">LOW</option>
                <option value="MEDIUM">MEDIUM</option>
                <option value="HIGH">HIGH</option>
                <option value="CRITICAL">CRITICAL</option>
              </select>
            </label>
          </div>
        </div>

        <div className="flex justify-end">
          <Button variant="outline" onClick={() => setFilters(defaultFilters)}>
            Reset Filters
          </Button>
        </div>

        {loading ? (
          <div className="py-12 text-center text-muted-foreground">Loading alerts...</div>
        ) : alerts.length === 0 ? (
          <div className="py-12 text-center text-muted-foreground">No alerts match the current filters.</div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {alerts.map((alert) => (
              <Card key={alert.alert_id} className="flex flex-col">
                <CardHeader className="space-y-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="h-5 w-5 text-destructive" />
                      <CardTitle className="text-lg">{alert.title}</CardTitle>
                    </div>
                    <Badge variant={alert.status === 'ACTIVE' ? 'destructive' : 'secondary'}>
                      {alert.status}
                    </Badge>
                  </div>
                  <CardDescription className="space-y-1">
                    <div>{alert.alert_type}</div>
                    <div>Severity: {alert.severity}</div>
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex-1 space-y-4">
                  <p className="text-sm">{alert.message}</p>
                  <div className="space-y-2 text-sm text-muted-foreground">
                    <div>Created: {format(new Date(alert.created_at), 'PPp')}</div>
                    <div>Acknowledged: {alert.acknowledged_at ? format(new Date(alert.acknowledged_at), 'PPp') : '—'}</div>
                    <div>Resolved: {alert.resolved_at ? format(new Date(alert.resolved_at), 'PPp') : '—'}</div>
                  </div>
                  {alert.resolution_note ? (
                    <div className="rounded-md border border-border bg-muted/20 p-3 text-sm">
                      <span className="font-medium">Resolution:</span> {alert.resolution_note}
                    </div>
                  ) : null}
                </CardContent>
                <CardFooter className="gap-2 border-t pt-4">
                  <AlertActionButtons
                    alert={alert}
                    isLoading={Boolean(actionLoading[alert.alert_id])}
                    onAcknowledge={() => void handleAcknowledge(alert.alert_id)}
                    onResolve={() => void handleResolve(alert.alert_id)}
                  />
                </CardFooter>
              </Card>
            ))}
          </div>
        )}
      </div>
    </AppLayout>
  );
}
