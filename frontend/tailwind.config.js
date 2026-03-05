/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#e8f4fb',
          100: '#d1e9f7',
          500: '#0E76A8',
          600: '#0c6494',
          700: '#0a5280',
          900: '#1B3A6B',
        },
      },
    },
  },
  plugins: [],
}
