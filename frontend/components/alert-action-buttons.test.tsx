import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AlertActionButtons } from './alert-action-buttons';

const baseAlert = {
  alert_id: 'alert_001',
  alert_type: 'LOW_STOCK' as const,
  status: 'ACTIVE' as const,
  severity: 'HIGH' as const,
  title: 'Low Stock',
  message: 'Stock is low',
  created_at: '2026-04-26T09:00:00Z',
};

describe('AlertActionButtons', () => {
  it('renders acknowledge and resolve actions for active alerts', async () => {
    const user = userEvent.setup();
    const onAcknowledge = vi.fn();
    const onResolve = vi.fn();

    render(
      <AlertActionButtons
        alert={baseAlert}
        isLoading={false}
        onAcknowledge={onAcknowledge}
        onResolve={onResolve}
      />
    );

    await user.click(screen.getByRole('button', { name: /acknowledge/i }));
    await user.click(screen.getByRole('button', { name: /resolve/i }));

    expect(onAcknowledge).toHaveBeenCalledTimes(1);
    expect(onResolve).toHaveBeenCalledTimes(1);
  });
});
