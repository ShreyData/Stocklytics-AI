export type FreshnessStatus = 'fresh' | 'delayed' | 'stale';

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  request_id?: string;
  status?: number;
}

// ---------------------------------------------------------------------------
// Auth types
// ---------------------------------------------------------------------------

export interface UserProfile {
  user_id: string;
  role: string;
  store_id: string;
  email?: string | null;
}

export interface MeResponse {
  request_id: string;
  user: UserProfile;
}

// ---------------------------------------------------------------------------
// Product types
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

export interface BillingLineItemRequest {
  product_id: string;
  quantity: number;
}

export interface BillingCreateRequest {
  store_id: string;
  idempotency_key: string;
  customer_id?: string;
  payment_method: 'cash' | 'upi' | 'card';
  items: BillingLineItemRequest[];
}

export interface TransactionItem {
  product_id: string;
  quantity: number;
  unit_price: number;
  line_total: number;
}

export interface Transaction {
  transaction_id: string;
  store_id?: string;
  customer_id?: string | null;
  status: 'COMPLETED' | 'FAILED' | 'PENDING';
  payment_method?: string;
  total_amount: number;
  sale_timestamp?: string;
  idempotency_key?: string;
  items?: TransactionItem[];
}

export interface InventoryUpdate {
  product_id: string;
  new_quantity_on_hand: number;
}

export interface BillingCreateResponse {
  request_id: string;
  idempotent_replay: boolean;
  transaction: Transaction;
  inventory_updates?: InventoryUpdate[];
}

// ---------------------------------------------------------------------------
// Customer types
// ---------------------------------------------------------------------------

export interface Customer {
  customer_id: string;
  store_id?: string;
  name: string;
  phone: string;
  total_spend: number;
  visit_count: number;
  last_purchase_at?: string | null;
}

export interface CustomerCreateRequest {
  store_id: string;
  name: string;
  phone: string;
}

// ---------------------------------------------------------------------------
// Alert types
// ---------------------------------------------------------------------------

export interface Alert {
  alert_id: string;
  store_id?: string;
  alert_type: 'LOW_STOCK' | 'NOT_SELLING' | 'EXPIRY_SOON' | 'HIGH_DEMAND';
  status: 'ACTIVE' | 'ACKNOWLEDGED' | 'RESOLVED';
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  title: string;
  message: string;
  created_at: string;
  acknowledged_at?: string | null;
  resolved_at?: string | null;
  source_entity_id?: string;
}

export interface AlertsSummary {
  active: number;
  acknowledged: number;
  resolved_today: number;
}

// ---------------------------------------------------------------------------
// Dashboard / Analytics types
// ---------------------------------------------------------------------------

export interface DashboardSummary {
  today_sales: number;
  today_transactions: number;
  active_alert_count: number;
  low_stock_count: number;
  top_selling_product: string | null;
}

export interface SalesTrendPoint {
  label: string;
  sales_amount: number;
  transactions: number;
}

export interface ProductPerformanceItem {
  product_id: string;
  product_name: string;
  quantity_sold: number;
  revenue: number;
}

export interface CustomerInsight {
  customer_id: string;
  name: string;
  lifetime_spend: number;
  visit_count: number;
}

export interface AnalyticsResponse<T> {
  request_id: string;
  analytics_last_updated_at: string;
  freshness_status: FreshnessStatus;
  summary?: DashboardSummary;
  points?: T[];
  items?: T[];
  top_customers?: T[];
}

// ---------------------------------------------------------------------------
// AI types
// ---------------------------------------------------------------------------

export interface AIGrounding {
  analytics_used: boolean;
  alerts_used: string[];
  inventory_products_used: string[];
}

export interface AIChatResponse {
  request_id: string;
  chat_session_id: string;
  analytics_last_updated_at: string;
  freshness_status: FreshnessStatus;
  answer: string;
  grounding: AIGrounding;
}

// ---------------------------------------------------------------------------
// API envelope
// ---------------------------------------------------------------------------

export interface ApiResponse<T = unknown> {
  request_id: string;
  [key: string]: T | string | number | boolean | null | undefined;
}
