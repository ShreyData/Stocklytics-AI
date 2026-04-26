import React from 'react';
import { CheckCircle2, Clock } from 'lucide-react';
import { Alert } from '@/lib/types';
import { Button } from './ui/button';

interface AlertActionButtonsProps {
  alert: Alert;
  isLoading: boolean;
  onAcknowledge: () => void;
  onResolve: () => void;
}

export function AlertActionButtons({
  alert,
  isLoading,
  onAcknowledge,
  onResolve,
}: AlertActionButtonsProps) {
  return (
    <>
      {alert.status === 'ACTIVE' ? (
        <Button
          variant="outline"
          className="flex-1"
          onClick={onAcknowledge}
          disabled={isLoading}
        >
          <Clock className="mr-2 h-4 w-4" />
          Acknowledge
        </Button>
      ) : null}
      {alert.status !== 'RESOLVED' ? (
        <Button className="flex-1" onClick={onResolve} disabled={isLoading}>
          <CheckCircle2 className="mr-2 h-4 w-4" />
          Resolve
        </Button>
      ) : null}
    </>
  );
}
