import AnimatedBackground from "@/components/AnimatedBackground";
import SurveillanceAdminPanel from "@/components/admin/SurveillanceAdminPanel";
import { getCameraConfigs } from "@/lib/api";
import type { SurveillanceCameraConfig } from "@/types/camera-config";

export const dynamic = "force-dynamic";

export default async function SurveillanceAdminRoute() {
  let initialCameras: SurveillanceCameraConfig[] = [];
  let initialError: string | null = null;

  try {
    initialCameras = await getCameraConfigs();
  } catch (error) {
    initialError =
      error instanceof Error
        ? error.message
        : "Failed to load surveillance configuration";
  }

  return (
    <main className="app-shell">
      <AnimatedBackground />
      <div className="app-shell-inner">
        <SurveillanceAdminPanel
          initialCameras={initialCameras}
          initialError={initialError}
        />
      </div>
    </main>
  );
}
