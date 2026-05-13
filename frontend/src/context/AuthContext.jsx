import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import { authApi, clearStoredAuth, getStoredAuth, setStoredAuth } from '../services/api.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [accessToken, setAccessToken] = useState(null)
  const [refreshToken, setRefreshToken] = useState(null)
  const [hydrated, setHydrated] = useState(false)

  useEffect(() => {
    const stored = getStoredAuth()
    if (stored.accessToken && stored.refreshToken) {
      setUser(stored.user)
      setAccessToken(stored.accessToken)
      setRefreshToken(stored.refreshToken)
      authApi.me()
        .then((res) => {
          const currentUser = res.data.user
          setUser(currentUser)
          setStoredAuth({ accessToken: stored.accessToken, refreshToken: stored.refreshToken, user: currentUser })
        })
        .catch(() => {
          clearStoredAuth()
          setUser(null)
          setAccessToken(null)
          setRefreshToken(null)
        })
        .finally(() => setHydrated(true))
    } else {
      setHydrated(true)
    }
  }, [])

  const login = async (email, password) => {
    const res = await authApi.login({ email, password })
    const { access_token: access, refresh_token: refresh, user: nextUser } = res.data
    setUser(nextUser)
    setAccessToken(access)
    setRefreshToken(refresh)
    setStoredAuth({ accessToken: access, refreshToken: refresh, user: nextUser })
    toast.success(`Welcome back, ${nextUser.full_name || nextUser.email}`)
    return nextUser
  }

  const logout = async () => {
    try {
      await authApi.logout(refreshToken)
    } catch {
      // Ignore logout errors and clear locally
    }
    clearStoredAuth()
    setUser(null)
    setAccessToken(null)
    setRefreshToken(null)
    toast.success('Signed out')
  }

  const value = useMemo(() => ({
    user,
    accessToken,
    refreshToken,
    hydrated,
    isAuthenticated: Boolean(user && accessToken),
    login,
    logout,
  }), [user, accessToken, refreshToken, hydrated])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}

