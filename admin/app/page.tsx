import AnimatedBackground from "@/components/AnimatedBackground";
import LiveSurveillanceDashboard from "@/components/live/LiveSurveillanceDashboard";
import { getSurveillanceFeeds } from "@/lib/api";
import type { SurveillanceFeed } from "@/types/surveillance";

export const dynamic = "force-dynamic";

export default async function Home() {
  let initialFeeds: SurveillanceFeed[] = [];
  let initialFeedError: string | null = null;

  try {
    initialFeeds = await getSurveillanceFeeds();
  } catch (error) {
    initialFeedError =
      error instanceof Error ? error.message : "Failed to load surveillance feeds";
  }

  return (
    <main className="app-shell">
      <AnimatedBackground />
      <div className="app-shell-inner">
        <LiveSurveillanceDashboard
          initialFeeds={initialFeeds}
          initialFeedError={initialFeedError}
        />
      </div>
    </main>
  );
}
