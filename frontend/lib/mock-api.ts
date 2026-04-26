import { v4 as uuidv4 } from 'uuid';
import {
  AIChatResponse,
  Alert,
  AlertFilters,
  AlertsSummary,
  AnalyticsResponse,
  BillingCreateRequest,
  BillingCreateResponse,
  ChatHistoryMessage,
  Customer,
  CustomerCreateRequest,
  CustomerInsight,
  CustomerPurchaseHistoryItem,
  DashboardSummary,
  MeResponse,
  Product,
  ProductCreateRequest,
  ProductPerformanceItem,
  ProductUpdateRequest,
  SalesTrendPoint,
  StockAdjustmentRequest,
} from './types';
import {
  MOCK_AI_HISTORY,
  MOCK_ALERTS,
  MOCK_ANALYTICS_LAST_UPDATED_AT,
  MOCK_CUSTOMERS,
  MOCK_CUSTOMER_INSIGHTS,
  MOCK_DASHBOARD_SUMMARY,
  MOCK_PRODUCTS,
  MOCK_PURCHASE_HISTORY,
  MOCK_PRODUCT_PERFORMANCE,
  MOCK_SALES_TRENDS,
  MOCK_USER,
} from './mock-data';

type InventoryUpdatesResponse = {
  request_id: string;
  adjustment_id: string;
};

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

const state = {
  products: clone(MOCK_PRODUCTS),
  customers: clone(MOCK_CUSTOMERS),
  purchaseHistory: clone(MOCK_PURCHASE_HISTORY),
  alerts: clone(MOCK_ALERTS),
  chatHistory: clone(MOCK_AI_HISTORY) as Record<string, ChatHistoryMessage[]>,
  transactionsByKey: new Map<string, BillingCreateResponse>(),
};

export function resetMockState() {
  state.products = clone(MOCK_PRODUCTS);
  state.customers = clone(MOCK_CUSTOMERS);
  state.purchaseHistory = clone(MOCK_PURCHASE_HISTORY);
  state.alerts = clone(MOCK_ALERTS);
  state.chatHistory = clone(MOCK_AI_HISTORY) as Record<string, ChatHistoryMessage[]>;
  state.transactionsByKey = new Map<string, BillingCreateResponse>();
}

function nextRequestId(prefix: string) {
  return `${prefix}_${uuidv4().replace(/-/g, '').slice(0, 12)}`;
}

function getAlertsSummarySnapshot(alerts: Alert[]): AlertsSummary {
  const today = new Date().toISOString().slice(0, 10);
  return {
    active: alerts.filter((alert) => alert.status === 'ACTIVE').length,
    acknowledged: alerts.filter((alert) => alert.status === 'ACKNOWLEDGED').length,
    resolved_today: alerts.filter(
      (alert) => alert.status === 'RESOLVED' && alert.resolved_at?.startsWith(today)
    ).length,
  };
}

function getAnalyticsEnvelope<T>(payload: Partial<AnalyticsResponse<T>>) {
  return {
    request_id: nextRequestId('req_mock'),
    analytics_last_updated_at: MOCK_ANALYTICS_LAST_UPDATED_AT,
    freshness_status: 'delayed' as const,
    ...payload,
  };
}

function applyAlertFilters(items: Alert[], filters: AlertFilters = {}) {
  return items.filter((alert) => {
    if (filters.status && filters.status !== 'ALL' && alert.status !== filters.status) {
      return false;
    }
    if (filters.alert_type && filters.alert_type !== 'ALL' && alert.alert_type !== filters.alert_type) {
      return false;
    }
    if (filters.severity && filters.severity !== 'ALL' && alert.severity !== filters.severity) {
      return false;
    }
    return true;
  });
}

function aiFreshnessNote() {
  return '\n\nNote: Analytics data is slightly delayed, so this answer uses the latest available snapshot.';
}

export const mockApi = {
  async getMe(): Promise<MeResponse> {
    return {
      request_id: nextRequestId('req_me'),
      user: clone(MOCK_USER),
    };
  },

  async getProducts() {
    return {
      request_id: nextRequestId('req_products'),
      items: clone(state.products),
      next_page_token: null,
    };
  },

  async getProduct(productId: string) {
    const product = state.products.find((item) => item.product_id === productId);
    if (!product) {
      throw {
        code: 'PRODUCT_NOT_FOUND',
        message: 'Product was not found.',
        status: 404,
      };
    }
    return {
      request_id: nextRequestId('req_product'),
      product: clone(product),
    };
  },

  async createProduct(data: ProductCreateRequest) {
    const product: Product = {
      product_id: `prod_${uuidv4().slice(0, 8)}`,
      store_id: data.store_id,
      name: data.name,
      category: data.category,
      price: data.price,
      quantity_on_hand: data.quantity,
      reorder_threshold: data.reorder_threshold,
      expiry_date: data.expiry_date ?? null,
      expiry_status: 'OK',
      status: data.status ?? 'ACTIVE',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    state.products.unshift(product);
    return {
      request_id: nextRequestId('req_product_create'),
      product: clone(product),
    };
  },

  async updateProduct(productId: string, data: ProductUpdateRequest) {
    const product = state.products.find((item) => item.product_id === productId);
    if (!product) {
      throw {
        code: 'PRODUCT_NOT_FOUND',
        message: 'Product was not found.',
        status: 404,
      };
    }
    Object.assign(product, data, { updated_at: new Date().toISOString() });
    return {
      request_id: nextRequestId('req_product_update'),
      product: clone(product),
    };
  },

  async adjustStock(productId: string, data: StockAdjustmentRequest): Promise<InventoryUpdatesResponse> {
    const product = state.products.find((item) => item.product_id === productId);
    if (!product) {
      throw {
        code: 'PRODUCT_NOT_FOUND',
        message: 'Product was not found.',
        status: 404,
      };
    }

    const direction = data.adjustment_type === 'REMOVE' || data.adjustment_type === 'SALE_DEDUCTION' ? -1 : 1;
    const nextQuantity = product.quantity_on_hand + direction * data.quantity_delta;
    if (nextQuantity < 0) {
      throw {
        code: 'NEGATIVE_STOCK_NOT_ALLOWED',
        message: 'Stock cannot go negative.',
        status: 409,
      };
    }

    product.quantity_on_hand = nextQuantity;
    product.updated_at = new Date().toISOString();

    return {
      request_id: nextRequestId('req_adjust'),
      adjustment_id: `adj_${uuidv4().slice(0, 8)}`,
    };
  },

  async createTransaction(data: BillingCreateRequest): Promise<BillingCreateResponse> {
    const cached = state.transactionsByKey.get(data.idempotency_key);
    if (cached) {
      return {
        ...clone(cached),
        request_id: nextRequestId('req_bill_replay'),
        idempotent_replay: true,
      };
    }

    const failedItems = data.items
      .map((item) => {
        const product = state.products.find((candidate) => candidate.product_id === item.product_id);
        if (!product) {
          return {
            product_id: item.product_id,
            requested_quantity: item.quantity,
            available_quantity: 0,
          };
        }
        if (product.quantity_on_hand < item.quantity) {
          return {
            product_id: item.product_id,
            requested_quantity: item.quantity,
            available_quantity: product.quantity_on_hand,
          };
        }
        return null;
      })
      .filter(Boolean);

    if (failedItems.length > 0) {
      throw {
        code: 'INSUFFICIENT_STOCK',
        message: 'One or more products do not have enough stock.',
        details: { failed_items: failedItems },
        status: 409,
      };
    }

    const inventory_updates = data.items.map((item) => {
      const product = state.products.find((candidate) => candidate.product_id === item.product_id)!;
      product.quantity_on_hand -= item.quantity;
      product.updated_at = new Date().toISOString();
      return {
        product_id: product.product_id,
        new_quantity_on_hand: product.quantity_on_hand,
      };
    });

    const transaction = {
      transaction_id: `txn_${uuidv4().slice(0, 8)}`,
      store_id: data.store_id,
      customer_id: data.customer_id ?? null,
      status: 'COMPLETED' as const,
      payment_method: data.payment_method,
      total_amount: data.items.reduce((sum, item) => {
        const product = state.products.find((candidate) => candidate.product_id === item.product_id)!;
        return sum + product.price * item.quantity;
      }, 0),
      sale_timestamp: new Date().toISOString(),
      idempotency_key: data.idempotency_key,
      items: data.items.map((item) => {
        const product = state.products.find((candidate) => candidate.product_id === item.product_id)!;
        return {
          product_id: item.product_id,
          quantity: item.quantity,
          unit_price: product.price,
          line_total: product.price * item.quantity,
        };
      }),
    };

    if (data.customer_id) {
      const customer = state.customers.find((candidate) => candidate.customer_id === data.customer_id);
      if (customer) {
        customer.total_spend += transaction.total_amount;
        customer.visit_count += 1;
        customer.last_purchase_at = transaction.sale_timestamp;
        const history = state.purchaseHistory[data.customer_id] ?? [];
        history.unshift({
          transaction_id: transaction.transaction_id,
          total_amount: transaction.total_amount,
          sale_timestamp: transaction.sale_timestamp,
        });
        state.purchaseHistory[data.customer_id] = history;
      }
    }

    const response: BillingCreateResponse = {
      request_id: nextRequestId('req_bill'),
      idempotent_replay: false,
      transaction,
      inventory_updates,
    };
    state.transactionsByKey.set(data.idempotency_key, clone(response));
    return response;
  },

  async getCustomers() {
    return {
      request_id: nextRequestId('req_customers'),
      items: clone(state.customers),
    };
  },

  async createCustomer(data: CustomerCreateRequest) {
    const customer: Customer = {
      customer_id: `cust_${uuidv4().slice(0, 8)}`,
      store_id: data.store_id,
      name: data.name,
      phone: data.phone,
      total_spend: 0,
      visit_count: 0,
      last_purchase_at: null,
    };
    state.customers.unshift(customer);
    state.purchaseHistory[customer.customer_id] = [];
    return {
      request_id: nextRequestId('req_customer_create'),
      customer: clone(customer),
    };
  },

  async getCustomer(customerId: string) {
    const customer = state.customers.find((item) => item.customer_id === customerId);
    if (!customer) {
      throw {
        code: 'CUSTOMER_NOT_FOUND',
        message: 'Customer was not found.',
        status: 404,
      };
    }
    return {
      request_id: nextRequestId('req_customer'),
      customer: clone(customer),
    };
  },

  async getCustomerPurchaseHistory(customerId: string) {
    if (!state.customers.find((item) => item.customer_id === customerId)) {
      throw {
        code: 'CUSTOMER_NOT_FOUND',
        message: 'Customer was not found.',
        status: 404,
      };
    }
    return {
      request_id: nextRequestId('req_customer_history'),
      customer_id: customerId,
      transactions: clone(state.purchaseHistory[customerId] ?? []),
    };
  },

  async getDashboardSummary(): Promise<AnalyticsResponse<DashboardSummary>> {
    return getAnalyticsEnvelope<DashboardSummary>({
      summary: clone(MOCK_DASHBOARD_SUMMARY),
    });
  },

  async getSalesTrends(): Promise<AnalyticsResponse<SalesTrendPoint>> {
    return getAnalyticsEnvelope<SalesTrendPoint>({
      points: clone(MOCK_SALES_TRENDS),
    });
  },

  async getProductPerformance(): Promise<AnalyticsResponse<ProductPerformanceItem>> {
    return getAnalyticsEnvelope<ProductPerformanceItem>({
      items: clone(MOCK_PRODUCT_PERFORMANCE),
    });
  },

  async getCustomerInsights(): Promise<AnalyticsResponse<CustomerInsight>> {
    return getAnalyticsEnvelope<CustomerInsight>({
      top_customers: clone(MOCK_CUSTOMER_INSIGHTS),
    });
  },

  async getAlerts(filters: AlertFilters = {}) {
    return {
      request_id: nextRequestId('req_alerts'),
      items: clone(applyAlertFilters(state.alerts, filters)),
    };
  },

  async getAlertsSummary() {
    return {
      request_id: nextRequestId('req_alerts_summary'),
      summary: getAlertsSummarySnapshot(state.alerts),
    };
  },

  async acknowledgeAlert(alertId: string) {
    const alert = state.alerts.find((item) => item.alert_id === alertId);
    if (!alert) {
      throw {
        code: 'ALERT_NOT_FOUND',
        message: 'Alert was not found.',
        status: 404,
      };
    }
    if (alert.status !== 'ACTIVE') {
      throw {
        code: 'INVALID_ALERT_TRANSITION',
        message: 'Only active alerts can be acknowledged.',
        status: 409,
      };
    }
    alert.status = 'ACKNOWLEDGED';
    alert.acknowledged_at = new Date().toISOString();
    alert.acknowledged_by = MOCK_USER.user_id;
    return {
      request_id: nextRequestId('req_alert_ack'),
      alert: clone(alert),
    };
  },

  async resolveAlert(alertId: string) {
    const alert = state.alerts.find((item) => item.alert_id === alertId);
    if (!alert) {
      throw {
        code: 'ALERT_NOT_FOUND',
        message: 'Alert was not found.',
        status: 404,
      };
    }
    if (alert.status === 'RESOLVED') {
      throw {
        code: 'INVALID_ALERT_TRANSITION',
        message: 'Resolved alerts cannot be resolved again.',
        status: 409,
      };
    }
    if (!alert.acknowledged_at) {
      alert.acknowledged_at = new Date().toISOString();
      alert.acknowledged_by = MOCK_USER.user_id;
    }
    alert.status = 'RESOLVED';
    alert.resolved_at = new Date().toISOString();
    alert.resolved_by = MOCK_USER.user_id;
    alert.resolution_note = alert.resolution_note ?? 'Resolved during local demo review.';
    return {
      request_id: nextRequestId('req_alert_resolve'),
      alert: clone(alert),
    };
  },

  async askAI(storeId: string, chatSessionId: string, query: string): Promise<AIChatResponse> {
    const answer = `For ${storeId}, focus first on low stock for Butter Biscuit and the recent demand spike for Rice 5kg.${aiFreshnessNote()}`;
    const now = new Date().toISOString();
    const history = state.chatHistory[chatSessionId] ?? [];
    history.push(
      { role: 'user', text: query, created_at: now },
      { role: 'assistant', text: answer, created_at: now }
    );
    state.chatHistory[chatSessionId] = history;

    return {
      request_id: nextRequestId('req_ai'),
      chat_session_id: chatSessionId,
      analytics_last_updated_at: MOCK_ANALYTICS_LAST_UPDATED_AT,
      freshness_status: 'delayed',
      answer,
      grounding: {
        analytics_used: true,
        alerts_used: ['alert_low_stock_001', 'alert_high_demand_001'],
        inventory_products_used: ['prod_biscuit_01', 'prod_rice_5kg'],
      },
    };
  },

  async getChatSessionHistory(chatSessionId: string) {
    const messages = state.chatHistory[chatSessionId];
    if (!messages) {
      throw {
        code: 'CHAT_SESSION_NOT_FOUND',
        message: 'Chat session was not found.',
        status: 404,
      };
    }
    return {
      request_id: nextRequestId('req_ai_history'),
      chat_session_id: chatSessionId,
      messages: clone(messages),
    };
  },
};
