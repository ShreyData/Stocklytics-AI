'use client';

import React, { createContext, useContext, useEffect, useState } from 'react';
import { signInWithEmailAndPassword, signOut, onIdTokenChanged } from 'firebase/auth';
import { apiService } from '@/lib/api-service';
import { AuthMode, UserProfile } from '@/lib/types';
import { AUTH_TOKEN_KEY } from '@/lib/auth-storage';
import { getFirebaseAuth } from '@/lib/firebase';
import { autoLoginDemo, getAuthMode, getFrontendRuntimeMode } from '@/lib/runtime';

interface AuthContextType {
  user: UserProfile | null;
  storeId: string;
  isAuthenticated: boolean;
  isLoading: boolean;
  authMode: AuthMode;
  loginWithEmailPassword: (email: string, password: string) => Promise<void>;
  loginWithDevMode: () => Promise<void>;
  logout: () => Promise<void>;
  refreshSession: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

async function hydrateBackendSession() {
  const res = await apiService.getMe();
  return res.user;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const authMode = getAuthMode();

  useEffect(() => {
    let unsubscribed = false;

    async function applyMockSession() {
      const runtimeMode = getFrontendRuntimeMode();
      let token = typeof window !== 'undefined' ? localStorage.getItem(AUTH_TOKEN_KEY) : null;
      if (!token && typeof window !== 'undefined') {
        if (runtimeMode === 'backend_stub_auth') {
          localStorage.setItem(AUTH_TOKEN_KEY, 'dev-token');
          token = 'dev-token';
        } else if (runtimeMode === 'mock_api' && autoLoginDemo) {
          localStorage.setItem(AUTH_TOKEN_KEY, 'mock-demo-token');
          token = 'mock-demo-token';
        }
      }
      if (!token) {
        setUser(null);
        setIsLoading(false);
        return;
      }

      try {
        const nextUser = await hydrateBackendSession();
        if (!unsubscribed) {
          setUser(nextUser);
        }
      } catch {
        if (typeof window !== 'undefined') {
          localStorage.removeItem(AUTH_TOKEN_KEY);
        }
        if (!unsubscribed) {
          setUser(null);
        }
      } finally {
        if (!unsubscribed) {
          setIsLoading(false);
        }
      }
    }

    if (authMode === 'mock') {
      void applyMockSession();
      return () => {
        unsubscribed = true;
      };
    }

    const firebase = getFirebaseAuth();
    if (!firebase) {
      setIsLoading(false);
      return () => {
        unsubscribed = true;
      };
    }

    const unsubscribe = onIdTokenChanged(firebase.auth, async (firebaseUser) => {
      if (unsubscribed) {
        return;
      }

      if (!firebaseUser) {
        localStorage.removeItem(AUTH_TOKEN_KEY);
        setUser(null);
        setIsLoading(false);
        return;
      }

      setIsLoading(true);
      try {
        const token = await firebaseUser.getIdToken();
        localStorage.setItem(AUTH_TOKEN_KEY, token);
        const nextUser = await hydrateBackendSession();
        if (!unsubscribed) {
          setUser(nextUser);
        }
      } catch {
        localStorage.removeItem(AUTH_TOKEN_KEY);
        if (!unsubscribed) {
          setUser(null);
        }
      } finally {
        if (!unsubscribed) {
          setIsLoading(false);
        }
      }
    });

    return () => {
      unsubscribed = true;
      unsubscribe();
    };
  }, [authMode]);

  async function refreshSession() {
    if (authMode === 'mock') {
      setIsLoading(true);
      try {
        const nextUser = await hydrateBackendSession();
        setUser(nextUser);
      } finally {
        setIsLoading(false);
      }
      return;
    }

    const firebase = getFirebaseAuth();
    if (!firebase?.auth.currentUser) {
      setUser(null);
      return;
    }

    setIsLoading(true);
    try {
      const token = await firebase.auth.currentUser.getIdToken(true);
      localStorage.setItem(AUTH_TOKEN_KEY, token);
      const nextUser = await hydrateBackendSession();
      setUser(nextUser);
    } finally {
      setIsLoading(false);
    }
  }

  async function loginWithEmailPassword(email: string, password: string) {
    const firebase = getFirebaseAuth();
    if (!firebase) {
      throw new Error('Firebase Auth is not configured for this environment.');
    }

    setIsLoading(true);
    await firebase.persistenceReady;
    await signInWithEmailAndPassword(firebase.auth, email.trim(), password);
  }

  async function loginWithDevMode() {
    localStorage.setItem(AUTH_TOKEN_KEY, 'dev-token');
    setIsLoading(true);
    try {
      const nextUser = await hydrateBackendSession();
      setUser(nextUser);
    } finally {
      setIsLoading(false);
    }
  }

  async function logout() {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    setUser(null);

    if (authMode === 'firebase') {
      const firebase = getFirebaseAuth();
      if (firebase) {
        await signOut(firebase.auth);
      }
    }
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        storeId: user?.store_id || '',
        isAuthenticated: Boolean(user),
        isLoading,
        authMode,
        loginWithEmailPassword,
        loginWithDevMode,
        logout,
        refreshSession,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
