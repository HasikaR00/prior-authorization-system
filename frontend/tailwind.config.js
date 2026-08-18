/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        navy: {
          900: '#0B132B',
          800: '#1C2541',
          700: '#2A365B',
        },
        brand: {
          500: '#2563EB',
          600: '#1D4ED8',
          700: '#1E40AF',
        }
      }
    },
  },
  plugins: [],
}
