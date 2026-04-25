import { ApiError } from './types';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

export function normalizeApiError(error: unknown): ApiError {
  if (isRecord(error)) {
    const code = typeof error.code === 'string' ? error.code : 'UNKNOWN_ERROR';
    const message =
      typeof error.message === 'string'
        ? error.message
        : 'An unexpected error occurred.';
    const details = isRecord(error.details) ? error.details : undefined;
    const request_id =
      typeof error.request_id === 'string' ? error.request_id : undefined;
    const status = typeof error.status === 'number' ? error.status : undefined;
    return { code, message, details, request_id, status };
  }

  if (error instanceof Error) {
    return {
      code: 'UNKNOWN_ERROR',
      message: error.message || 'An unexpected error occurred.',
    };
  }

  return {
    code: 'UNKNOWN_ERROR',
    message: 'An unexpected error occurred.',
  };
}

export function getErrorMessage(
  error: unknown,
  fallback = 'Something went wrong. Please try again.'
): string {
  const normalized = normalizeApiError(error);
  return normalized.message || fallback;
}

export function getBillingFailureMessage(error: unknown): string {
  const normalized = normalizeApiError(error);
  if (normalized.code !== 'INSUFFICIENT_STOCK') {
    return normalized.message || 'Billing failed. You can safely retry.';
  }

  const failedItems = normalized.details?.failed_items;
  if (!Array.isArray(failedItems) || failedItems.length === 0) {
    return normalized.message || 'Billing failed due to insufficient stock.';
  }

  const details = failedItems
    .map((item) => {
      if (!isRecord(item)) return null;
      const productId =
        typeof item.product_id === 'string' ? item.product_id : 'unknown_product';
      const requested =
        typeof item.requested_quantity === 'number'
          ? item.requested_quantity
          : typeof item.quantity === 'number'
            ? item.quantity
            : undefined;
      const available =
        typeof item.available_quantity === 'number' ? item.available_quantity : undefined;
      if (requested !== undefined && available !== undefined) {
        return `${productId} (requested ${requested}, available ${available})`;
      }
      return productId;
    })
    .filter(Boolean)
    .join(', ');

  if (!details) {
    return normalized.message || 'Billing failed due to insufficient stock.';
  }

  return `Insufficient stock for: ${details}.`;
}
