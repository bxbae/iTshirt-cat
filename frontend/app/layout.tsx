import type { Metadata } from "next";
import { ThemeProvider, themeInitScript } from "@/components/ThemeProvider";
import { AuthProvider } from "@/lib/auth";
import { CartProvider } from "@/lib/cart";
import "pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "캣북스 · 책과 문구, 고양이가 지키는 서점",
  description: "책·문구·굿즈를 사고, 영수증 기준으로 환불과 보상을 빠르게 처리해 주는 온라인 서점 (데모)",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // The init script sets class/data-theme before React hydrates, so the mismatch is expected.
    <html lang="ko" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body>
        <ThemeProvider>
          <AuthProvider>
            <CartProvider>{children}</CartProvider>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
