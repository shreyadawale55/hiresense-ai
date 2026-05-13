import { RiMoonLine, RiSunLine } from 'react-icons/ri'
import { useTheme } from '../context/ThemeContext.jsx'

export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  return (
    <button type="button" className="btn btn-secondary btn-sm" onClick={toggleTheme}>
      {theme === 'dark' ? <RiSunLine /> : <RiMoonLine />}
      {theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
    </button>
  )
}

