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
  Transaction,
} from './types';
import {
  MOCK_AI_HISTORY,
  MOCK_ALERTS,
  MOCK_ANALYTICS_LAST_UPDATED_AT,
  MOCK_CUSTOMERS,
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

const LOW_STOCK_ALERT = 'LOW_STOCK';
const EXPIRY_SOON_ALERT = 'EXPIRY_SOON';

function computeExpiryStatus(expiryDate: string | null): Product['expiry_status'] {
  if (!expiryDate) {
    return 'OK';
  }

  const now = new Date();
  const expiry = new Date(expiryDate);
  if (Number.isNaN(expiry.getTime())) {
    return 'OK';
  }

  const msRemaining = expiry.getTime() - now.getTime();
  const daysRemaining = msRemaining / (1000 * 60 * 60 * 24);
  if (daysRemaining < 0) {
    return 'EXPIRED';
  }
  if (daysRemaining <= 7) {
    return 'EXPIRING_SOON';
  }
  return 'OK';
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

const state = {
  products: clone(MOCK_PRODUCTS),
  customers: clone(MOCK_CUSTOMERS),
  purchaseHistory: clone(MOCK_PURCHASE_HISTORY),
  alerts: clone(MOCK_ALERTS),
  chatHistory: clone(MOCK_AI_HISTORY) as Record<string, ChatHistoryMessage[]>,
  transactions: [] as Transaction[],
  transactionsByKey: new Map<string, BillingCreateResponse>(),
  analyticsLastUpdatedAt: MOCK_ANALYTICS_LAST_UPDATED_AT,
};

function reevaluateDerivedState() {
  const now = new Date().toISOString();

  for (const product of state.products) {
    product.expiry_status = computeExpiryStatus(product.expiry_date);
  }

  for (const product of state.products) {
    const lowStockConditionKey = `${product.store_id}:LOW_STOCK:${product.product_id}`;
    const lowStockAlert = state.alerts.find((alert) => alert.condition_key === lowStockConditionKey);
    const isLowStock =
      product.expiry_status !== 'EXPIRED' &&
      product.quantity_on_hand <= product.reorder_threshold;

    if (isLowStock) {
      const severity = product.quantity_on_hand === 0 ? 'CRITICAL' : 'HIGH';
      if (lowStockAlert) {
        lowStockAlert.title = `Low Stock: ${product.name}`;
        lowStockAlert.message = `Stock is below reorder threshold for ${product.name}. ${product.quantity_on_hand} units left against threshold ${product.reorder_threshold}.`;
        lowStockAlert.severity = severity;
        lowStockAlert.source_entity_id = product.product_id;
        if (lowStockAlert.status === 'RESOLVED') {
          lowStockAlert.status = 'ACTIVE';
          lowStockAlert.acknowledged_at = null;
          lowStockAlert.acknowledged_by = null;
          lowStockAlert.resolved_at = null;
          lowStockAlert.resolved_by = null;
          lowStockAlert.resolution_note = null;
          lowStockAlert.created_at = now;
        }
      } else {
        state.alerts.unshift({
          alert_id: `alert_low_stock_${product.product_id}`,
          store_id: product.store_id,
          alert_type: LOW_STOCK_ALERT,
          status: 'ACTIVE',
          severity,
          title: `Low Stock: ${product.name}`,
          message: `Stock is below reorder threshold for ${product.name}. ${product.quantity_on_hand} units left against threshold ${product.reorder_threshold}.`,
          created_at: now,
          condition_key: lowStockConditionKey,
          source_entity_id: product.product_id,
        });
      }
    } else if (lowStockAlert && lowStockAlert.status !== 'RESOLVED') {
      lowStockAlert.status = 'RESOLVED';
      lowStockAlert.resolved_at = now;
      lowStockAlert.resolved_by = 'system';
      lowStockAlert.resolution_note = `Stock recovered above reorder threshold for ${product.name}.`;
    }

    const expiryConditionKey = `${product.store_id}:EXPIRY_SOON:${product.product_id}`;
    const expiryAlert = state.alerts.find((alert) => alert.condition_key === expiryConditionKey);
    const hasExpiryRisk =
      product.quantity_on_hand > 0 &&
      (product.expiry_status === 'EXPIRING_SOON' || product.expiry_status === 'EXPIRED');

    if (hasExpiryRisk) {
      const isExpired = product.expiry_status === 'EXPIRED';
      const severity = isExpired ? 'HIGH' : 'MEDIUM';
      const message = isExpired
        ? `${product.name} is expired and still has ${product.quantity_on_hand} units in stock.`
        : `${product.name} will expire soon and still has ${product.quantity_on_hand} units in stock.`;

      if (expiryAlert) {
        expiryAlert.title = `${isExpired ? 'Expired' : 'Expiry Soon'}: ${product.name}`;
        expiryAlert.message = message;
        expiryAlert.severity = severity;
        expiryAlert.source_entity_id = product.product_id;
        if (expiryAlert.status === 'RESOLVED') {
          expiryAlert.status = 'ACTIVE';
          expiryAlert.acknowledged_at = null;
          expiryAlert.acknowledged_by = null;
          expiryAlert.resolved_at = null;
          expiryAlert.resolved_by = null;
          expiryAlert.resolution_note = null;
          expiryAlert.created_at = now;
        }
      } else {
        state.alerts.unshift({
          alert_id: `alert_expiry_${product.product_id}`,
          store_id: product.store_id,
          alert_type: EXPIRY_SOON_ALERT,
          status: 'ACTIVE',
          severity,
          title: `${isExpired ? 'Expired' : 'Expiry Soon'}: ${product.name}`,
          message,
          created_at: now,
          condition_key: expiryConditionKey,
          source_entity_id: product.product_id,
        });
      }
    } else if (expiryAlert && expiryAlert.status !== 'RESOLVED') {
      expiryAlert.status = 'RESOLVED';
      expiryAlert.resolved_at = now;
      expiryAlert.resolved_by = 'system';
      expiryAlert.resolution_note = `Expiry risk cleared for ${product.name}.`;
    }
  }
}

function markAnalyticsUpdated() {
  state.analyticsLastUpdatedAt = new Date().toISOString();
}

function getProductPerformanceSnapshot(): ProductPerformanceItem[] {
  const performance = new Map(
    MOCK_PRODUCT_PERFORMANCE.map((item) => [
      item.product_id,
      {
        product_id: item.product_id,
        product_name: item.product_name,
        quantity_sold: item.quantity_sold,
        revenue: item.revenue,
      },
    ])
  );

  for (const transaction of state.transactions) {
    for (const item of transaction.items ?? []) {
      const product = state.products.find((candidate) => candidate.product_id === item.product_id);
      const existing = performance.get(item.product_id);
      if (existing) {
        existing.quantity_sold += item.quantity;
        existing.revenue += item.line_total;
      } else {
        performance.set(item.product_id, {
          product_id: item.product_id,
          product_name: product?.name ?? item.product_id,
          quantity_sold: item.quantity,
          revenue: item.line_total,
        });
      }
    }
  }

  return Array.from(performance.values()).sort((a, b) => {
    if (b.revenue !== a.revenue) {
      return b.revenue - a.revenue;
    }
    return b.quantity_sold - a.quantity_sold;
  });
}

function getSalesTrendsSnapshot(): SalesTrendPoint[] {
  const points = new Map(
    MOCK_SALES_TRENDS.map((point) => [
      point.label,
      {
        label: point.label,
        sales_amount: point.sales_amount,
        transactions: point.transactions,
      },
    ])
  );

  for (const transaction of state.transactions) {
    if (!transaction.sale_timestamp) {
      continue;
    }
    const label = transaction.sale_timestamp.slice(0, 10);
    const point = points.get(label);
    if (point) {
      point.sales_amount += transaction.total_amount;
      point.transactions += 1;
    } else {
      points.set(label, {
        label,
        sales_amount: transaction.total_amount,
        transactions: 1,
      });
    }
  }

  return Array.from(points.values()).sort((a, b) => a.label.localeCompare(b.label));
}

function getCustomerInsightsSnapshot(): CustomerInsight[] {
  return clone(state.customers)
    .sort((a, b) => {
      if (b.total_spend !== a.total_spend) {
        return b.total_spend - a.total_spend;
      }
      return b.visit_count - a.visit_count;
    })
    .map((customer) => ({
      customer_id: customer.customer_id,
      name: customer.name,
      lifetime_spend: customer.total_spend,
      visit_count: customer.visit_count,
    }));
}

function getDashboardSummarySnapshot(): DashboardSummary {
  const todayLabel = new Date().toISOString().slice(0, 10);
  const salesToday = getSalesTrendsSnapshot().find((point) => point.label === todayLabel);
  const productPerformance = getProductPerformanceSnapshot();

  return {
    today_sales: salesToday?.sales_amount ?? 0,
    today_transactions: salesToday?.transactions ?? 0,
    active_alert_count: state.alerts.filter((alert) => alert.status === 'ACTIVE').length,
    low_stock_count: state.products.filter(
      (product) => product.status === 'ACTIVE' && product.quantity_on_hand <= product.reorder_threshold
    ).length,
    top_selling_product: productPerformance[0]?.product_name ?? null,
  };
}

export function resetMockState() {
  state.products = clone(MOCK_PRODUCTS);
  state.customers = clone(MOCK_CUSTOMERS);
  state.purchaseHistory = clone(MOCK_PURCHASE_HISTORY);
  state.alerts = clone(MOCK_ALERTS);
  state.chatHistory = clone(MOCK_AI_HISTORY) as Record<string, ChatHistoryMessage[]>;
  state.transactions = [];
  state.transactionsByKey = new Map<string, BillingCreateResponse>();
  state.analyticsLastUpdatedAt = MOCK_ANALYTICS_LAST_UPDATED_AT;
  reevaluateDerivedState();
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
    analytics_last_updated_at: state.analyticsLastUpdatedAt,
    freshness_status: 'fresh' as const,
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

function queryIncludes(query: string, terms: string[]) {
  const lowered = query.toLowerCase();
  return terms.some((term) => lowered.includes(term));
}

function buildMockAssistantAnswer(storeId: string, query: string) {
  const dashboard = getDashboardSummarySnapshot();
  const activeAlerts = state.alerts.filter((alert) => alert.status === 'ACTIVE');
  const activeProducts = state.products.filter((product) => product.status === 'ACTIVE');
  const lowStockProducts = activeProducts.filter(
    (product) => product.quantity_on_hand <= product.reorder_threshold
  );
  const riskProducts = activeProducts.filter((product) =>
    product.expiry_status === 'EXPIRED' ||
    product.expiry_status === 'EXPIRING_SOON' ||
    product.quantity_on_hand <= product.reorder_threshold
  );

  if (queryIncludes(query, ['new product', 'recent product', 'added in inventory', 'added to inventory'])) {
    const newest = [...activeProducts].sort((left, right) =>
      new Date(right.created_at ?? 0).getTime() - new Date(left.created_at ?? 0).getTime()
    )[0];
    if (!newest) {
      return `I could not find a recent product addition for ${storeId}.`;
    }
    return `${newest.name} is the newest product in inventory. It is in ${newest.category}, priced at ${newest.price}, and currently has ${newest.quantity_on_hand} units on hand.`;
  }

  if (queryIncludes(query, ['what needs attention', 'focus', 'priority', 'inventory status', 'current inventory status'])) {
    const topRisk = riskProducts[0];
    const topAlert = activeAlerts[0];
    const parts = [
      `For ${storeId}, ${lowStockProducts.length} products are at or below reorder threshold and ${riskProducts.filter((product) => product.expiry_status !== 'OK').length} have expiry risk.`,
    ];
    if (topAlert) {
      parts.push(`Your top alert is ${topAlert.title}.`);
    }
    if (topRisk) {
      parts.push(`${topRisk.name} is the most urgent inventory item with ${topRisk.quantity_on_hand} units left and status ${topRisk.expiry_status.toLowerCase()}.`);
    }
    parts.push('Best next move is to restock the weakest items first and clear expired inventory from sale.');
    return parts.join(' ');
  }

  if (queryIncludes(query, ['best customers', 'top customers', 'loyal customers', 'my customers', 'customer'])) {
    const topCustomers = [...state.customers]
      .sort((left, right) => {
        if (right.total_spend !== left.total_spend) {
          return right.total_spend - left.total_spend;
        }
        return right.visit_count - left.visit_count;
      })
      .slice(0, 3);

    if (topCustomers.length === 0) {
      return `I could not find customer records for ${storeId} right now.`;
    }

    return `Your top customers right now are ${topCustomers
      .map((customer) => `${customer.name} (${customer.total_spend} spend, ${customer.visit_count} visits)`)
      .join(', ')}. Best next move is to keep these repeat buyers engaged with stock updates or bundle offers.`;
  }

  if (queryIncludes(query, ['sales', 'sale', 'revenue', 'transactions'])) {
    return `Today's sales are ${dashboard.today_sales} across ${dashboard.today_transactions} transactions. ${dashboard.top_selling_product ?? 'Your top product'} is leading today, so protect its stock cover.`;
  }

  const topAlert = activeAlerts.find((alert) => alert.status !== 'RESOLVED');
  const topProduct = dashboard.top_selling_product ?? 'your fastest moving product';
  return topAlert
    ? `For ${storeId}, focus first on ${topAlert.title.toLowerCase()} and keep an eye on ${topProduct}.`
    : `For ${storeId}, inventory looks stable right now. Keep an eye on ${topProduct}.`;
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
    reevaluateDerivedState();
    markAnalyticsUpdated();
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
    product.expiry_status = computeExpiryStatus(product.expiry_date);
    reevaluateDerivedState();
    markAnalyticsUpdated();
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
    reevaluateDerivedState();
    markAnalyticsUpdated();

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
    state.transactions.unshift(clone(transaction));
    state.transactionsByKey.set(data.idempotency_key, clone(response));
    reevaluateDerivedState();
    markAnalyticsUpdated();
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
      summary: getDashboardSummarySnapshot(),
    });
  },

  async getSalesTrends(): Promise<AnalyticsResponse<SalesTrendPoint>> {
    return getAnalyticsEnvelope<SalesTrendPoint>({
      points: getSalesTrendsSnapshot(),
    });
  },

  async getProductPerformance(): Promise<AnalyticsResponse<ProductPerformanceItem>> {
    return getAnalyticsEnvelope<ProductPerformanceItem>({
      items: getProductPerformanceSnapshot(),
    });
  },

  async getCustomerInsights(): Promise<AnalyticsResponse<CustomerInsight>> {
    return getAnalyticsEnvelope<CustomerInsight>({
      top_customers: getCustomerInsightsSnapshot(),
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
    const answer = buildMockAssistantAnswer(storeId, query);
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
      analytics_last_updated_at: state.analyticsLastUpdatedAt,
      freshness_status: 'fresh',
      answer,
      grounding: {
        analytics_used: true,
        alerts_used: state.alerts
          .filter((alert) => alert.status !== 'RESOLVED')
          .slice(0, 3)
          .map((alert) => alert.alert_id),
        inventory_products_used: state.products
          .filter((product) => product.quantity_on_hand <= product.reorder_threshold)
          .slice(0, 3)
          .map((product) => product.product_id),
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

resetMockState();
