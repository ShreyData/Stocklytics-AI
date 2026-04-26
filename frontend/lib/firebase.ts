'use client';

import { initializeApp, getApps } from 'firebase/app';
import { browserLocalPersistence, getAuth, setPersistence } from 'firebase/auth';
import { firebaseConfig, getAuthMode } from './runtime';

let persistenceReady: Promise<void> | null = null;

export function getFirebaseAuth() {
  if (getAuthMode() !== 'firebase') {
    return null;
  }

  const app = getApps()[0] ?? initializeApp(firebaseConfig);
  const auth = getAuth(app);

  if (!persistenceReady) {
    persistenceReady = setPersistence(auth, browserLocalPersistence).then(() => undefined);
  }

  return { auth, persistenceReady };
}
