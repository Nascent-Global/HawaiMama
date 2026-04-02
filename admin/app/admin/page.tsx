import AnimatedBackground from "@/components/AnimatedBackground";
import AdminGate from "@/components/auth/AdminGate";
import SurveillanceAdminPanel from "@/components/admin/SurveillanceAdminPanel";

export const dynamic = "force-dynamic";

export default function SurveillanceAdminRoute() {
  return (
    <main className="app-shell">
      <AnimatedBackground />
      <div className="app-shell-inner">
        <AdminGate
          anyOfPermissions={["can_manage_feeds", "can_manage_admins"]}
          deniedTitle="Feed admin unavailable"
          deniedCopy="Your account can use the dashboard, but it cannot manage surveillance feeds or office access."
        >
          <SurveillanceAdminPanel />
        </AdminGate>
      </div>
    </main>
  );
}
