/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f5f7ff',
          100: '#ebf0ff',
          200: '#d6e0ff',
          300: '#adc2ff',
          400: '#7599ff',
          500: '#3b66f5', // Core brand color
          600: '#2546d9',
          700: '#1c34b8',
          800: '#1b2b94',
          900: '#1a2775',
          950: '#101745',
        },
        dark: {
          50: '#a3a3c2',
          100: '#707099',
          200: '#474766',
          300: '#2a2a40',
          400: '#1e1e2f',
          500: '#141421', // Dark background base
          600: '#0d0d17',
          700: '#08080f',
          800: '#040408',
          900: '#000000',
        }
      },
      fontFamily: {
        sans: ['Outfit', 'Inter', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
