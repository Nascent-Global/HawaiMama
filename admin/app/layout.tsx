import type { ReactNode } from "react";
import "./globals.css";
import CustomCursor from "@/components/CustomCursor";
import { AdminSessionProvider } from "@/lib/auth";

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">
        <AdminSessionProvider>
          <CustomCursor />
          {children}
        </AdminSessionProvider>
      </body>
    </html>
  );
}
