'use client';

import { useEffect, useState } from 'react';
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

export default function Alerts() {
  const { storeId } = useAuth();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchAlerts = async () => {
      try {
        const res = await apiService.getAlerts(storeId);
        setAlerts(res.items);
      } catch (error) {
        toast.error('Failed to load alerts');
      } finally {
        setLoading(false);
      }
    };
    fetchAlerts();
  }, [storeId]);

  const handleAcknowledge = (alertId: string) => {
    setAlerts((prev) =>
      prev.map((a) => (a.alert_id === alertId ? { ...a, status: 'ACKNOWLEDGED' } : a))
    );
    toast.success('Alert acknowledged');
  };

  const handleResolve = (alertId: string) => {
    setAlerts((prev) =>
      prev.map((a) => (a.alert_id === alertId ? { ...a, status: 'RESOLVED' } : a))
    );
    toast.success('Alert resolved');
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
                    >
                      <Clock className="w-4 h-4 mr-2" />
                      Acknowledge
                    </Button>
                  )}
                  {alert.status !== 'RESOLVED' && (
                    <Button
                      className="flex-1"
                      onClick={() => handleResolve(alert.alert_id)}
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
