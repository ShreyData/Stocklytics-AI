export const useMocks = process.env.NEXT_PUBLIC_USE_MOCKS === 'true';
export const autoLoginDemo = process.env.NEXT_PUBLIC_AUTO_LOGIN_DEMO === 'true';

function requireEnv(value: string | undefined, name: string) {
  if (!value) {
    throw new Error(`Missing required env var: ${name}`);
  }
  return value;
}

export const firebaseConfig = {
  apiKey: useMocks ? '' : requireEnv(process.env.NEXT_PUBLIC_FIREBASE_API_KEY, 'NEXT_PUBLIC_FIREBASE_API_KEY'),
  authDomain: useMocks ? '' : requireEnv(process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN, 'NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN'),
  projectId: useMocks ? '' : requireEnv(process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID, 'NEXT_PUBLIC_FIREBASE_PROJECT_ID'),
  storageBucket: useMocks ? '' : requireEnv(process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET, 'NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET'),
  messagingSenderId: useMocks ? '' : requireEnv(process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID, 'NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID'),
  appId: useMocks ? '' : requireEnv(process.env.NEXT_PUBLIC_FIREBASE_APP_ID, 'NEXT_PUBLIC_FIREBASE_APP_ID'),
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
