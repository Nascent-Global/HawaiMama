"use client";

import type { ReactNode } from "react";
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { getCurrentAdmin, loginAdmin, logoutAdmin } from "@/lib/api";
import type { AdminAccount, AdminPermissions } from "@/types/auth";

type AdminSessionContextValue = {
  admin: AdminAccount | null;
  isBooting: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AdminSessionContext = createContext<AdminSessionContextValue | null>(null);

async function loadCurrentAdmin(): Promise<AdminAccount | null> {
  try {
    return await getCurrentAdmin();
  } catch (error) {
    if (error instanceof Error && error.message.includes("401")) {
      return null;
    }
    throw error;
  }
}

export function AdminSessionProvider({ children }: { children: ReactNode }) {
  const [admin, setAdmin] = useState<AdminAccount | null>(null);
  const [isBooting, setIsBooting] = useState(true);

  const refresh = async () => {
    setAdmin(await loadCurrentAdmin());
  };

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const nextAdmin = await loadCurrentAdmin();
        if (active) {
          setAdmin(nextAdmin);
        }
      } finally {
        if (active) {
          setIsBooting(false);
        }
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const value = useMemo<AdminSessionContextValue>(
    () => ({
      admin,
      isBooting,
      async login(username: string, password: string) {
        const result = await loginAdmin({ username, password });
        setAdmin(result.admin);
      },
      async logout() {
        await logoutAdmin();
        setAdmin(null);
      },
      async refresh() {
        await refresh();
      },
    }),
    [admin, isBooting],
  );

  return <AdminSessionContext.Provider value={value}>{children}</AdminSessionContext.Provider>;
}

export function useAdminSession(): AdminSessionContextValue {
  const context = useContext(AdminSessionContext);
  if (!context) {
    throw new Error("useAdminSession must be used within AdminSessionProvider");
  }
  return context;
}

export function canAccessPermission(
  admin: AdminAccount | null,
  permission: keyof AdminPermissions,
): boolean {
  if (!admin) {
    return false;
  }
  if (admin.role === "superadmin") {
    return true;
  }
  return Boolean(admin.permissions[permission]);
}
