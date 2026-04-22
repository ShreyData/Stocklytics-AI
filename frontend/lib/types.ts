// ---------------------------------------------------------------------------
// Product types — aligned with backend ProductResponse / ProductCreateRequest
// ---------------------------------------------------------------------------

export interface Product {
  product_id: string;
  store_id: string;
  name: string;
  category: string;
  price: number;
  quantity_on_hand: number;
  reorder_threshold: number;
  expiry_date: string | null;
  expiry_status: 'OK' | 'EXPIRING_SOON' | 'EXPIRED';
  status: 'ACTIVE' | 'INACTIVE';
  created_at?: string;
  updated_at?: string;
}

export interface ProductCreateRequest {
  store_id: string;
  name: string;
  category: string;
  price: number;
  quantity: number;
  reorder_threshold: number;
  expiry_date?: string | null;
  status?: 'ACTIVE' | 'INACTIVE';
}

export interface ProductUpdateRequest {
  store_id: string;
  name?: string;
  category?: string;
  price?: number;
  reorder_threshold?: number;
  expiry_date?: string | null;
  status?: 'ACTIVE' | 'INACTIVE';
}

export interface StockAdjustmentRequest {
  store_id: string;
  adjustment_type: 'ADD' | 'REMOVE' | 'SALE_DEDUCTION' | 'MANUAL_CORRECTION';
  quantity_delta: number;
  reason: string;
  source_ref?: string;
}

// ---------------------------------------------------------------------------
// Billing types
// ---------------------------------------------------------------------------

export interface TransactionItem {
  product_id: string;
  quantity: number;
  unit_price: number;
  line_total: number;
}

export interface Transaction {
  transaction_id: string;
  store_id: string;
  customer_id?: string;
  status: 'COMPLETED' | 'FAILED' | 'PENDING';
  payment_method: string;
  total_amount: number;
  sale_timestamp: string;
  idempotency_key?: string;
  items: TransactionItem[];
}

// ---------------------------------------------------------------------------
// Customer types
// ---------------------------------------------------------------------------

export interface Customer {
  customer_id: string;
  store_id: string;
  name: string;
  phone: string;
  total_spend: number;
  visit_count: number;
  last_purchase_at?: string;
}

// ---------------------------------------------------------------------------
// Alert types
// ---------------------------------------------------------------------------

export interface Alert {
  alert_id: string;
  alert_type: 'LOW_STOCK' | 'NOT_SELLING' | 'EXPIRING_SOON';
  status: 'ACTIVE' | 'ACKNOWLEDGED' | 'RESOLVED';
  severity: 'HIGH' | 'MEDIUM' | 'LOW';
  title: string;
  message: string;
  created_at: string;
  acknowledged_at?: string | null;
  resolved_at?: string | null;
  source_entity_id?: string;
}

// ---------------------------------------------------------------------------
// Dashboard / Analytics types
// ---------------------------------------------------------------------------

export interface DashboardSummary {
  today_sales: number;
  today_transactions: number;
  active_alert_count: number;
  low_stock_count: number;
  top_selling_product: string;
}

export interface AnalyticsResponse<T> {
  request_id: string;
  analytics_last_updated_at: string;
  freshness_status: 'fresh' | 'delayed' | 'stale';
  summary?: DashboardSummary;
  points?: any[];
  items?: any[];
  top_customers?: any[];
}

// ---------------------------------------------------------------------------
// API envelope — matches backend success_response helper
// ---------------------------------------------------------------------------

export interface ApiResponse<T = any> {
  request_id: string;
  [key: string]: any;
}
