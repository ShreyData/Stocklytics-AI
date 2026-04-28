import axios from 'axios';
import { AUTH_TOKEN_KEY } from './auth-storage';
import { getFirebaseAuth } from './firebase';

const baseURL = process.env.NEXT_PUBLIC_API_BASE_URL;

if (!baseURL) {
  throw new Error('Missing required env var: NEXT_PUBLIC_API_BASE_URL');
}

export const apiClient = axios.create({
  baseURL,
  headers: {
    'Content-Type': 'application/json',
  },
});

async function resolveAuthToken() {
  if (typeof window === 'undefined') {
    return null;
  }

  const cachedToken = localStorage.getItem(AUTH_TOKEN_KEY);
  if (cachedToken) {
    return cachedToken;
  }

  const firebase = getFirebaseAuth();
  const firebaseUser = firebase?.auth.currentUser;
  if (!firebaseUser) {
    return null;
  }

  const token = await firebaseUser.getIdToken();
  localStorage.setItem(AUTH_TOKEN_KEY, token);
  return token;
}

// Add a request interceptor to inject the auth token
apiClient.interceptors.request.use(
  async (config) => {
    const token = await resolveAuthToken();
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
