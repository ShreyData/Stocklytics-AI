'use client';

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { apiService } from '@/lib/api-service';
import { UserProfile } from '@/lib/types';

const AUTH_TOKEN_KEY = 'auth_token';

interface AuthContextType {
  user: UserProfile | null;
  storeId: string;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (token: string) => Promise<void>;
  logout: () => void;
  refreshSession: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const hydrateSession = useCallback(async (options?: { throwOnError?: boolean }) => {
    const token = typeof window !== 'undefined' ? localStorage.getItem(AUTH_TOKEN_KEY) : null;
    if (!token) {
      setUser(null);
      setIsLoading(false);
      return;
    }

    try {
      const res = await apiService.getMe();
      setUser(res.user);
    } catch (error) {
      if (typeof window !== 'undefined') {
        localStorage.removeItem(AUTH_TOKEN_KEY);
      }
      setUser(null);
      if (options?.throwOnError) {
        throw error;
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    hydrateSession();
  }, [hydrateSession]);

  const login = useCallback(async (token: string) => {
    if (!token.trim()) {
      throw new Error('Token is required.');
    }
    setIsLoading(true);
    localStorage.setItem(AUTH_TOKEN_KEY, token.trim());
    await hydrateSession({ throwOnError: true });
  }, [hydrateSession]);

  const logout = useCallback(() => {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    setUser(null);
    setIsLoading(false);
  }, []);

  const value = useMemo<AuthContextType>(() => ({
    user,
    storeId: user?.store_id || '',
    isAuthenticated: Boolean(user),
    isLoading,
    login,
    logout,
    refreshSession: hydrateSession,
  }), [user, isLoading, login, logout, hydrateSession]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
