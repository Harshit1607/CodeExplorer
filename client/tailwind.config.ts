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
        // Light theme colors (from reference image)
        light: {
          bg: '#F8FAFC',
          card: '#FFFFFF',
          border: '#E2E8F0',
          text: '#1E293B',
          'text-secondary': '#64748B',
        },
        // Dark theme colors (from reference image)
        dark: {
          bg: '#0F172A',
          card: '#1E293B',
          border: '#334155',
          text: '#F8FAFC',
          'text-secondary': '#94A3B8',
        },
        // Accent colors
        primary: {
          50: '#EEF2FF',
          100: '#E0E7FF',
          200: '#C7D2FE',
          300: '#A5B4FC',
          400: '#818CF8',
          500: '#6366F1',
          600: '#4F46E5',
          700: '#4338CA',
          800: '#3730A3',
          900: '#312E81',
        },
        accent: {
          blue: '#3B82F6',
          indigo: '#6366F1',
          deepblue: '#2563EB',
          green: '#22C55E',
          orange: '#F97316',
          cyan: '#06B6D4',
        },
      },
    },
  },
  plugins: [],
};
export default config;
