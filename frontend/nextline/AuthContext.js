import { createContext, useContext, useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { fetchJson } from './api';

const AuthContext = createContext();

export function AuthProvider({ children }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);
  // The rider's account, including crash-alert contact. Null until loaded.
  const [user, setUser] = useState(null);

  useEffect(() => {
    AsyncStorage.getItem('access').then((token) => {
      setIsAuthenticated(Boolean(token));
      setLoading(false);
    });
  }, []);

  const login = async ({ access, refresh }) => {
    await AsyncStorage.multiSet([['access', access], ['refresh', refresh]]);
    setIsAuthenticated(true);
  };

  const logout = async () => {
    await AsyncStorage.multiRemove(['access', 'refresh']);
    setIsAuthenticated(false);
    setUser(null);
  };

  const refreshUser = async () => {
    try {
      setUser(await fetchJson('/api/user/me/', { logout }));
    } catch {
      // Offline at the trailhead is normal; screens cope with a missing user.
    }
  };

  useEffect(() => {
    if (isAuthenticated) refreshUser();
  }, [isAuthenticated]);

  const value = { isAuthenticated, user, setUser, refreshUser, login, logout };
  return <AuthContext.Provider value={value}>{!loading && children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
