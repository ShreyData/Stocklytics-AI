import React from 'react';
import { AlertTriangle } from 'lucide-react';
import { FreshnessStatus } from '@/lib/types';
import { cn } from '@/lib/utils';

interface FreshnessNoteProps {
  status: FreshnessStatus;
  className?: string;
}

export function FreshnessNote({ status, className }: FreshnessNoteProps) {
  if (status === 'fresh') {
    return null;
  }

  const message =
    status === 'delayed'
      ? 'Analytics is slightly delayed. Values shown here use the latest successful snapshot.'
      : 'Analytics is stale. Keep the data visible, but treat it as an older snapshot until the pipeline refreshes.';

  return (
    <div
      className={cn(
        'flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-100',
        className
      )}
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
      <p>{message}</p>
    </div>
  );
}
