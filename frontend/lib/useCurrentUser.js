'use client';

import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { me } from './api';
import { canAccess } from './permissions';

const CurrentUserContext = createContext({ user: null, loaded: false, can: () => false });

export function CurrentUserProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let active = true;
    me()
      .then((row) => {
        if (!active) return;
        setUser(row || null);
      })
      .catch(() => {
        if (!active) return;
        setUser(null);
      })
      .finally(() => {
        if (!active) return;
        setLoaded(true);
      });
    return () => {
      active = false;
    };
  }, []);

  const value = useMemo(() => ({
    user,
    loaded,
    can: (key) => canAccess(user, key),
  }), [user, loaded]);

  return <CurrentUserContext.Provider value={value}>{children}</CurrentUserContext.Provider>;
}

export function useCurrentUser() {
  return useContext(CurrentUserContext);
}
