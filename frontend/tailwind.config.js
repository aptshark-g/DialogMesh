/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // === 品牌色 ===
        primary: {
          DEFAULT: '#D97706',
          light: '#F59E0B',
          dark: '#B45309',
          subtle: 'rgba(217, 119, 6, 0.10)',
        },
        // === 辅助色 ===
        teal: '#0D9488',
        rose: '#E11D48',
        slate: '#64748B',
        emerald: '#10B981',
        blue: '#3B82F6',
        // === 暗色模式背景层级 ===
        surface: {
          DEFAULT: '#0C0A0F',
          sidebar: '#121018',
          card: '#1A1724',
          'card-hover': '#252134',
          'card-active': '#312E40',
          input: '#1A1724',
          overlay: 'rgba(0, 0, 0, 0.6)',
        },
        // === 文字色 ===
        text: {
          primary: '#E8E6F0',
          secondary: '#A9A5B8',
          muted: '#6B6680',
          ai: '#F59E0B',
        },
        // === 边框色 ===
        border: {
          subtle: '#2A2635',
          medium: '#3A3548',
          strong: '#4A4560',
        },
        // === 状态色 ===
        status: {
          success: '#10B981',
          warning: '#F59E0B',
          error: '#EF4444',
          info: '#3B82F6',
          pending: '#6B6680',
          processing: '#8B5CF6',
        },
        // === 意图类型色 ===
        intent: {
          'scan-memory': '#D97706',
          'read-memory': '#0D9488',
          'write-memory': '#8B5CF6',
          'hack-value': '#E11D48',
          'explain': '#3B82F6',
          'provide-code': '#10B981',
          'unknown': '#6B6680',
        },
        // === 亮色模式 (fallback) ===
        'light-surface': {
          main: '#FDFCF8',
          sidebar: '#F5F0E8',
          card: '#FFFFFF',
          'card-hover': '#F3F0EB',
          'card-active': '#FEF3C7',
        },
      },
      fontFamily: {
        sans: ['Inter', 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Consolas', 'monospace'],
      },
      fontSize: {
        'xs': ['12px', '16px'],
        'sm': ['14px', '20px'],
        'base': ['15px', '22px'],
        'lg': ['16px', '24px'],
        'xl': ['18px', '28px'],
        '2xl': ['20px', '30px'],
        '3xl': ['28px', '36px'],
        '4xl': ['36px', '44px'],
      },
      spacing: {
        '18': '4.5rem',
        '22': '5.5rem',
        '30': '7.5rem',
      },
      borderRadius: {
        'sm': '4px',
        'md': '8px',
        'lg': '12px',
        'xl': '16px',
      },
      boxShadow: {
        'card': '0 1px 3px rgba(0, 0, 0, 0.3), 0 1px 2px rgba(0, 0, 0, 0.2)',
        'card-hover': '0 4px 12px rgba(0, 0, 0, 0.4), 0 2px 4px rgba(0, 0, 0, 0.3)',
        'modal': '0 24px 48px rgba(0, 0, 0, 0.5), 0 12px 24px rgba(0, 0, 0, 0.4)',
        'amber': '0 0 12px rgba(217, 119, 6, 0.3)',
      },
      zIndex: {
        'dropdown': '100',
        'sticky': '200',
        'drawer': '300',
        'modal': '400',
        'toast': '500',
        'tooltip': '600',
      },
      animation: {
        'message-enter': 'message-enter 400ms ease-out forwards',
        'card-appear': 'card-appear 300ms ease-out forwards',
        'thinking-pulse': 'thinking-pulse 1.4s infinite ease-in-out both',
        'executing-pulse': 'executing-pulse 2s infinite ease-in-out',
        'shimmer': 'shimmer 1.5s infinite',
      },
      keyframes: {
        'message-enter': {
          '0%': { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'card-appear': {
          '0%': { opacity: '0', transform: 'scale(0.96)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        'thinking-pulse': {
          '0%, 80%, 100%': { transform: 'scale(0)', opacity: '0' },
          '40%': { transform: 'scale(1)', opacity: '1' },
        },
        'executing-pulse': {
          '0%, 100%': { boxShadow: '0 0 0px rgba(217, 119, 6, 0)', borderColor: '#D97706' },
          '50%': { boxShadow: '0 0 12px rgba(217, 119, 6, 0.4)', borderColor: '#F59E0B' },
        },
        'shimmer': {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
      transitionTimingFunction: {
        'spring': 'cubic-bezier(0.34, 1.56, 0.64, 1)',
      },
    },
  },
  plugins: [],
};
