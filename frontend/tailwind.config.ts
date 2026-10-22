import type { Config } from "tailwindcss";

// Every themed color reads a CSS variable (see app/globals.css), so light/dark is one
// variable swap on <html class="dark"> instead of a dark: variant on every component.
const v = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;
const scale = (name: string, shades: number[]) => Object.fromEntries(shades.map((s) => [s, v(`${name}-${s}`)]));

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Pretendard Variable", "Pretendard", "-apple-system", "BlinkMacSystemFont", "Apple SD Gothic Neo", "Noto Sans KR", "Segoe UI", "sans-serif"],
      },
      colors: {
        canvas: v("canvas"),
        app: v("app"),
        surface: { DEFAULT: v("surface"), 2: v("surface-2") },
        accent: { DEFAULT: v("accent"), 50: v("accent-50") },
        chart: { 1: v("chart-1"), 2: v("chart-2") },
        hero: { from: v("hero-from"), to: v("hero-to") },
        ink: scale("ink", [50, 100, 300, 500, 700, 900]),
        brand: { ...scale("brand", [50, 100, 500, 600, 700]), strong: v("brand-strong") },
        // Only the status shades the console uses are themed; the rest keep Tailwind defaults.
        red: scale("red", [50, 100, 700, 800]),
        amber: scale("amber", [50, 100, 700, 800]),
        emerald: scale("emerald", [50, 100, 700, 800]),
        violet: scale("violet", [50, 700]),
      },
    },
  },
  plugins: [],
};
export default config;
