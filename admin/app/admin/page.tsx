import AnimatedBackground from "@/components/AnimatedBackground";
import SurveillanceAdminPanel from "@/components/admin/SurveillanceAdminPanel";

export default function SurveillanceAdminRoute() {
  return (
    <main className="app-shell">
      <AnimatedBackground />
      <div className="app-shell-inner">
        <SurveillanceAdminPanel />
      </div>
    </main>
  );
}
