export const useMocks = process.env.NEXT_PUBLIC_USE_MOCKS === 'true';

export const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY || '',
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN || '',
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID || '',
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET || '',
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID || '',
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID || '',
};

export function hasFirebaseConfig() {
  return Boolean(
    firebaseConfig.apiKey &&
      firebaseConfig.authDomain &&
      firebaseConfig.projectId &&
      firebaseConfig.appId
  );
}

export function getAuthMode() {
  return useMocks || !hasFirebaseConfig() ? 'mock' : 'firebase';
}

export function getFrontendRuntimeMode() {
  if (useMocks) {
    return 'mock_api';
  }
  if (hasFirebaseConfig()) {
    return 'firebase';
  }
  return 'backend_stub_auth';
}
