import { createContext, useContext, useEffect, useMemo, useState } from 'react'

const ThemeContext = createContext(null)
const STORAGE_KEY = 'hiresense.theme'
const hasStorage = typeof window !== 'undefined' && typeof window.localStorage !== 'undefined'

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => (hasStorage ? localStorage.getItem(STORAGE_KEY) : null) || 'dark')

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    if (hasStorage) {
      localStorage.setItem(STORAGE_KEY, theme)
    }
  }, [theme])

  const value = useMemo(() => ({
    theme,
    setTheme,
    toggleTheme: () => setTheme((current) => (current === 'dark' ? 'light' : 'dark')),
  }), [theme])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within ThemeProvider')
  }
  return context
}
