import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Light theme colors
        light: {
          bg: '#FAFAFA',
          card: '#FFFFFF',
          border: '#E4E4E7',
          text: '#000000',
          'text-secondary': '#52525B',
        },
        // Dark theme colors
        dark: {
          bg: '#050505',
          card: '#18181B',
          border: '#27272A',
          text: '#FAFAFA',
          'text-secondary': '#A1A1AA',
        },
        // Accent colors (monochrome scale)
        primary: {
          50: '#fafafa',
          100: '#f4f4f5',
          200: '#e4e4e7',
          300: '#d4d4d8',
          400: '#a1a1aa',
          500: '#71717a',
          600: '#52525b',
          700: '#3f3f46',
          800: '#27272a',
          900: '#18181b',
        },
        accent: {
          blue: '#52525B',
          indigo: '#52525B',
          deepblue: '#3F3F46',
          green: '#71717A',
          orange: '#52525B',
          cyan: '#A1A1AA',
        },
      },
    },
  },
  plugins: [],
};
export default config;
