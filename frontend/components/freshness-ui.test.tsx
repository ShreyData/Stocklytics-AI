import React from 'react';
import { render, screen } from '@testing-library/react';
import { FreshnessBadge } from './freshness-badge';
import { FreshnessNote } from './freshness-note';

describe('freshness UI', () => {
  it('shows the freshness badge label', () => {
    render(<FreshnessBadge lastUpdatedAt="2026-04-26T10:45:00Z" status="delayed" />);

    expect(screen.getByText('Delayed')).toBeInTheDocument();
  });

  it('shows a stale warning note without hiding the data', () => {
    render(<FreshnessNote status="stale" />);

    expect(screen.getByText(/Analytics is stale/i)).toBeInTheDocument();
  });
});
