'use client';

import React, { createContext, useContext, useState, useEffect } from 'react';

interface AuthContextType {
  storeId: string;
  setStoreId: (id: string) => void;
  isAuthenticated: boolean;
  login: (token: string, storeId: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [storeId, setStoreId] = useState<string>(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('store_id') || 'store_001';
    }
    return 'store_001';
  });
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(true);

  useEffect(() => {
    // Auto-set dev-token for local development.
    // The backend accepts "dev-token" as a valid Bearer token
    // in local environments (see backend/app/common/auth.py).
    if (typeof window !== 'undefined') {
      const existingToken = localStorage.getItem('auth_token');
      if (!existingToken) {
        localStorage.setItem('auth_token', 'dev-token');
      }
      const existingStore = localStorage.getItem('store_id');
      if (!existingStore) {
        localStorage.setItem('store_id', 'store_001');
      }
    }
  }, []);

  const login = (token: string, newStoreId: string) => {
    localStorage.setItem('auth_token', token);
    localStorage.setItem('store_id', newStoreId);
    setStoreId(newStoreId);
    setIsAuthenticated(true);
  };

  const logout = () => {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('store_id');
    setIsAuthenticated(false);
  };

  return (
    <AuthContext.Provider value={{ storeId, setStoreId, isAuthenticated, login, logout }}>
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
