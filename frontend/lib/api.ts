import axios from 'axios';

const baseURL = process.env.NEXT_PUBLIC_API_BASE_URL || '/api/v1';

export const apiClient = axios.create({
  baseURL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add a request interceptor to inject the auth token
apiClient.interceptors.request.use(
  (config) => {
    const token = typeof window !== 'undefined'
      ? localStorage.getItem('auth_token')
      : null;
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Add a response interceptor for standardized error formatting
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // Standardized error formatting based on the API contract
    const formattedError = error.response?.data?.error || {
      code: error.response?.status === 404 ? 'NOT_FOUND' : 'UNKNOWN_ERROR',
      message: error.response?.data?.detail || error.message || 'An unknown error occurred.',
      request_id: error.response?.data?.request_id,
    };
    return Promise.reject(formattedError);
  }
);
