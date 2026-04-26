const DATA_CHANGED_EVENT = 'stocklytics:data-changed';

export type DataChangedDetail = {
  source: 'inventory' | 'billing' | 'alerts' | 'customers';
};

export function emitDataChanged(detail: DataChangedDetail) {
  if (typeof window === 'undefined') {
    return;
  }
  window.dispatchEvent(new CustomEvent<DataChangedDetail>(DATA_CHANGED_EVENT, { detail }));
}

export function subscribeToDataChanged(callback: () => void) {
  if (typeof window === 'undefined') {
    return () => {};
  }

  const handler = () => callback();
  window.addEventListener(DATA_CHANGED_EVENT, handler);
  return () => window.removeEventListener(DATA_CHANGED_EVENT, handler);
}
