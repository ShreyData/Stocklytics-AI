import React from 'react';
import { Badge } from './ui/badge';
import { formatDistanceToNow } from 'date-fns';
import { Clock } from 'lucide-react';
import { cn } from '@/lib/utils';

interface FreshnessBadgeProps {
  lastUpdatedAt: string;
  status: 'fresh' | 'delayed' | 'stale';
  className?: string;
}

export function FreshnessBadge({ lastUpdatedAt, status, className }: FreshnessBadgeProps) {
  const timeAgo = formatDistanceToNow(new Date(lastUpdatedAt), { addSuffix: true });

  const statusConfig = {
    fresh: { label: 'Fresh', color: 'bg-green-500/10 text-green-500 border-green-500/20' },
    delayed: { label: 'Delayed', color: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20' },
    stale: { label: 'Stale', color: 'bg-red-500/10 text-red-500 border-red-500/20' },
  };

  const config = statusConfig[status];

  return (
    <div className={cn('flex items-center gap-2', className)}>
      <Badge variant="outline" className={cn('font-mono text-xs', config.color)}>
        <Clock className="w-3 h-3 mr-1" />
        {config.label}
      </Badge>
      <span className="text-xs text-muted-foreground font-mono">
        Updated {timeAgo}
      </span>
    </div>
  );
}
