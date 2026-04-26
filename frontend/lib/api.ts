import axios from 'axios';
import { AUTH_TOKEN_KEY } from './auth-storage';

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
      ? localStorage.getItem(AUTH_TOKEN_KEY)
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
    const apiError = error.response?.data?.error;
    const formattedError = apiError
      ? {
          code: apiError.code || 'UNKNOWN_ERROR',
          message: apiError.message || 'An unknown error occurred.',
          details: apiError.details,
          request_id: error.response?.data?.request_id,
          status: error.response?.status,
        }
      : {
          code: error.response?.status === 404 ? 'NOT_FOUND' : 'UNKNOWN_ERROR',
          message:
            error.response?.data?.detail ||
            error.message ||
            'An unknown error occurred.',
          request_id: error.response?.data?.request_id,
          status: error.response?.status,
        };
    return Promise.reject(formattedError);
  }
);
