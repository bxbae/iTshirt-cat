"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, storeUserId, storedUserId } from "./api";
import type { Me } from "./types";

interface AuthValue {
  user: Me | null;
  ready: boolean;
  login: (id: number) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

/** Demo sign-in: pick one of the seeded customers. The id is sent as X-User-Id on every request. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);

  const refresh = useCallback(async () => {
    if (storedUserId() == null) {
      setUser(null);
      return;
    }
    try {
      setUser(await api.me());
    } catch {
      storeUserId(null);
      setUser(null);
    }
  }, []);

  useEffect(() => {
    refresh().finally(() => setReady(true));
  }, [refresh]);

  const login = useCallback(async (id: number) => {
    storeUserId(id);
    await refresh();
  }, [refresh]);

  const logout = useCallback(() => {
    storeUserId(null);
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, ready, login, logout, refresh }), [user, ready, login, logout, refresh]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
