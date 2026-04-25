import { apiClient } from './api';
import {
  AIChatResponse,
  Alert,
  AlertsSummary,
  AnalyticsResponse,
  BillingCreateRequest,
  BillingCreateResponse,
  Customer,
  CustomerCreateRequest,
  CustomerInsight,
  DashboardSummary,
  MeResponse,
  Product,
  ProductCreateRequest,
  ProductPerformanceItem,
  ProductUpdateRequest,
  SalesTrendPoint,
  StockAdjustmentRequest,
} from './types';

export const apiService = {
  // =========================================================================
  // PLATFORM / AUTH
  // =========================================================================

  getMe: async (): Promise<MeResponse> => {
    const res = await apiClient.get('/me');
    return res.data;
  },

  // =========================================================================
  // INVENTORY
  // =========================================================================

  getProducts: async (
    storeId: string
  ): Promise<{ request_id: string; items: Product[]; next_page_token?: string | null }> => {
    const res = await apiClient.get('/inventory/products', {
      params: { store_id: storeId },
    });
    return {
      request_id: res.data.request_id,
      items: res.data.items || [],
      next_page_token: res.data.next_page_token,
    };
  },

  getProduct: async (
    productId: string
  ): Promise<{ request_id: string; product: Product }> => {
    const res = await apiClient.get(`/inventory/products/${productId}`);
    return { request_id: res.data.request_id, product: res.data.product };
  },

  createProduct: async (
    data: ProductCreateRequest
  ): Promise<{ request_id: string; product: Product }> => {
    const res = await apiClient.post('/inventory/products', data);
    return { request_id: res.data.request_id, product: res.data.product };
  },

  updateProduct: async (
    productId: string,
    data: ProductUpdateRequest
  ): Promise<{ request_id: string; product: Product }> => {
    const res = await apiClient.patch(`/inventory/products/${productId}`, data);
    return { request_id: res.data.request_id, product: res.data.product };
  },

  adjustStock: async (
    productId: string,
    data: StockAdjustmentRequest
  ): Promise<{ request_id: string; adjustment_id: string }> => {
    const res = await apiClient.post(
      `/inventory/products/${productId}/stock-adjustments`,
      data
    );
    return {
      request_id: res.data.request_id,
      adjustment_id: res.data.adjustment_id,
    };
  },

  // =========================================================================
  // BILLING
  // =========================================================================

  createTransaction: async (
    data: BillingCreateRequest
  ): Promise<BillingCreateResponse> => {
    const res = await apiClient.post('/billing/transactions', data);
    return res.data;
  },

  // =========================================================================
  // CUSTOMERS
  // =========================================================================

  getCustomers: async (): Promise<{ request_id: string; items: Customer[] }> => {
    const res = await apiClient.get('/customers');
    return { request_id: res.data.request_id, items: res.data.items || [] };
  },

  createCustomer: async (
    data: CustomerCreateRequest
  ): Promise<{ request_id: string; customer: Customer }> => {
    const res = await apiClient.post('/customers', data);
    return { request_id: res.data.request_id, customer: res.data.customer };
  },

  // =========================================================================
  // ANALYTICS
  // =========================================================================

  getDashboardSummary: async (
    storeId: string
  ): Promise<AnalyticsResponse<DashboardSummary>> => {
    const res = await apiClient.get('/analytics/dashboard', {
      params: { store_id: storeId },
    });
    return res.data;
  },

  getSalesTrends: async (
    storeId: string,
    range: '7d' | '30d' | '90d' = '30d',
    granularity: 'daily' | 'weekly' = 'daily'
  ): Promise<AnalyticsResponse<SalesTrendPoint>> => {
    const res = await apiClient.get('/analytics/sales-trends', {
      params: { store_id: storeId, range, granularity },
    });
    return res.data;
  },

  getProductPerformance: async (
    storeId: string
  ): Promise<AnalyticsResponse<ProductPerformanceItem>> => {
    const res = await apiClient.get('/analytics/product-performance', {
      params: { store_id: storeId },
    });
    return res.data;
  },

  getCustomerInsights: async (
    storeId: string
  ): Promise<AnalyticsResponse<CustomerInsight>> => {
    const res = await apiClient.get('/analytics/customer-insights', {
      params: { store_id: storeId },
    });
    return res.data;
  },

  // =========================================================================
  // ALERTS
  // =========================================================================

  getAlerts: async (
    storeId: string
  ): Promise<{ request_id: string; items: Alert[] }> => {
    const res = await apiClient.get('/alerts', {
      params: { store_id: storeId },
    });
    return { request_id: res.data.request_id, items: res.data.items || [] };
  },

  getAlertsSummary: async (
    storeId: string
  ): Promise<{ request_id: string; summary: AlertsSummary }> => {
    const res = await apiClient.get('/alerts/summary', {
      params: { store_id: storeId },
    });
    return { request_id: res.data.request_id, summary: res.data.summary };
  },

  acknowledgeAlert: async (
    alertId: string,
    payload: { store_id: string; note?: string }
  ): Promise<{ request_id: string; alert: Partial<Alert> }> => {
    const res = await apiClient.post(`/alerts/${alertId}/acknowledge`, payload);
    return { request_id: res.data.request_id, alert: res.data.alert };
  },

  resolveAlert: async (
    alertId: string,
    payload: { store_id: string; resolution_note?: string }
  ): Promise<{ request_id: string; alert: Partial<Alert> }> => {
    const res = await apiClient.post(`/alerts/${alertId}/resolve`, payload);
    return { request_id: res.data.request_id, alert: res.data.alert };
  },

  // =========================================================================
  // AI
  // =========================================================================

  askAI: async (
    storeId: string,
    chatSessionId: string,
    query: string
  ): Promise<AIChatResponse> => {
    const res = await apiClient.post('/ai/chat', {
      store_id: storeId,
      chat_session_id: chatSessionId,
      query,
    });
    return res.data;
  },

  getChatSessionHistory: async (
    chatSessionId: string
  ): Promise<{
    request_id: string;
    chat_session_id: string;
    messages: Array<{ role: 'user' | 'assistant'; text: string; created_at: string }>;
  }> => {
    const res = await apiClient.get(`/ai/chat/sessions/${chatSessionId}`);
    return res.data;
  },
};
