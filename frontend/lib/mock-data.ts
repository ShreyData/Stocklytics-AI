import {
  Alert,
  Customer,
  CustomerInsight,
  CustomerPurchaseHistoryItem,
  DashboardSummary,
  Product,
  ProductPerformanceItem,
  SalesTrendPoint,
} from './types';

const now = new Date('2026-04-26T11:30:00.000Z');

export const MOCK_USER = {
  user_id: 'dev_user_001',
  role: 'admin',
  store_id: 'store_001',
  email: 'dev@stocklytics.local',
};

export const MOCK_PRODUCTS: Product[] = [
  {
    product_id: 'prod_rice_5kg',
    store_id: 'store_001',
    name: 'Rice 5kg',
    category: 'Grocery',
    price: 320,
    quantity_on_hand: 18,
    reorder_threshold: 10,
    expiry_date: '2026-08-15T00:00:00Z',
    expiry_status: 'OK',
    status: 'ACTIVE',
    created_at: '2026-04-01T09:00:00Z',
    updated_at: '2026-04-26T10:00:00Z',
  },
  {
    product_id: 'prod_biscuit_01',
    store_id: 'store_001',
    name: 'Butter Biscuit',
    category: 'Snacks',
    price: 35,
    quantity_on_hand: 6,
    reorder_threshold: 8,
    expiry_date: '2026-05-04T00:00:00Z',
    expiry_status: 'EXPIRING_SOON',
    status: 'ACTIVE',
    created_at: '2026-04-01T09:05:00Z',
    updated_at: '2026-04-26T10:00:00Z',
  },
  {
    product_id: 'prod_milk_1l',
    store_id: 'store_001',
    name: 'Milk 1L',
    category: 'Dairy',
    price: 64,
    quantity_on_hand: 0,
    reorder_threshold: 6,
    expiry_date: '2026-04-25T00:00:00Z',
    expiry_status: 'EXPIRED',
    status: 'ACTIVE',
    created_at: '2026-04-02T09:00:00Z',
    updated_at: '2026-04-26T09:45:00Z',
  },
];

export const MOCK_CUSTOMERS: Customer[] = [
  {
    customer_id: 'cust_001',
    store_id: 'store_001',
    name: 'Ravi Kumar',
    phone: '+919999999999',
    total_spend: 3140,
    visit_count: 9,
    last_purchase_at: '2026-04-25T13:45:00Z',
  },
  {
    customer_id: 'cust_002',
    store_id: 'store_001',
    name: 'Asha Patel',
    phone: '+918888888888',
    total_spend: 1860,
    visit_count: 5,
    last_purchase_at: '2026-04-24T11:20:00Z',
  },
];

export const MOCK_PURCHASE_HISTORY: Record<string, CustomerPurchaseHistoryItem[]> = {
  cust_001: [
    {
      transaction_id: 'txn_101',
      total_amount: 745,
      sale_timestamp: '2026-04-25T13:45:00Z',
    },
    {
      transaction_id: 'txn_099',
      total_amount: 520,
      sale_timestamp: '2026-04-22T10:10:00Z',
    },
  ],
  cust_002: [
    {
      transaction_id: 'txn_098',
      total_amount: 360,
      sale_timestamp: '2026-04-24T11:20:00Z',
    },
  ],
};

export const MOCK_ALERTS: Alert[] = [
  {
    alert_id: 'alert_low_stock_001',
    store_id: 'store_001',
    alert_type: 'LOW_STOCK',
    status: 'ACTIVE',
    severity: 'HIGH',
    title: 'Low Stock: Butter Biscuit',
    message: 'Stock is below reorder threshold for Butter Biscuit.',
    created_at: '2026-04-26T08:45:00Z',
    condition_key: 'store_001:LOW_STOCK:prod_biscuit_01',
    source_entity_id: 'prod_biscuit_01',
  },
  {
    alert_id: 'alert_high_demand_001',
    store_id: 'store_001',
    alert_type: 'HIGH_DEMAND',
    status: 'ACKNOWLEDGED',
    severity: 'MEDIUM',
    title: 'High Demand: Rice 5kg',
    message: 'Rice 5kg sales are above the recent baseline.',
    created_at: '2026-04-25T15:10:00Z',
    acknowledged_at: '2026-04-25T15:25:00Z',
    acknowledged_by: 'dev_user_001',
    condition_key: 'store_001:HIGH_DEMAND:prod_rice_5kg',
    source_entity_id: 'prod_rice_5kg',
  },
  {
    alert_id: 'alert_not_selling_001',
    store_id: 'store_001',
    alert_type: 'NOT_SELLING',
    status: 'RESOLVED',
    severity: 'LOW',
    title: 'Not Selling: Milk 1L',
    message: 'Milk 1L has no recent sales and expired stock is present.',
    created_at: '2026-04-23T09:00:00Z',
    acknowledged_at: '2026-04-23T10:00:00Z',
    resolved_at: '2026-04-24T08:30:00Z',
    acknowledged_by: 'dev_user_001',
    resolved_by: 'dev_user_001',
    resolution_note: 'Pulled expired units and paused reorders.',
    condition_key: 'store_001:NOT_SELLING:prod_milk_1l',
    source_entity_id: 'prod_milk_1l',
  },
];

export const MOCK_DASHBOARD_SUMMARY: DashboardSummary = {
  today_sales: 12450,
  today_transactions: 31,
  active_alert_count: 2,
  low_stock_count: 2,
  top_selling_product: 'Rice 5kg',
};

export const MOCK_SALES_TRENDS: SalesTrendPoint[] = [
  { label: '2026-04-20', sales_amount: 10120, transactions: 25 },
  { label: '2026-04-21', sales_amount: 10860, transactions: 27 },
  { label: '2026-04-22', sales_amount: 11240, transactions: 28 },
  { label: '2026-04-23', sales_amount: 11800, transactions: 30 },
  { label: '2026-04-24', sales_amount: 12110, transactions: 32 },
  { label: '2026-04-25', sales_amount: 11920, transactions: 29 },
  { label: '2026-04-26', sales_amount: 12450, transactions: 31 },
];

export const MOCK_PRODUCT_PERFORMANCE: ProductPerformanceItem[] = [
  {
    product_id: 'prod_rice_5kg',
    product_name: 'Rice 5kg',
    quantity_sold: 48,
    revenue: 15360,
  },
  {
    product_id: 'prod_biscuit_01',
    product_name: 'Butter Biscuit',
    quantity_sold: 72,
    revenue: 2520,
  },
];

export const MOCK_CUSTOMER_INSIGHTS: CustomerInsight[] = [
  {
    customer_id: 'cust_001',
    name: 'Ravi Kumar',
    lifetime_spend: 3140,
    visit_count: 9,
  },
  {
    customer_id: 'cust_002',
    name: 'Asha Patel',
    lifetime_spend: 1860,
    visit_count: 5,
  },
];

export const MOCK_ANALYTICS_LAST_UPDATED_AT = new Date(
  now.getTime() - 45 * 60 * 1000
).toISOString();

export const MOCK_AI_HISTORY = {
  chat_demo_001: [
    {
      role: 'user' as const,
      text: 'What needs my attention first today?',
      created_at: '2026-04-26T09:30:00Z',
    },
    {
      role: 'assistant' as const,
      text: 'Butter Biscuit is below threshold, and Rice 5kg demand is elevated. Analytics is slightly delayed, so treat this as the latest available snapshot.',
      created_at: '2026-04-26T09:30:02Z',
    },
  ],
};
