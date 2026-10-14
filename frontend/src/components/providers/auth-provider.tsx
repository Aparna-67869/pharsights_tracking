"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, clearToken, getToken } from "@/lib/api";

export interface SessionUser {
  username: string;
  role: string;
  permissions: string[];
  can_create_accounts: boolean;
  allowed_login_email: string | null;
}

interface AuthContextValue {
  user: SessionUser | null;
  loading: boolean;
  error: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  hasScope: (scope: string) => boolean;
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = React.useState<SessionUser | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      setUser(await api.me());
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) clearToken();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  const login = React.useCallback(
    async (username: string, password: string) => {
      setError(null);
      try {
        await api.login(username, password);
        const me = await api.me();
        setUser(me);
        router.push("/");
      } catch (err) {
        const message = err instanceof ApiError ? err.message : "Sign-in failed";
        setError(message);
        throw err;
      }
    },
    [router],
  );

  const logout = React.useCallback(() => {
    clearToken();
    setUser(null);
    router.push("/login");
  }, [router]);

  const hasScope = React.useCallback(
    (scope: string) => {
      if (!user) return false;
      const scopes = user.permissions;
      if (scopes.includes("*") || scopes.includes(scope)) return true;
      const ns = scope.split(":")[0];
      return scopes.includes(`${ns}:*`);
    },
    [user],
  );

  const value = React.useMemo(
    () => ({ user, loading, error, login, logout, hasScope }),
    [user, loading, error, login, logout, hasScope],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = React.useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
