/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        pm: {
          bg:      { DEFAULT: '#EDEAE0', dark: '#1E1D17' },
          surface: { DEFAULT: '#F6F3E9', dark: '#262419' },
          border:  { DEFAULT: '#D6D1C2', dark: '#35332A' },
          text:    { DEFAULT: '#2E2C22', dark: '#EDEAE0' },
          muted:   { DEFAULT: '#8C8769', dark: '#8C8769' },
          accent:  { DEFAULT: '#5F7A3F', dark: '#6B8A4A' },
        },
        sev: {
          critical: '#B5482F',
          high:     '#A8782C',
          medium:   '#8C8769',
          low:      '#8C8769',
        },
      },
      borderRadius: {
        card: '7px',
      },
      fontSize: {
        body: ['13px', '1.5'],
        meta: ['11.5px', '1.4'],
        label: ['12px', '1.4'],
      },
    },
  },
  plugins: [],
}
