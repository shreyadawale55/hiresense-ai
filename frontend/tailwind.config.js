/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        display: ['Space Grotesk', 'Inter', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        glow: '0 0 24px rgba(99, 102, 241, 0.3)',
      },
      backgroundImage: {
        'hero-radial': 'radial-gradient(circle at top, rgba(99,102,241,0.18), transparent 55%)',
      },
    },
  },
  plugins: [],
}

