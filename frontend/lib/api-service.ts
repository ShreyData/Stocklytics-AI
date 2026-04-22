import { apiClient } from './api';
import {
  DashboardSummary,
  Alert,
  Product,
  AnalyticsResponse,
  ProductCreateRequest,
  ProductUpdateRequest,
  StockAdjustmentRequest,
} from './types';
import { v4 as uuidv4 } from 'uuid';

// ---------------------------------------------------------------------------
// Config: check if we should force mock mode
// ---------------------------------------------------------------------------

const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === 'true';

// ---------------------------------------------------------------------------
// Mock data (used when backend modules are stubs or as fallback)
// ---------------------------------------------------------------------------

const mockDashboardSummary: DashboardSummary = {
  today_sales: 12450.0,
  today_transactions: 31,
  active_alert_count: 6,
  low_stock_count: 4,
  top_selling_product: 'Rice 5kg',
};

const mockProducts: Product[] = [
  {
    product_id: 'prod_rice_5kg',
    store_id: 'store_001',
    name: 'Rice 5kg',
    category: 'Groceries',
    price: 320.0,
    quantity_on_hand: 25,
    expiry_date: '2026-06-30T00:00:00Z',
    reorder_threshold: 8,
    expiry_status: 'OK',
    status: 'ACTIVE',
  },
  {
    product_id: 'prod_biscuit_01',
    store_id: 'store_001',
    name: 'Biscuit Pack',
    category: 'Snacks',
    price: 35.0,
    quantity_on_hand: 47,
    expiry_date: '2026-07-10T00:00:00Z',
    reorder_threshold: 50,
    expiry_status: 'OK',
    status: 'ACTIVE',
  },
  {
    product_id: 'prod_milk_1l',
    store_id: 'store_001',
    name: 'Milk 1L',
    category: 'Dairy',
    price: 60.0,
    quantity_on_hand: 5,
    expiry_date: '2026-04-15T00:00:00Z',
    reorder_threshold: 10,
    expiry_status: 'EXPIRING_SOON',
    status: 'ACTIVE',
  },
];

const mockAlerts: Alert[] = [
  {
    alert_id: 'alert_001',
    alert_type: 'LOW_STOCK',
    status: 'ACTIVE',
    severity: 'HIGH',
    title: 'Milk 1L stock is low',
    message: 'Only 5 units left. Reorder soon.',
    created_at: '2026-04-02T10:31:00Z',
    source_entity_id: 'prod_milk_1l',
  },
  {
    alert_id: 'alert_013',
    alert_type: 'NOT_SELLING',
    status: 'ACTIVE',
    severity: 'MEDIUM',
    title: 'Biscuit Pack is not selling',
    message: 'No sale recorded in the last 14 days.',
    created_at: '2026-04-01T09:00:00Z',
    source_entity_id: 'prod_biscuit_01',
  },
];

// Simulate network delay for mock calls
const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// ---------------------------------------------------------------------------
// API Service
// ---------------------------------------------------------------------------

export const apiService = {
  // =========================================================================
  // INVENTORY — Real API calls (fallback to mocks if backend unavailable)
  // =========================================================================

  getProducts: async (storeId: string): Promise<{ items: Product[] }> => {
    if (USE_MOCKS) {
      await delay(500);
      return { items: mockProducts };
    }
    try {
      const res = await apiClient.get('/inventory/products', {
        params: { store_id: storeId },
      });
      return { items: res.data.items || [] };
    } catch (error) {
      console.warn('Backend unavailable for inventory, using mock data', error);
      await delay(300);
      return { items: mockProducts };
    }
  },

  getProduct: async (productId: string): Promise<{ product: Product }> => {
    if (USE_MOCKS) {
      await delay(300);
      const product = mockProducts.find((p) => p.product_id === productId);
      return { product: product || mockProducts[0] };
    }
    try {
      const res = await apiClient.get(`/inventory/products/${productId}`);
      return { product: res.data.product };
    } catch (error) {
      console.warn('Backend unavailable, using mock data', error);
      const product = mockProducts.find((p) => p.product_id === productId);
      return { product: product || mockProducts[0] };
    }
  },

  createProduct: async (data: ProductCreateRequest): Promise<{ product: Product }> => {
    if (USE_MOCKS) {
      await delay(500);
      const newProduct: Product = {
        product_id: `prod_${uuidv4().slice(0, 8)}`,
        store_id: data.store_id,
        name: data.name,
        category: data.category,
        price: data.price,
        quantity_on_hand: data.quantity,
        reorder_threshold: data.reorder_threshold,
        expiry_date: data.expiry_date || null,
        expiry_status: 'OK',
        status: data.status || 'ACTIVE',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      mockProducts.push(newProduct);
      return { product: newProduct };
    }
    const res = await apiClient.post('/inventory/products', data);
    return { product: res.data.product };
  },

  updateProduct: async (
    productId: string,
    data: ProductUpdateRequest
  ): Promise<{ product: Product }> => {
    if (USE_MOCKS) {
      await delay(500);
      const idx = mockProducts.findIndex((p) => p.product_id === productId);
      if (idx !== -1) {
        mockProducts[idx] = { ...mockProducts[idx], ...data, updated_at: new Date().toISOString() };
        return { product: mockProducts[idx] };
      }
      throw { code: 'NOT_FOUND', message: 'Product not found' };
    }
    const res = await apiClient.patch(`/inventory/products/${productId}`, data);
    return { product: res.data.product };
  },

  adjustStock: async (
    productId: string,
    data: StockAdjustmentRequest
  ): Promise<any> => {
    if (USE_MOCKS) {
      await delay(500);
      const product = mockProducts.find((p) => p.product_id === productId);
      if (product) {
        if (data.adjustment_type === 'ADD') {
          product.quantity_on_hand += data.quantity_delta;
        } else {
          product.quantity_on_hand = Math.max(0, product.quantity_on_hand - data.quantity_delta);
        }
      }
      return { request_id: uuidv4(), adjustment_id: `adj_${uuidv4().slice(0, 8)}` };
    }
    const res = await apiClient.post(
      `/inventory/products/${productId}/stock-adjustments`,
      data
    );
    return res.data;
  },

  // =========================================================================
  // ANALYTICS — Mock (backend stub, no endpoints yet)
  // =========================================================================

  getDashboardSummary: async (storeId: string): Promise<AnalyticsResponse<DashboardSummary>> => {
    await delay(500);
    return {
      request_id: uuidv4(),
      analytics_last_updated_at: new Date().toISOString(),
      freshness_status: 'fresh',
      summary: mockDashboardSummary,
    };
  },

  // =========================================================================
  // ALERTS — Mock (backend stub, no endpoints yet)
  // =========================================================================

  getAlerts: async (storeId: string): Promise<{ items: Alert[] }> => {
    await delay(500);
    return { items: mockAlerts };
  },

  // =========================================================================
  // BILLING — Mock (backend stub, no endpoints yet)
  // =========================================================================

  createTransaction: async (data: any): Promise<any> => {
    await delay(800);
    const failedItems = data.items.filter((item: any) => {
      const product = mockProducts.find((p) => p.product_id === item.product_id);
      return !product || product.quantity_on_hand < item.quantity;
    });

    if (failedItems.length > 0) {
      throw {
        code: 'INSUFFICIENT_STOCK',
        message: 'One or more products do not have enough stock.',
        details: { failed_items: failedItems },
      };
    }

    return {
      request_id: uuidv4(),
      idempotent_replay: false,
      transaction: {
        transaction_id: `txn_${uuidv4()}`,
        status: 'COMPLETED',
        total_amount: data.items.reduce(
          (acc: number, item: any) => acc + item.quantity * 100,
          0
        ),
      },
    };
  },

  // =========================================================================
  // AI CHAT — Mock (backend stub, no endpoints yet)
  // =========================================================================

  askAI: async (storeId: string, query: string): Promise<any> => {
    await delay(1500);
    return {
      request_id: uuidv4(),
      chat_session_id: uuidv4(),
      analytics_last_updated_at: new Date().toISOString(),
      freshness_status: 'fresh',
      answer: `Based on the analytics summary, today's sales are $12,450. The top selling product is Rice 5kg. There is an active alert for Biscuit Pack not selling.`,
      grounding: {
        analytics_used: true,
        alerts_used: ['alert_013'],
        inventory_products_used: ['prod_rice_5kg', 'prod_biscuit_01'],
      },
    };
  },
};
