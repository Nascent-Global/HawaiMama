import type { AccidentLog } from "@/types/accident";
import { AccidentLogSchema } from "@/types/accident";
import type { AdminAccount } from "@/types/auth";
import { AdminAccountSchema, LoginResponseSchema } from "@/types/auth";
import type { SurveillanceCameraConfig } from "@/types/camera-config";
import { SurveillanceCameraConfigSchema } from "@/types/camera-config";
import type { ChallanLog } from "@/types/challan";
import { ChallanSchema } from "@/types/challan";
import type { SurveillanceFeed } from "@/types/surveillance";
import { SurveillanceFeedSchema } from "@/types/surveillance";
import type { ViolationLog } from "@/types/violation";
import { ViolationLogSchema } from "@/types/violation";
import { z } from "zod";

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"
).replace(/\/+$/, "");

const API_MEDIA_PREFIXES = [
  "/camera/",
  "/snapshots/",
  "/inputs/",
  "/surveillance-media/",
  "/surveillance-previews/",
  "/surveillance-output/",
  "/wwwroots/",
];
const surveillanceFeedListSchema = z.array(SurveillanceFeedSchema);
const violationLogListSchema = z.array(ViolationLogSchema);
const accidentLogListSchema = z.array(AccidentLogSchema);
const challanLogListSchema = z.array(ChallanSchema);
const cameraConfigListSchema = z.array(SurveillanceCameraConfigSchema);
const adminAccountListSchema = z.array(AdminAccountSchema);
const verifyViolationResponseSchema = z.object({
  violation: ViolationLogSchema,
  challan: ChallanSchema.nullish(),
});
const verifyAccidentResponseSchema = z.object({
  accident: AccidentLogSchema,
});

function apiUrl(path: string): string {
  if (/^https?:\/\//.test(path)) {
    return path;
  }
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

export function resolveMediaUrl(path: string | null | undefined): string {
  if (!path) {
    return "";
  }
  if (/^https?:\/\//.test(path)) {
    return path;
  }
  if (API_MEDIA_PREFIXES.some((prefix) => path.startsWith(prefix))) {
    return apiUrl(path);
  }
  return path;
}

async function getJson(path: string): Promise<unknown> {
  const response = await fetch(apiUrl(path), {
    cache: "no-store",
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

async function postJson(path: string, body?: unknown): Promise<unknown> {
  const response = await fetch(apiUrl(path), {
    method: "POST",
    cache: "no-store",
    credentials: "include",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

async function patchJson(path: string, body: unknown): Promise<unknown> {
  const response = await fetch(apiUrl(path), {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    cache: "no-store",
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

async function deleteJson(path: string): Promise<unknown> {
  const response = await fetch(apiUrl(path), {
    method: "DELETE",
    cache: "no-store",
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

export async function getSurveillanceFeeds(): Promise<SurveillanceFeed[]> {
  const feeds = surveillanceFeedListSchema.parse(await getJson("/surveillance/feeds"));
  return feeds.map((feed) => ({
    ...feed,
    stream_video: resolveMediaUrl(feed.stream_video),
    poster: resolveMediaUrl(feed.poster),
    videoUrl: resolveMediaUrl(feed.videoUrl),
    previewVideoUrl: resolveMediaUrl(feed.previewVideoUrl),
    processedVideoUrl: resolveMediaUrl(feed.processedVideoUrl),
  }));
}

export async function getViolations(): Promise<ViolationLog[]> {
  const violations = violationLogListSchema.parse(await getJson("/violations"));
  return violations.map((violation) => ({
    ...violation,
    screenshot1Url: resolveMediaUrl(violation.screenshot1Url),
    screenshot2Url: resolveMediaUrl(violation.screenshot2Url),
    screenshot3Url: resolveMediaUrl(violation.screenshot3Url),
    videoUrl: resolveMediaUrl(violation.videoUrl),
    cameraLocationLink: resolveMediaUrl(violation.cameraLocationLink),
    evidenceClipUrl: resolveMediaUrl(violation.evidenceClipUrl),
    sourceVideoUrl: resolveMediaUrl(violation.sourceVideoUrl),
  }));
}

export async function verifyViolation(id: string): Promise<{ violation: ViolationLog; challan?: ChallanLog | null }> {
  const result = verifyViolationResponseSchema.parse(await postJson(`/violations/${id}/verify`));
  return {
    ...result,
    violation: {
      ...result.violation,
      screenshot1Url: resolveMediaUrl(result.violation.screenshot1Url),
      screenshot2Url: resolveMediaUrl(result.violation.screenshot2Url),
      screenshot3Url: resolveMediaUrl(result.violation.screenshot3Url),
      videoUrl: resolveMediaUrl(result.violation.videoUrl),
      cameraLocationLink: resolveMediaUrl(result.violation.cameraLocationLink),
      evidenceClipUrl: resolveMediaUrl(result.violation.evidenceClipUrl),
      sourceVideoUrl: resolveMediaUrl(result.violation.sourceVideoUrl),
    },
  };
}

export async function getAccidents(): Promise<AccidentLog[]> {
  const accidents = accidentLogListSchema.parse(await getJson("/accidents"));
  return accidents.map((accident) => ({
    ...accident,
    screenshot1Url: resolveMediaUrl(accident.screenshot1Url),
    screenshot2Url: resolveMediaUrl(accident.screenshot2Url),
    screenshot3Url: resolveMediaUrl(accident.screenshot3Url),
    videoUrl: resolveMediaUrl(accident.videoUrl),
  }));
}

export async function verifyAccident(id: string): Promise<{ accident: AccidentLog }> {
  const result = verifyAccidentResponseSchema.parse(await postJson(`/accidents/${id}/verify`));
  return {
    accident: {
      ...result.accident,
      screenshot1Url: resolveMediaUrl(result.accident.screenshot1Url),
      screenshot2Url: resolveMediaUrl(result.accident.screenshot2Url),
      screenshot3Url: resolveMediaUrl(result.accident.screenshot3Url),
      videoUrl: resolveMediaUrl(result.accident.videoUrl),
    },
  };
}

export async function getChallans(): Promise<ChallanLog[]> {
  return challanLogListSchema.parse(await getJson("/challans"));
}

export async function getCameraConfigs(): Promise<SurveillanceCameraConfig[]> {
  const cameras = cameraConfigListSchema.parse(await getJson("/admin/cameras"));
  return cameras.map((camera) => ({
    ...camera,
    stream_url: resolveMediaUrl(camera.stream_url),
    video_url: resolveMediaUrl(camera.video_url),
  }));
}

export async function updateCameraConfig(
  id: string,
  body: Partial<
    Pick<
      SurveillanceCameraConfig,
      | "location"
      | "system_mode"
      | "frame_skip"
      | "resolution"
      | "fps_limit"
      | "ocr_enabled"
      | "ocr_debug"
      | "intersection_id"
      | "lanes"
      | "roi_config_path"
      | "confidence_threshold"
      | "plate_confidence_threshold"
      | "char_confidence_threshold"
      | "helmet_confidence_threshold"
      | "overspeed_threshold_kmh"
      | "line1_y"
      | "line2_y"
      | "line_distance_meters"
      | "line_tolerance_pixels"
      | "helmet_stability_frames"
      | "stop_speed_threshold_px"
      | "stop_frames_threshold"
      | "stop_line_distance_px"
      | "min_green_time"
      | "max_green_time"
      | "yellow_time"
      | "priority_queue_weight"
      | "priority_wait_weight"
      | "fairness_weight"
      | "max_priority_score"
      | "initial_active_lane"
    >
  >,
): Promise<SurveillanceCameraConfig> {
  const camera = SurveillanceCameraConfigSchema.parse(await patchJson(`/admin/cameras/${id}`, body));
  return {
    ...camera,
    stream_url: resolveMediaUrl(camera.stream_url),
    video_url: resolveMediaUrl(camera.video_url),
  };
}

export async function createCameraConfig(input: {
  file: File;
  location: string;
  system_mode: SurveillanceCameraConfig["system_mode"];
}): Promise<SurveillanceCameraConfig> {
  const formData = new FormData();
  formData.set("file", input.file);
  formData.set("location", input.location);
  formData.set("system_mode", input.system_mode);

  const response = await fetch(apiUrl("/admin/cameras"), {
    method: "POST",
    body: formData,
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  const camera = SurveillanceCameraConfigSchema.parse(await response.json());
  return {
    ...camera,
    stream_url: resolveMediaUrl(camera.stream_url),
    video_url: resolveMediaUrl(camera.video_url),
  };
}

export async function deleteCameraConfig(id: string): Promise<void> {
  await deleteJson(`/admin/cameras/${id}`);
}

export async function loginAdmin(input: {
  username: string;
  password: string;
}): Promise<{ admin: AdminAccount; token: string }> {
  return LoginResponseSchema.parse(await postJson("/auth/login", input));
}

export async function logoutAdmin(): Promise<void> {
  await postJson("/auth/logout");
}

export async function getCurrentAdmin(): Promise<AdminAccount> {
  return AdminAccountSchema.parse(await getJson("/auth/me"));
}

export async function getAdminAccounts(): Promise<AdminAccount[]> {
  return adminAccountListSchema.parse(await getJson("/auth/admins"));
}

export async function createAdminAccount(input: {
  username: string;
  full_name: string;
  password: string;
  role: "superadmin" | "admin";
  is_active: boolean;
  all_locations: boolean;
  allowed_locations: string[];
  permissions: Record<string, boolean>;
}): Promise<AdminAccount> {
  return AdminAccountSchema.parse(await postJson("/auth/admins", input));
}

export async function updateAdminAccount(
  id: string,
  body: {
    full_name?: string;
    password?: string;
    role?: "superadmin" | "admin";
    is_active?: boolean;
    all_locations?: boolean;
    allowed_locations?: string[];
    permissions?: Record<string, boolean>;
  },
): Promise<AdminAccount> {
  return AdminAccountSchema.parse(await patchJson(`/auth/admins/${id}`, body));
}

export { API_BASE_URL };
