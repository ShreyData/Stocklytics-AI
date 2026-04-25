'use client';

import { useCallback, useEffect, useState } from 'react';
import { AppLayout } from '@/components/app-layout';
import { apiService } from '@/lib/api-service';
import { useAuth } from '@/components/auth-provider';
import { Alert } from '@/lib/types';
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { AlertTriangle, CheckCircle2, Clock } from 'lucide-react';
import { format } from 'date-fns';
import { toast } from 'sonner';
import { getErrorMessage } from '@/lib/errors';

export default function Alerts() {
  const { storeId } = useAuth();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({});

  const fetchAlerts = useCallback(async () => {
    if (!storeId) return;
    try {
      setLoading(true);
      const res = await apiService.getAlerts(storeId);
      setAlerts(res.items);
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to load alerts.'));
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  const withActionLoading = async (
    alertId: string,
    action: () => Promise<void>
  ) => {
    setActionLoading((prev) => ({ ...prev, [alertId]: true }));
    try {
      await action();
      await fetchAlerts();
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to update alert.'));
    } finally {
      setActionLoading((prev) => ({ ...prev, [alertId]: false }));
    }
  };

  const handleAcknowledge = async (alertId: string) => {
    if (!storeId) return;
    await withActionLoading(alertId, async () => {
      await apiService.acknowledgeAlert(alertId, { store_id: storeId });
      toast.success('Alert acknowledged');
    });
  };

  const handleResolve = async (alertId: string) => {
    if (!storeId) return;
    await withActionLoading(alertId, async () => {
      await apiService.resolveAlert(alertId, { store_id: storeId });
      toast.success('Alert resolved');
    });
  };

  return (
    <AppLayout>
      <div className="space-y-8">
        <div className="flex items-center justify-between">
          <h1 className="text-3xl font-bold tracking-tight">Alerts</h1>
        </div>

        {loading ? (
          <div className="text-center py-12 text-muted-foreground">Loading alerts...</div>
        ) : alerts.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">No active alerts.</div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {alerts.map((alert) => (
              <Card key={alert.alert_id} className="flex flex-col">
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="w-5 h-5 text-destructive" />
                      <CardTitle className="text-lg">{alert.title}</CardTitle>
                    </div>
                    <Badge variant={alert.status === 'ACTIVE' ? 'destructive' : 'secondary'}>
                      {alert.status}
                    </Badge>
                  </div>
                  <CardDescription>{format(new Date(alert.created_at), 'PPp')}</CardDescription>
                </CardHeader>
                <CardContent className="flex-1">
                  <p className="text-sm">{alert.message}</p>
                </CardContent>
                <CardFooter className="gap-2 border-t pt-4">
                  {alert.status === 'ACTIVE' && (
                    <Button
                      variant="outline"
                      className="flex-1"
                      onClick={() => handleAcknowledge(alert.alert_id)}
                      disabled={Boolean(actionLoading[alert.alert_id])}
                    >
                      <Clock className="w-4 h-4 mr-2" />
                      Acknowledge
                    </Button>
                  )}
                  {alert.status !== 'RESOLVED' && (
                    <Button
                      className="flex-1"
                      onClick={() => handleResolve(alert.alert_id)}
                      disabled={Boolean(actionLoading[alert.alert_id])}
                    >
                      <CheckCircle2 className="w-4 h-4 mr-2" />
                      Resolve
                    </Button>
                  )}
                </CardFooter>
              </Card>
            ))}
          </div>
        )}
      </div>
    </AppLayout>
  );
}
