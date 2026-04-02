import { Merriweather, Noto_Sans } from "next/font/google";
import "./globals.css";
import CustomCursor from "@/components/CustomCursor";
import { AdminSessionProvider } from "@/lib/auth";

const bodyFont = Noto_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-body",
});

const headingFont = Merriweather({
  subsets: ["latin"],
  weight: ["700"],
  variable: "--font-heading",
});

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${bodyFont.variable} ${headingFont.variable}`}>
      <body className={`${bodyFont.className} antialiased`}>
        <AdminSessionProvider>
          <CustomCursor />
          {children}
        </AdminSessionProvider>
      </body>
    </html>
  );
}
