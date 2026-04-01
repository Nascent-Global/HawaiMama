import AnimatedBackground from "@/components/AnimatedBackground";
import LiveSurveillanceDashboard from "@/components/live/LiveSurveillanceDashboard";

export default function Home() {
  return (
    <main className="app-shell">
      <AnimatedBackground />
      <div className="app-shell-inner">
        <LiveSurveillanceDashboard />
      </div>
    </main>
  );
}
