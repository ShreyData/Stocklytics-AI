import { getBillingFailureMessage } from './errors';

describe('getBillingFailureMessage', () => {
  it('returns a clear insufficient stock summary', () => {
    const message = getBillingFailureMessage({
      code: 'INSUFFICIENT_STOCK',
      message: 'One or more products do not have enough stock.',
      details: {
        failed_items: [
          {
            product_id: 'prod_rice_5kg',
            requested_quantity: 4,
            available_quantity: 2,
          },
        ],
      },
    });

    expect(message).toContain('Insufficient stock');
    expect(message).toContain('prod_rice_5kg');
    expect(message).toContain('requested 4, available 2');
  });
});
