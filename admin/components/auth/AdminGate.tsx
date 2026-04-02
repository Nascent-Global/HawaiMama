"use client";

import type { FormEvent, ReactNode } from "react";
import { useMemo, useState } from "react";
import { canAccessPermission, useAdminSession } from "@/lib/auth";
import type { AdminPermissions } from "@/types/auth";

type PermissionKey = keyof AdminPermissions;

function LoginPanel() {
  const { login, isBooting } = useAdminSession();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    try {
      setIsSubmitting(true);
      setError(null);
      await login(username.trim(), password);
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : "Login failed");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isBooting) {
    return (
      <div className="auth-shell">
        <div className="auth-card">
          <p className="auth-kicker">Hawai Mama</p>
          <h1 className="auth-title">Checking session</h1>
          <p className="auth-copy">Connecting to the admin backend.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-shell">
      <form className="auth-card" onSubmit={handleSubmit}>
        <p className="auth-kicker">Traffic Monitoring Admin</p>
        <h1 className="auth-title">Sign in to continue</h1>
        <p className="auth-copy">
          Use the office account provided by the superadmin. Access is scoped by office permissions and surveillance location.
        </p>
        <label className="auth-field">
          <span>Username</span>
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            placeholder="admin"
            autoComplete="username"
          />
        </label>
        <label className="auth-field">
          <span>Password</span>
          <input
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            type="password"
            placeholder="••••••••"
            autoComplete="current-password"
          />
        </label>
        {error ? <div className="auth-error">{error}</div> : null}
        <button
          type="submit"
          className="auth-submit"
          disabled={isSubmitting || !username.trim() || !password}
        >
          {isSubmitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}

function AccessDenied({
  title = "Access denied",
  copy = "Your account does not have access to this section.",
}: {
  title?: string;
  copy?: string;
}) {
  return (
    <div className="auth-shell">
      <div className="auth-card">
        <p className="auth-kicker">Restricted area</p>
        <h1 className="auth-title">{title}</h1>
        <p className="auth-copy">{copy}</p>
      </div>
    </div>
  );
}

export default function AdminGate({
  children,
  permission,
  anyOfPermissions,
  deniedTitle,
  deniedCopy,
}: {
  children: ReactNode;
  permission?: PermissionKey;
  anyOfPermissions?: PermissionKey[];
  deniedTitle?: string;
  deniedCopy?: string;
}) {
  const { admin, isBooting } = useAdminSession();

  const hasAccess = useMemo(() => {
    if (!admin) {
      return false;
    }
    if (permission) {
      return canAccessPermission(admin, permission);
    }
    if (anyOfPermissions?.length) {
      return anyOfPermissions.some((candidate) => canAccessPermission(admin, candidate));
    }
    return true;
  }, [admin, anyOfPermissions, permission]);

  if (isBooting || !admin) {
    return <LoginPanel />;
  }

  if (!hasAccess) {
    return <AccessDenied title={deniedTitle} copy={deniedCopy} />;
  }

  return <>{children}</>;
}
