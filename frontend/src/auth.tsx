import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { api, tokens, type Json } from './api';
import { setLanguage } from './i18n';

interface AuthState {
  user: Json | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  isCurator: boolean;
  isAdmin: boolean;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Json | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!tokens.access) {
      setLoading(false);
      return;
    }
    api
      .get('/auth/me')
      .then((u) => setUser(u))
      .catch(() => tokens.clear())
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const onLogout = () => setUser(null);
    window.addEventListener('auth:logout', onLogout);
    return () => window.removeEventListener('auth:logout', onLogout);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const d = await api.post('/auth/login', { username, password });
    tokens.set(d.access_token, d.refresh_token);
    setUser(d.user);
    if (!localStorage.getItem('uh_lang') && d.user?.locale) setLanguage(d.user.locale);
  }, []);

  const logout = useCallback(() => {
    tokens.clear();
    setUser(null);
  }, []);

  const role = user?.role;
  return (
    <Ctx.Provider value={{ user, loading, login, logout, isCurator: role === 'curator' || role === 'admin', isAdmin: role === 'admin' }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error('useAuth outside provider');
  return c;
}
