// app/layout.tsx
import { Outfit } from "next/font/google";
import "./globals.css";
import CustomCursor from "@/components/CustomCursor";
import { AdminSessionProvider } from "@/lib/auth";

const outfit = Outfit({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-outfit",
});

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={outfit.variable}>
      <body className={`${outfit.className} antialiased`}>
        <AdminSessionProvider>
          <CustomCursor />
          {children}
        </AdminSessionProvider>
      </body>
    </html>
  );
}
