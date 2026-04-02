import AnimatedBackground from "@/components/AnimatedBackground";
import AdminGate from "@/components/auth/AdminGate";
import LiveSurveillanceDashboard from "@/components/live/LiveSurveillanceDashboard";

export const dynamic = "force-dynamic";

export default function Home() {
  return (
    <main className="app-shell">
      <AnimatedBackground />
      <div className="app-shell-inner">
        <AdminGate>
          <LiveSurveillanceDashboard />
        </AdminGate>
      </div>
    </main>
  );
}
