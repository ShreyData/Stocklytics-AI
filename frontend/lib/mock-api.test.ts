import { mockApi, resetMockState } from './mock-api';

describe('mockApi', () => {
  beforeEach(() => {
    resetMockState();
  });

  it('replays billing requests with the same idempotency key', async () => {
    const payload = {
      store_id: 'store_001',
      idempotency_key: 'bill_demo_001',
      payment_method: 'cash' as const,
      items: [{ product_id: 'prod_rice_5kg', quantity: 2 }],
    };

    const first = await mockApi.createTransaction(payload);
    const replay = await mockApi.createTransaction(payload);

    expect(first.idempotent_replay).toBe(false);
    expect(replay.idempotent_replay).toBe(true);
    expect(replay.transaction.transaction_id).toBe(first.transaction.transaction_id);
  });

  it('supports alert acknowledge and resolve actions', async () => {
    const acknowledged = await mockApi.acknowledgeAlert('alert_low_stock_001');
    expect(acknowledged.alert.status).toBe('ACKNOWLEDGED');

    const resolved = await mockApi.resolveAlert('alert_low_stock_001');
    expect(resolved.alert.status).toBe('RESOLVED');
    expect(resolved.alert.resolved_at).toBeTruthy();
  });

  it('recomputes analytics and alerts from live billing and inventory changes', async () => {
    const beforeDashboard = await mockApi.getDashboardSummary();
    const beforeProducts = await mockApi.getProductPerformance();

    await mockApi.createTransaction({
      store_id: 'store_001',
      idempotency_key: 'bill_live_sync_001',
      payment_method: 'cash',
      items: [{ product_id: 'prod_rice_5kg', quantity: 2 }],
    });

    const afterBillingDashboard = await mockApi.getDashboardSummary();
    const afterBillingProducts = await mockApi.getProductPerformance();

    expect(afterBillingDashboard.summary?.today_sales).toBe(
      (beforeDashboard.summary?.today_sales ?? 0) + 640
    );
    expect(afterBillingDashboard.summary?.today_transactions).toBe(
      (beforeDashboard.summary?.today_transactions ?? 0) + 1
    );
    expect(
      afterBillingProducts.items?.find((item) => item.product_id === 'prod_rice_5kg')?.quantity_sold
    ).toBe(
      (beforeProducts.items?.find((item) => item.product_id === 'prod_rice_5kg')?.quantity_sold ?? 0) + 2
    );

    await mockApi.adjustStock('prod_rice_5kg', {
      store_id: 'store_001',
      adjustment_type: 'REMOVE',
      quantity_delta: 7,
      reason: 'Damage during unloading',
    });

    const alerts = await mockApi.getAlerts({
      status: 'ACTIVE',
      alert_type: 'LOW_STOCK',
    });

    expect(alerts.items.some((alert) => alert.source_entity_id === 'prod_rice_5kg')).toBe(true);
  });

  it('returns AI answers with a freshness note when analytics is delayed', async () => {
    const response = await mockApi.askAI('store_001', 'chat_demo_qa', 'What needs attention?');

    expect(response.freshness_status).toBe('fresh');
    expect(response.answer).toContain('latest available snapshot');
  });
});
