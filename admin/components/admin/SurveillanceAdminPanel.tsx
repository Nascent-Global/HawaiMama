"use client";

import Image from "next/image";
import Link from "next/link";
import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import {
  createAdminAccount,
  createCameraConfig,
  deleteCameraConfig,
  getAdminAccounts,
  getCameraConfigs,
  updateAdminAccount,
  updateCameraConfig,
} from "@/lib/api";
import { canAccessPermission, useAdminSession } from "@/lib/auth";
import type { AdminAccount, AdminPermissions } from "@/types/auth";
import type { SurveillanceCameraConfig } from "@/types/camera-config";

type CameraDraft = {
  location: string;
  system_mode: SurveillanceCameraConfig["system_mode"];
  frame_skip: string;
  resolution_width: string;
  resolution_height: string;
  fps_limit: string;
  ocr_enabled: boolean;
  ocr_debug: boolean;
  intersection_id: string;
  lanes_text: string;
  roi_config_path: string;
  confidence_threshold: string;
  plate_confidence_threshold: string;
  char_confidence_threshold: string;
  helmet_confidence_threshold: string;
  overspeed_threshold_kmh: string;
  line1_y: string;
  line2_y: string;
  line_distance_meters: string;
  line_tolerance_pixels: string;
  helmet_stability_frames: string;
  stop_speed_threshold_px: string;
  stop_frames_threshold: string;
  stop_line_distance_px: string;
  min_green_time: string;
  max_green_time: string;
  yellow_time: string;
  priority_queue_weight: string;
  priority_wait_weight: string;
  fairness_weight: string;
  max_priority_score: string;
  initial_active_lane: string;
};

type Drafts = Record<string, CameraDraft>;
type ModeFilter = "all" | SurveillanceCameraConfig["system_mode"];
type PermissionKey = keyof AdminPermissions;

type AdminDraft = {
  full_name: string;
  password: string;
  role: AdminAccount["role"];
  is_active: boolean;
  all_locations: boolean;
  allowed_locations: string[];
  permissions: AdminPermissions;
};

const MODE_OPTIONS: Array<{
  value: SurveillanceCameraConfig["system_mode"];
  label: string;
  helper: string;
}> = [
  {
    value: "enforcement_mode",
    label: "Enforcement mode",
    helper: "Speed, helmet, plate, and violation-first monitoring.",
  },
  {
    value: "traffic_management_mode",
    label: "Traffic light mode",
    helper: "Flow and intersection-focused monitoring for traffic ops.",
  },
];

const PERMISSION_META: Array<{
  key: PermissionKey;
  label: string;
  helper: string;
}> = [
  { key: "can_view_live", label: "Live surveillance", helper: "Open raw and processed surveillance feeds." },
  { key: "can_manage_feeds", label: "Feed configuration", helper: "Rename feeds, upload clips, and remove sources." },
  { key: "can_view_violations", label: "Violation logs", helper: "Read violation records and evidence." },
  { key: "can_verify_violations", label: "Verify violations", helper: "Confirm violations and generate challans." },
  { key: "can_view_accidents", label: "Accident logs", helper: "Read accident records." },
  { key: "can_verify_accidents", label: "Verify accidents", helper: "Confirm accidents and issue reports." },
  { key: "can_view_challans", label: "Challan logs", helper: "Read and print challans." },
  { key: "can_manage_admins", label: "Manage admins", helper: "Create office users and change access scope." },
];

function basePermissions(): AdminPermissions {
  return {
    can_view_live: true,
    can_manage_feeds: false,
    can_view_violations: true,
    can_verify_violations: true,
    can_view_accidents: true,
    can_verify_accidents: true,
    can_view_challans: true,
    can_manage_admins: false,
  };
}

function superadminPermissions(): AdminPermissions {
  return {
    can_view_live: true,
    can_manage_feeds: true,
    can_view_violations: true,
    can_verify_violations: true,
    can_view_accidents: true,
    can_verify_accidents: true,
    can_view_challans: true,
    can_manage_admins: true,
  };
}

function createDrafts(cameras: SurveillanceCameraConfig[]): Drafts {
  return Object.fromEntries(
    cameras.map((camera) => [
      camera.id,
      createCameraDraft(camera),
    ]),
  );
}

function createEmptyCameraDraft(): CameraDraft {
  return {
    location: "",
    system_mode: "enforcement_mode",
    frame_skip: "",
    resolution_width: "",
    resolution_height: "",
    fps_limit: "",
    ocr_enabled: true,
    ocr_debug: false,
    intersection_id: "",
    lanes_text: "",
    roi_config_path: "",
    confidence_threshold: "",
    plate_confidence_threshold: "",
    char_confidence_threshold: "",
    helmet_confidence_threshold: "",
    overspeed_threshold_kmh: "",
    line1_y: "",
    line2_y: "",
    line_distance_meters: "",
    line_tolerance_pixels: "",
    helmet_stability_frames: "",
    stop_speed_threshold_px: "",
    stop_frames_threshold: "",
    stop_line_distance_px: "",
    min_green_time: "",
    max_green_time: "",
    yellow_time: "",
    priority_queue_weight: "",
    priority_wait_weight: "",
    fairness_weight: "",
    max_priority_score: "",
    initial_active_lane: "",
  };
}

function optionalText(value: string | number | null | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

function createCameraDraft(camera: SurveillanceCameraConfig): CameraDraft {
  return {
    location: camera.location,
    system_mode: camera.system_mode,
    frame_skip: optionalText(camera.frame_skip),
    resolution_width: optionalText(camera.resolution?.[0]),
    resolution_height: optionalText(camera.resolution?.[1]),
    fps_limit: optionalText(camera.fps_limit),
    ocr_enabled: camera.ocr_enabled ?? true,
    ocr_debug: camera.ocr_debug ?? false,
    intersection_id: camera.intersection_id ?? "",
    lanes_text: (camera.lanes ?? []).join(", "),
    roi_config_path: camera.roi_config_path ?? "",
    confidence_threshold: optionalText(camera.confidence_threshold),
    plate_confidence_threshold: optionalText(camera.plate_confidence_threshold),
    char_confidence_threshold: optionalText(camera.char_confidence_threshold),
    helmet_confidence_threshold: optionalText(camera.helmet_confidence_threshold),
    overspeed_threshold_kmh: optionalText(camera.overspeed_threshold_kmh),
    line1_y: optionalText(camera.line1_y),
    line2_y: optionalText(camera.line2_y),
    line_distance_meters: optionalText(camera.line_distance_meters),
    line_tolerance_pixels: optionalText(camera.line_tolerance_pixels),
    helmet_stability_frames: optionalText(camera.helmet_stability_frames),
    stop_speed_threshold_px: optionalText(camera.stop_speed_threshold_px),
    stop_frames_threshold: optionalText(camera.stop_frames_threshold),
    stop_line_distance_px: optionalText(camera.stop_line_distance_px),
    min_green_time: optionalText(camera.min_green_time),
    max_green_time: optionalText(camera.max_green_time),
    yellow_time: optionalText(camera.yellow_time),
    priority_queue_weight: optionalText(camera.priority_queue_weight),
    priority_wait_weight: optionalText(camera.priority_wait_weight),
    fairness_weight: optionalText(camera.fairness_weight),
    max_priority_score: optionalText(camera.max_priority_score),
    initial_active_lane: camera.initial_active_lane ?? "",
  };
}

function parseOptionalNumber(value: string): number | null {
  const normalized = value.trim();
  if (!normalized) {
    return null;
  }
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseOptionalInteger(value: string): number | null {
  const parsed = parseOptionalNumber(value);
  return parsed === null ? null : Math.trunc(parsed);
}

function normalizeLaneList(value: string): string[] {
  return value
    .split(",")
    .map((lane) => lane.trim())
    .filter(Boolean);
}

function buildCameraUpdatePayload(draft: CameraDraft) {
  const width = parseOptionalInteger(draft.resolution_width);
  const height = parseOptionalInteger(draft.resolution_height);
  return {
    location: draft.location.trim(),
    system_mode: draft.system_mode,
    frame_skip: parseOptionalInteger(draft.frame_skip),
    resolution: width !== null && height !== null ? ([width, height] as [number, number]) : null,
    fps_limit: parseOptionalNumber(draft.fps_limit),
    ocr_enabled: draft.ocr_enabled,
    ocr_debug: draft.ocr_debug,
    intersection_id: draft.intersection_id.trim() || null,
    lanes: normalizeLaneList(draft.lanes_text),
    roi_config_path: draft.roi_config_path.trim() || null,
    confidence_threshold: parseOptionalNumber(draft.confidence_threshold),
    plate_confidence_threshold: parseOptionalNumber(draft.plate_confidence_threshold),
    char_confidence_threshold: parseOptionalNumber(draft.char_confidence_threshold),
    helmet_confidence_threshold: parseOptionalNumber(draft.helmet_confidence_threshold),
    overspeed_threshold_kmh: parseOptionalNumber(draft.overspeed_threshold_kmh),
    line1_y: parseOptionalNumber(draft.line1_y),
    line2_y: parseOptionalNumber(draft.line2_y),
    line_distance_meters: parseOptionalNumber(draft.line_distance_meters),
    line_tolerance_pixels: parseOptionalInteger(draft.line_tolerance_pixels),
    helmet_stability_frames: parseOptionalInteger(draft.helmet_stability_frames),
    stop_speed_threshold_px: parseOptionalNumber(draft.stop_speed_threshold_px),
    stop_frames_threshold: parseOptionalInteger(draft.stop_frames_threshold),
    stop_line_distance_px: parseOptionalNumber(draft.stop_line_distance_px),
    min_green_time: parseOptionalNumber(draft.min_green_time),
    max_green_time: parseOptionalNumber(draft.max_green_time),
    yellow_time: parseOptionalNumber(draft.yellow_time),
    priority_queue_weight: parseOptionalNumber(draft.priority_queue_weight),
    priority_wait_weight: parseOptionalNumber(draft.priority_wait_weight),
    fairness_weight: parseOptionalNumber(draft.fairness_weight),
    max_priority_score: parseOptionalNumber(draft.max_priority_score),
    initial_active_lane: draft.initial_active_lane.trim() || null,
  };
}

function isCameraDraftDirty(camera: SurveillanceCameraConfig, draft: CameraDraft | undefined): boolean {
  if (!draft) {
    return false;
  }
  return JSON.stringify(draft) !== JSON.stringify(createCameraDraft(camera));
}

function createAdminDrafts(accounts: AdminAccount[]): Record<string, AdminDraft> {
  return Object.fromEntries(
    accounts.map((account) => [
      account.id,
      {
        full_name: account.full_name,
        password: "",
        role: account.role,
        is_active: account.is_active,
        all_locations: account.all_locations,
        allowed_locations: account.allowed_locations,
        permissions: account.permissions,
      },
    ]),
  );
}

function SearchIcon() {
  return (
    <svg
      className="dash-search-icon"
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <circle cx="11" cy="11" r="8" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  );
}

function RefreshIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M21 2v6h-6" />
      <path d="M3 22v-6h6" />
      <path d="M20.49 9A9 9 0 0 0 5.64 5.64L3 8" />
      <path d="M3.51 15a9 9 0 0 0 14.85 3.36L21 16" />
    </svg>
  );
}

export default function SurveillanceAdminPanel() {
  const { admin, logout } = useAdminSession();
  const canManageAdmins = canAccessPermission(admin, "can_manage_admins");
  const [cameras, setCameras] = useState<SurveillanceCameraConfig[]>([]);
  const [drafts, setDrafts] = useState<Drafts>({});
  const [searchQuery, setSearchQuery] = useState("");
  const [modeFilter, setModeFilter] = useState<ModeFilter>("all");
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [savedId, setSavedId] = useState<string | null>(null);
  const [uploadLocation, setUploadLocation] = useState("");
  const [uploadMode, setUploadMode] = useState<SurveillanceCameraConfig["system_mode"]>("enforcement_mode");
  const [selectedUploadFile, setSelectedUploadFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [accounts, setAccounts] = useState<AdminAccount[]>([]);
  const [accountDrafts, setAccountDrafts] = useState<Record<string, AdminDraft>>({});
  const [accountsError, setAccountsError] = useState<string | null>(null);
  const [accountsLoading, setAccountsLoading] = useState(false);
  const [savingAdminId, setSavingAdminId] = useState<string | null>(null);
  const [creatingAdmin, setCreatingAdmin] = useState(false);
  const [newAdmin, setNewAdmin] = useState<{
    username: string;
    full_name: string;
    password: string;
    role: AdminAccount["role"];
    is_active: boolean;
    all_locations: boolean;
    allowed_locations: string[];
    permissions: AdminPermissions;
  }>({
    username: "",
    full_name: "",
    password: "",
    role: "admin",
    is_active: true,
    all_locations: false,
    allowed_locations: [],
    permissions: basePermissions(),
  });
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const deferredSearchQuery = useDeferredValue(searchQuery);

  const refreshCameras = useCallback(async () => {
    try {
      setIsRefreshing(true);
      setIsLoading(true);
      setError(null);
      const data = await getCameraConfigs();
      setCameras(data);
      setDrafts(createDrafts(data));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load surveillance configuration");
    } finally {
      setIsRefreshing(false);
      setIsLoading(false);
    }
  }, []);

  const refreshAccounts = useCallback(async () => {
    if (!canManageAdmins) {
      return;
    }
    try {
      setAccountsLoading(true);
      setAccountsError(null);
      const data = await getAdminAccounts();
      setAccounts(data);
      setAccountDrafts(createAdminDrafts(data));
    } catch (loadError) {
      setAccountsError(loadError instanceof Error ? loadError.message : "Failed to load admin accounts");
    } finally {
      setAccountsLoading(false);
    }
  }, [canManageAdmins]);

  useEffect(() => {
    if (!admin) {
      return;
    }
    void refreshCameras();
    void refreshAccounts();
  }, [admin, refreshAccounts, refreshCameras]);

  const visibleCameras = useMemo(() => {
    const query = deferredSearchQuery.trim().toLowerCase();
    return cameras.filter((camera) => {
      const draft = drafts[camera.id] ?? createCameraDraft(camera);
      const matchesMode = modeFilter === "all" || draft.system_mode === modeFilter;
      const haystack = [camera.id, draft.location, camera.file_name, camera.address].join(" ").toLowerCase();
      return matchesMode && (!query || haystack.includes(query));
    });
  }, [cameras, deferredSearchQuery, drafts, modeFilter]);

  const uniqueLocations = useMemo(
    () => Array.from(new Set(cameras.map((camera) => camera.location).filter(Boolean))).sort(),
    [cameras],
  );

  const dirtyCount = useMemo(
    () =>
      cameras.reduce((count, camera) => {
        const draft = drafts[camera.id];
        return isCameraDraftDirty(camera, draft) ? count + 1 : count;
      }, 0),
    [cameras, drafts],
  );

  const enforcementCount = useMemo(
    () => cameras.filter((camera) => camera.system_mode === "enforcement_mode").length,
    [cameras],
  );

  const trafficCount = useMemo(
    () => cameras.filter((camera) => camera.system_mode === "traffic_management_mode").length,
    [cameras],
  );

  const handleDraftChange = <K extends keyof CameraDraft>(cameraId: string, field: K, value: CameraDraft[K]) => {
    setSavedId((current) => (current === cameraId ? null : current));
    setDrafts((current) => ({
      ...current,
      [cameraId]: {
        ...(current[cameraId] ?? createEmptyCameraDraft()),
        [field]: value,
      },
    }));
  };

  const handleReset = (camera: SurveillanceCameraConfig) => {
    setSavedId((current) => (current === camera.id ? null : current));
    setDrafts((current) => ({
      ...current,
      [camera.id]: createCameraDraft(camera),
    }));
  };

  const handleSave = async (cameraId: string) => {
    const draft = drafts[cameraId];
    if (!draft) {
      return;
    }
    try {
      setSavingId(cameraId);
      setSavedId(null);
      setError(null);
      const updated = await updateCameraConfig(cameraId, buildCameraUpdatePayload(draft));
      setCameras((current) => current.map((camera) => (camera.id === cameraId ? updated : camera)));
      setDrafts((current) => ({
        ...current,
        [cameraId]: createCameraDraft(updated),
      }));
      setSavedId(cameraId);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Failed to save surveillance configuration");
    } finally {
      setSavingId(null);
    }
  };

  const handleUpload = async () => {
    if (!selectedUploadFile) {
      setError("Select a surveillance clip first");
      return;
    }
    if (!uploadLocation.trim()) {
      setError("Enter a surveillance location");
      return;
    }
    try {
      setIsUploading(true);
      setError(null);
      const created = await createCameraConfig({
        file: selectedUploadFile,
        location: uploadLocation.trim(),
        system_mode: uploadMode,
      });
      const nextCameras = [...cameras, created].sort((left, right) =>
        left.id.localeCompare(right.id, undefined, { numeric: true }),
      );
      setCameras(nextCameras);
      setDrafts(createDrafts(nextCameras));
      setSavedId(created.id);
      setUploadLocation("");
      setUploadMode("enforcement_mode");
      setSelectedUploadFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Failed to add surveillance feed");
    } finally {
      setIsUploading(false);
    }
  };

  const handleRemove = async (camera: SurveillanceCameraConfig) => {
    const confirmed = window.confirm(`Remove ${camera.id.toUpperCase()} from the surveillance registry?`);
    if (!confirmed) {
      return;
    }
    try {
      setRemovingId(camera.id);
      setError(null);
      await deleteCameraConfig(camera.id);
      const nextCameras = cameras.filter((item) => item.id !== camera.id);
      setCameras(nextCameras);
      setDrafts(createDrafts(nextCameras));
      setSavedId((current) => (current === camera.id ? null : current));
    } catch (removeError) {
      setError(removeError instanceof Error ? removeError.message : "Failed to remove surveillance feed");
    } finally {
      setRemovingId(null);
    }
  };

  const handleDraftPermissionToggle = (adminId: string, permission: PermissionKey, checked: boolean) => {
    setAccountDrafts((current) => {
      const existing = current[adminId];
      if (!existing) {
        return current;
      }
      const nextPermissions = {
        ...existing.permissions,
        [permission]: checked,
      };
      if (permission === "can_manage_admins" && checked) {
        Object.assign(nextPermissions, superadminPermissions());
      }
      return {
        ...current,
        [adminId]: {
          ...existing,
          permissions: nextPermissions,
        },
      };
    });
  };

  const handleDraftLocationToggle = (adminId: string, location: string) => {
    setAccountDrafts((current) => {
      const existing = current[adminId];
      if (!existing) {
        return current;
      }
      const alreadySelected = existing.allowed_locations.includes(location);
      return {
        ...current,
        [adminId]: {
          ...existing,
          allowed_locations: alreadySelected
            ? existing.allowed_locations.filter((value) => value !== location)
            : [...existing.allowed_locations, location],
        },
      };
    });
  };

  const handleSaveAdmin = async (account: AdminAccount) => {
    const draft = accountDrafts[account.id];
    if (!draft) {
      return;
    }
    try {
      setSavingAdminId(account.id);
      setAccountsError(null);
      const updated = await updateAdminAccount(account.id, {
        full_name: draft.full_name.trim(),
        password: draft.password.trim() || undefined,
        role: draft.role,
        is_active: draft.is_active,
        all_locations: draft.role === "superadmin" ? true : draft.all_locations,
        allowed_locations: draft.role === "superadmin" || draft.all_locations ? [] : draft.allowed_locations,
        permissions: draft.role === "superadmin" ? superadminPermissions() : draft.permissions,
      });
      setAccounts((current) => current.map((item) => (item.id === account.id ? updated : item)));
      setAccountDrafts((current) => ({
        ...current,
        [account.id]: {
          ...createAdminDrafts([updated])[updated.id],
        },
      }));
    } catch (saveError) {
      setAccountsError(saveError instanceof Error ? saveError.message : "Failed to update admin account");
    } finally {
      setSavingAdminId(null);
    }
  };

  const handleCreateAdmin = async () => {
    try {
      setCreatingAdmin(true);
      setAccountsError(null);
      const created = await createAdminAccount({
        username: newAdmin.username.trim(),
        full_name: newAdmin.full_name.trim(),
        password: newAdmin.password,
        role: newAdmin.role,
        is_active: newAdmin.is_active,
        all_locations: newAdmin.role === "superadmin" ? true : newAdmin.all_locations,
        allowed_locations: newAdmin.role === "superadmin" || newAdmin.all_locations ? [] : newAdmin.allowed_locations,
        permissions: newAdmin.role === "superadmin" ? superadminPermissions() : newAdmin.permissions,
      });
      const nextAccounts = [...accounts, created].sort((left, right) => left.username.localeCompare(right.username));
      setAccounts(nextAccounts);
      setAccountDrafts(createAdminDrafts(nextAccounts));
      setNewAdmin({
        username: "",
        full_name: "",
        password: "",
        role: "admin",
        is_active: true,
        all_locations: false,
        allowed_locations: [],
        permissions: basePermissions(),
      });
    } catch (createError) {
      setAccountsError(createError instanceof Error ? createError.message : "Failed to create admin account");
    } finally {
      setCreatingAdmin(false);
    }
  };

  return (
    <div className="dash-root admin-root" suppressHydrationWarning>
      <div className="dash-top-bar admin-top-bar">
        <header className="logo-strip" role="banner">
          <div className="logo-strip-inner">
            <div className="logo-strip-brand">
              <Image
                src="/logo.png"
                alt="Hawai Mama — smart traffic monitoring"
                width={200}
                height={56}
                className="logo-strip-img"
                priority
                sizes="(max-width: 400px) 160px, 200px"
              />
              <p className="logo-strip-tagline">Surveillance feed control and office access management</p>
            </div>
          </div>
        </header>

        <div className="dash-toolbar dash-toolbar--inline admin-toolbar">
          <div className="dash-search-wrap admin-search-wrap">
            <input
              type="search"
              className="dash-search"
              placeholder="Search by feed id, filename, or location…"
              aria-label="Search surveillance feeds"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
            />
            <SearchIcon />
          </div>

          {admin ? (
            <div className="dash-session-pill">
              <div>
                <div className="dash-session-name">{admin.full_name}</div>
                <div className="dash-session-role">{admin.role === "superadmin" ? "Superadmin" : "Admin"}</div>
              </div>
              <button type="button" className="dash-session-logout" onClick={() => void logout()}>
                Logout
              </button>
            </div>
          ) : null}

          <div className="admin-toolbar-actions">
            <button
              type="button"
              className="admin-toolbar-btn admin-toolbar-btn--subtle"
              onClick={() => {
                void refreshCameras();
                void refreshAccounts();
              }}
              disabled={isRefreshing || accountsLoading}
            >
              <RefreshIcon />
              <span>{isRefreshing || accountsLoading ? "Refreshing…" : "Refresh data"}</span>
            </button>
            <Link href="/" className="admin-toolbar-btn admin-toolbar-btn--primary">
              Back to dashboard
            </Link>
          </div>
        </div>
      </div>

      <div className="dash-body admin-body">
        <aside className="dash-sidebar admin-sidebar" aria-label="Feed admin overview">
          <section className="admin-sidecard card-glass">
            <p className="admin-kicker">Control Room</p>
            <h1 className="admin-panel-title">Feed configuration</h1>
            <p className="admin-sidecopy">
              Every card below is backed by the Python camera registry. Office admins can rename feeds and switch runtime mode without editing backend code.
            </p>
            <div className="admin-stat-grid">
              <div className="admin-stat-card">
                <span className="admin-stat-value">{cameras.length}</span>
                <span className="admin-stat-label">Total feeds</span>
              </div>
              <div className="admin-stat-card">
                <span className="admin-stat-value">{enforcementCount}</span>
                <span className="admin-stat-label">Enforcement</span>
              </div>
              <div className="admin-stat-card">
                <span className="admin-stat-value">{trafficCount}</span>
                <span className="admin-stat-label">Traffic ops</span>
              </div>
              <div className="admin-stat-card">
                <span className="admin-stat-value">{dirtyCount}</span>
                <span className="admin-stat-label">Unsaved</span>
              </div>
            </div>
          </section>

          <section className="admin-sidecard card-glass">
            <p className="admin-kicker">Extend CCTV</p>
            <div className="admin-upload-card">
              <h2 className="admin-panel-title admin-panel-title--compact">Add surveillance source</h2>
              <p className="admin-sidecopy">
                For the hackathon demo, picking a file here copies it into the Python surveillance folder as the next feed.
              </p>

              <label className="admin-field">
                <span className="admin-field-label">Surveillance location</span>
                <input
                  value={uploadLocation}
                  onChange={(event) => setUploadLocation(event.target.value)}
                  className="admin-input"
                  placeholder="Lakeside Gate 2"
                />
              </label>

              <div className="admin-field">
                <span className="admin-field-label">Default operating mode</span>
                <div className="admin-mode-toggle" role="tablist" aria-label="Default mode for new feed">
                  {MODE_OPTIONS.map((option) => {
                    const isActive = uploadMode === option.value;
                    return (
                      <button
                        key={option.value}
                        type="button"
                        className={`admin-mode-option${isActive ? " admin-mode-option--active" : ""}`}
                        onClick={() => setUploadMode(option.value)}
                      >
                        <span>{option.label}</span>
                        <small>{option.helper}</small>
                      </button>
                    );
                  })}
                </div>
              </div>

              <input
                ref={fileInputRef}
                type="file"
                accept="video/*,.mp4,.mov,.m4v,.webm,.avi,.mkv"
                className="admin-file-input"
                onChange={(event) => setSelectedUploadFile(event.target.files?.[0] ?? null)}
              />

              <div className="admin-upload-picker">
                <button
                  type="button"
                  className="admin-action-btn admin-action-btn--ghost"
                  onClick={() => fileInputRef.current?.click()}
                >
                  Choose raw video
                </button>
                <span className="admin-upload-file">{selectedUploadFile?.name || "No file selected"}</span>
              </div>

              <button
                type="button"
                className="admin-action-btn admin-action-btn--primary"
                onClick={() => void handleUpload()}
                disabled={isUploading || !selectedUploadFile || !uploadLocation.trim()}
              >
                {isUploading ? "Adding feed…" : "Add surveillance feed"}
              </button>
            </div>
          </section>

          <section className="admin-sidecard card-glass">
            <p className="admin-kicker">Mode filter</p>
            <div className="admin-filter-list">
              <button
                type="button"
                className={`admin-filter-btn${modeFilter === "all" ? " admin-filter-btn--active" : ""}`}
                onClick={() => setModeFilter("all")}
              >
                All feeds
              </button>
              <button
                type="button"
                className={`admin-filter-btn${modeFilter === "enforcement_mode" ? " admin-filter-btn--active" : ""}`}
                onClick={() => setModeFilter("enforcement_mode")}
              >
                Enforcement
              </button>
              <button
                type="button"
                className={`admin-filter-btn${modeFilter === "traffic_management_mode" ? " admin-filter-btn--active" : ""}`}
                onClick={() => setModeFilter("traffic_management_mode")}
              >
                Traffic light
              </button>
            </div>
          </section>
        </aside>

        <div className="dash-main admin-main">
          {error ? <div className="admin-alert admin-alert--error">{error}</div> : null}
          {accountsError ? <div className="admin-alert admin-alert--error">{accountsError}</div> : null}

          {canManageAdmins ? (
            <section className="mb-6 rounded-2xl border border-slate-200 bg-white/90 p-6 shadow-sm">
              <div className="mb-5">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Office access control</p>
                <h2 className="mt-2 text-2xl font-semibold text-slate-900">Create and scope admin accounts</h2>
                <p className="mt-2 max-w-3xl text-sm text-slate-600">
                  Superadmins can decide which offices see which surveillance locations and which actions they can perform.
                </p>
              </div>

              <div className="grid gap-6 lg:grid-cols-[1.1fr_1.4fr]">
                <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-5">
                  <h3 className="text-lg font-semibold text-slate-900">Add office admin</h3>
                  <div className="mt-4 grid gap-4">
                    <label className="auth-field">
                      <span>Username</span>
                      <input
                        value={newAdmin.username}
                        onChange={(event) => setNewAdmin((current) => ({ ...current, username: event.target.value }))}
                        placeholder="ward7_admin"
                      />
                    </label>
                    <label className="auth-field">
                      <span>Full name</span>
                      <input
                        value={newAdmin.full_name}
                        onChange={(event) => setNewAdmin((current) => ({ ...current, full_name: event.target.value }))}
                        placeholder="Ward 7 Operations Desk"
                      />
                    </label>
                    <label className="auth-field">
                      <span>Temporary password</span>
                      <input
                        type="password"
                        value={newAdmin.password}
                        onChange={(event) => setNewAdmin((current) => ({ ...current, password: event.target.value }))}
                        placeholder="Create a password"
                      />
                    </label>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <label className="auth-field">
                        <span>Role</span>
                        <select
                          value={newAdmin.role}
                          onChange={(event) => {
                            const role = event.target.value as AdminAccount["role"];
                            setNewAdmin((current) => ({
                              ...current,
                              role,
                              all_locations: role === "superadmin" ? true : current.all_locations,
                              allowed_locations: role === "superadmin" ? [] : current.allowed_locations,
                              permissions: role === "superadmin" ? superadminPermissions() : current.permissions,
                            }));
                          }}
                        >
                          <option value="admin">Admin</option>
                          <option value="superadmin">Superadmin</option>
                        </select>
                      </label>
                      <label className="auth-checkbox">
                        <input
                          type="checkbox"
                          checked={newAdmin.is_active}
                          onChange={(event) => setNewAdmin((current) => ({ ...current, is_active: event.target.checked }))}
                        />
                        <span>Account is active</span>
                      </label>
                    </div>

                    <label className="auth-checkbox">
                      <input
                        type="checkbox"
                        checked={newAdmin.role === "superadmin" || newAdmin.all_locations}
                        disabled={newAdmin.role === "superadmin"}
                        onChange={(event) => setNewAdmin((current) => ({ ...current, all_locations: event.target.checked }))}
                      />
                      <span>Can access every surveillance location</span>
                    </label>

                    {newAdmin.role !== "superadmin" && !newAdmin.all_locations ? (
                      <div>
                        <div className="mb-2 text-sm font-medium text-slate-700">Allowed locations</div>
                        <div className="grid gap-2 sm:grid-cols-2">
                          {uniqueLocations.map((location) => (
                            <label key={location} className="auth-checkbox">
                              <input
                                type="checkbox"
                                checked={newAdmin.allowed_locations.includes(location)}
                                onChange={() =>
                                  setNewAdmin((current) => ({
                                    ...current,
                                    allowed_locations: current.allowed_locations.includes(location)
                                      ? current.allowed_locations.filter((value) => value !== location)
                                      : [...current.allowed_locations, location],
                                  }))
                                }
                              />
                              <span>{location}</span>
                            </label>
                          ))}
                        </div>
                      </div>
                    ) : null}

                    <div>
                      <div className="mb-2 text-sm font-medium text-slate-700">Permissions</div>
                      <div className="grid gap-2">
                        {PERMISSION_META.map((permission) => (
                          <label key={permission.key} className="auth-checkbox auth-checkbox--stacked">
                            <input
                              type="checkbox"
                              checked={newAdmin.role === "superadmin" || newAdmin.permissions[permission.key]}
                              disabled={newAdmin.role === "superadmin"}
                              onChange={(event) =>
                                setNewAdmin((current) => ({
                                  ...current,
                                  permissions: {
                                    ...current.permissions,
                                    [permission.key]: event.target.checked,
                                  },
                                }))
                              }
                            />
                            <span>
                              <strong>{permission.label}</strong>
                              <small>{permission.helper}</small>
                            </span>
                          </label>
                        ))}
                      </div>
                    </div>

                    <button
                      type="button"
                      className="admin-action-btn admin-action-btn--primary"
                      disabled={!newAdmin.username.trim() || !newAdmin.full_name.trim() || !newAdmin.password || creatingAdmin}
                      onClick={() => void handleCreateAdmin()}
                    >
                      {creatingAdmin ? "Creating admin…" : "Create admin"}
                    </button>
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-white p-5">
                  <div className="mb-4 flex items-center justify-between">
                    <h3 className="text-lg font-semibold text-slate-900">Existing office accounts</h3>
                    <span className="text-sm text-slate-500">{accounts.length} accounts</span>
                  </div>
                  {accountsLoading ? <p className="text-sm text-slate-500">Loading admin accounts…</p> : null}
                  <div className="space-y-4">
                    {accounts.map((account) => {
                      const draft = accountDrafts[account.id] ?? createAdminDrafts([account])[account.id];
                      return (
                        <article key={account.id} className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
                          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                            <div>
                              <h4 className="text-base font-semibold text-slate-900">{account.username}</h4>
                              <p className="text-sm text-slate-500">{account.role === "superadmin" ? "Superadmin" : "Office admin"}</p>
                            </div>
                            <span className={`admin-state-pill ${draft.is_active ? "admin-state-pill--saved" : "admin-state-pill--dirty"}`}>
                              {draft.is_active ? "Active" : "Disabled"}
                            </span>
                          </div>

                          <div className="grid gap-4 md:grid-cols-2">
                            <label className="auth-field">
                              <span>Display name</span>
                              <input
                                value={draft.full_name}
                                onChange={(event) =>
                                  setAccountDrafts((current) => ({
                                    ...current,
                                    [account.id]: { ...draft, full_name: event.target.value },
                                  }))
                                }
                              />
                            </label>
                            <label className="auth-field">
                              <span>Reset password</span>
                              <input
                                type="password"
                                value={draft.password}
                                onChange={(event) =>
                                  setAccountDrafts((current) => ({
                                    ...current,
                                    [account.id]: { ...draft, password: event.target.value },
                                  }))
                                }
                                placeholder="Leave blank to keep current"
                              />
                            </label>
                          </div>

                          <div className="mt-4 grid gap-4 md:grid-cols-2">
                            <label className="auth-checkbox">
                              <input
                                type="checkbox"
                                checked={draft.is_active}
                                onChange={(event) =>
                                  setAccountDrafts((current) => ({
                                    ...current,
                                    [account.id]: { ...draft, is_active: event.target.checked },
                                  }))
                                }
                              />
                              <span>Account is active</span>
                            </label>
                            <label className="auth-checkbox">
                              <input
                                type="checkbox"
                                checked={draft.role === "superadmin" || draft.all_locations}
                                disabled={draft.role === "superadmin"}
                                onChange={(event) =>
                                  setAccountDrafts((current) => ({
                                    ...current,
                                    [account.id]: { ...draft, all_locations: event.target.checked },
                                  }))
                                }
                              />
                              <span>All surveillance locations</span>
                            </label>
                          </div>

                          {draft.role !== "superadmin" && !draft.all_locations ? (
                            <div className="mt-4">
                              <div className="mb-2 text-sm font-medium text-slate-700">Allowed locations</div>
                              <div className="grid gap-2 sm:grid-cols-2">
                                {uniqueLocations.map((location) => (
                                  <label key={`${account.id}-${location}`} className="auth-checkbox">
                                    <input
                                      type="checkbox"
                                      checked={draft.allowed_locations.includes(location)}
                                      onChange={() => handleDraftLocationToggle(account.id, location)}
                                    />
                                    <span>{location}</span>
                                  </label>
                                ))}
                              </div>
                            </div>
                          ) : null}

                          <div className="mt-4">
                            <div className="mb-2 text-sm font-medium text-slate-700">Permissions</div>
                            <div className="grid gap-2 md:grid-cols-2">
                              {PERMISSION_META.map((permission) => (
                                <label key={`${account.id}-${permission.key}`} className="auth-checkbox auth-checkbox--stacked">
                                  <input
                                    type="checkbox"
                                    checked={draft.role === "superadmin" || draft.permissions[permission.key]}
                                    disabled={draft.role === "superadmin"}
                                    onChange={(event) =>
                                      handleDraftPermissionToggle(account.id, permission.key, event.target.checked)
                                    }
                                  />
                                  <span>
                                    <strong>{permission.label}</strong>
                                    <small>{permission.helper}</small>
                                  </span>
                                </label>
                              ))}
                            </div>
                          </div>

                          <div className="mt-4 flex justify-end">
                            <button
                              type="button"
                              className="admin-action-btn admin-action-btn--primary"
                              disabled={savingAdminId === account.id}
                              onClick={() => void handleSaveAdmin(account)}
                            >
                              {savingAdminId === account.id ? "Saving access…" : "Save access"}
                            </button>
                          </div>
                        </article>
                      );
                    })}
                  </div>
                </div>
              </div>
            </section>
          ) : null}

          {isLoading ? (
            <div className="dash-placeholder card-glass admin-empty-state">
              <h2 className="dash-placeholder-title">Loading surveillance registry</h2>
              <p>Pulling feed configuration from the Python backend.</p>
            </div>
          ) : null}

          {!isLoading && visibleCameras.length === 0 ? (
            <div className="dash-placeholder card-glass admin-empty-state">
              <h2 className="dash-placeholder-title">No matching feeds</h2>
              <p>Adjust the search or mode filter, or add more surveillance clips on the backend.</p>
            </div>
          ) : null}

          {!isLoading && visibleCameras.length > 0 ? (
            <div className="admin-feed-grid">
              {visibleCameras.map((camera) => {
                const draft = drafts[camera.id] ?? createCameraDraft(camera);
                const isDirty = isCameraDraftDirty(camera, draft);
                const isSaving = savingId === camera.id;
                const isRemoving = removingId === camera.id;
                const isSaved = savedId === camera.id && !isDirty;

                return (
                  <section key={camera.id} className="admin-feed-card">
                    <div className="admin-feed-preview">
                      {camera.video_url ? (
                        <video
                          src={camera.video_url}
                          className="admin-feed-image"
                          muted
                          autoPlay
                          loop
                          playsInline
                          preload="metadata"
                        />
                      ) : (
                        <div className="admin-feed-image admin-feed-image--empty">No preview</div>
                      )}
                      <div className="admin-feed-overlay">
                        <span className="admin-feed-status">{camera.status}</span>
                        <span className="admin-feed-mode-chip">
                          {draft.system_mode === "enforcement_mode" ? "Enforcement" : "Traffic light"}
                        </span>
                      </div>
                    </div>

                    <div className="admin-feed-content">
                      <div className="admin-feed-heading">
                        <div>
                          <p className="admin-card-eyebrow">{camera.id.toUpperCase()}</p>
                          <h2 className="admin-card-title">{draft.location}</h2>
                        </div>
                        <span className="admin-file-pill">{camera.file_name}</span>
                      </div>

                      <p className="admin-card-copy">
                        {camera.address || "Configured through the Python surveillance registry."}
                      </p>

                      <label className="admin-field">
                        <span className="admin-field-label">Display name</span>
                        <input
                          value={draft.location}
                          onChange={(event) => handleDraftChange(camera.id, "location", event.target.value)}
                          className="admin-input"
                          placeholder="Ward 4 Junction"
                        />
                      </label>

                      <div className="admin-field">
                        <span className="admin-field-label">Operating mode</span>
                        <div className="admin-mode-toggle" role="tablist" aria-label={`Mode for ${camera.id}`}>
                          {MODE_OPTIONS.map((option) => {
                            const isActive = draft.system_mode === option.value;
                            return (
                              <button
                                key={option.value}
                                type="button"
                                className={`admin-mode-option${isActive ? " admin-mode-option--active" : ""}`}
                                onClick={() => handleDraftChange(camera.id, "system_mode", option.value)}
                              >
                                <span>{option.label}</span>
                                <small>{option.helper}</small>
                              </button>
                            );
                          })}
                        </div>
                      </div>

                      <div className="admin-field">
                        <span className="admin-field-label">Shared runtime tuning</span>
                        <div className="grid gap-3 md:grid-cols-2">
                          <label className="admin-field">
                            <span className="admin-field-label">Frame skip</span>
                            <input
                              value={draft.frame_skip}
                              onChange={(event) => handleDraftChange(camera.id, "frame_skip", event.target.value)}
                              className="admin-input"
                              placeholder="1"
                              inputMode="numeric"
                            />
                          </label>
                          <label className="admin-field">
                            <span className="admin-field-label">FPS limit</span>
                            <input
                              value={draft.fps_limit}
                              onChange={(event) => handleDraftChange(camera.id, "fps_limit", event.target.value)}
                              className="admin-input"
                              placeholder="12"
                              inputMode="decimal"
                            />
                          </label>
                          <label className="admin-field">
                            <span className="admin-field-label">Resolution width</span>
                            <input
                              value={draft.resolution_width}
                              onChange={(event) => handleDraftChange(camera.id, "resolution_width", event.target.value)}
                              className="admin-input"
                              placeholder="1280"
                              inputMode="numeric"
                            />
                          </label>
                          <label className="admin-field">
                            <span className="admin-field-label">Resolution height</span>
                            <input
                              value={draft.resolution_height}
                              onChange={(event) => handleDraftChange(camera.id, "resolution_height", event.target.value)}
                              className="admin-input"
                              placeholder="720"
                              inputMode="numeric"
                            />
                          </label>
                          <label className="admin-field">
                            <span className="admin-field-label">ROI config path</span>
                            <input
                              value={draft.roi_config_path}
                              onChange={(event) => handleDraftChange(camera.id, "roi_config_path", event.target.value)}
                              className="admin-input"
                              placeholder="config/approach_rois_input6.json"
                            />
                          </label>
                          <label className="admin-field">
                            <span className="admin-field-label">Intersection ID</span>
                            <input
                              value={draft.intersection_id}
                              onChange={(event) => handleDraftChange(camera.id, "intersection_id", event.target.value)}
                              className="admin-input"
                              placeholder="lakeside-main"
                            />
                          </label>
                          <label className="admin-field md:col-span-2">
                            <span className="admin-field-label">Lane names</span>
                            <input
                              value={draft.lanes_text}
                              onChange={(event) => handleDraftChange(camera.id, "lanes_text", event.target.value)}
                              className="admin-input"
                              placeholder="north, south, east, west"
                            />
                          </label>
                          <label className="auth-checkbox">
                            <input
                              type="checkbox"
                              checked={draft.ocr_enabled}
                              onChange={(event) => handleDraftChange(camera.id, "ocr_enabled", event.target.checked)}
                            />
                            <span>Enable OCR</span>
                          </label>
                          <label className="auth-checkbox">
                            <input
                              type="checkbox"
                              checked={draft.ocr_debug}
                              onChange={(event) => handleDraftChange(camera.id, "ocr_debug", event.target.checked)}
                            />
                            <span>OCR debug</span>
                          </label>
                        </div>
                      </div>

                      <div className="admin-field">
                        <span className="admin-field-label">Enforcement tuning</span>
                        <div className="grid gap-3 md:grid-cols-2">
                          <label className="admin-field">
                            <span className="admin-field-label">Detector confidence</span>
                            <input
                              value={draft.confidence_threshold}
                              onChange={(event) => handleDraftChange(camera.id, "confidence_threshold", event.target.value)}
                              className="admin-input"
                              placeholder="0.25"
                              inputMode="decimal"
                            />
                          </label>
                          <label className="admin-field">
                            <span className="admin-field-label">Plate confidence</span>
                            <input
                              value={draft.plate_confidence_threshold}
                              onChange={(event) => handleDraftChange(camera.id, "plate_confidence_threshold", event.target.value)}
                              className="admin-input"
                              placeholder="0.25"
                              inputMode="decimal"
                            />
                          </label>
                          <label className="admin-field">
                            <span className="admin-field-label">Character confidence</span>
                            <input
                              value={draft.char_confidence_threshold}
                              onChange={(event) => handleDraftChange(camera.id, "char_confidence_threshold", event.target.value)}
                              className="admin-input"
                              placeholder="0.20"
                              inputMode="decimal"
                            />
                          </label>
                          <label className="admin-field">
                            <span className="admin-field-label">Helmet confidence</span>
                            <input
                              value={draft.helmet_confidence_threshold}
                              onChange={(event) => handleDraftChange(camera.id, "helmet_confidence_threshold", event.target.value)}
                              className="admin-input"
                              placeholder="0.30"
                              inputMode="decimal"
                            />
                          </label>
                          <label className="admin-field">
                            <span className="admin-field-label">Overspeed threshold km/h</span>
                            <input
                              value={draft.overspeed_threshold_kmh}
                              onChange={(event) => handleDraftChange(camera.id, "overspeed_threshold_kmh", event.target.value)}
                              className="admin-input"
                              placeholder="60"
                              inputMode="decimal"
                            />
                          </label>
                          <label className="admin-field">
                            <span className="admin-field-label">Helmet stability frames</span>
                            <input
                              value={draft.helmet_stability_frames}
                              onChange={(event) => handleDraftChange(camera.id, "helmet_stability_frames", event.target.value)}
                              className="admin-input"
                              placeholder="5"
                              inputMode="numeric"
                            />
                          </label>
                          <label className="admin-field">
                            <span className="admin-field-label">Speed line 1 Y</span>
                            <input
                              value={draft.line1_y}
                              onChange={(event) => handleDraftChange(camera.id, "line1_y", event.target.value)}
                              className="admin-input"
                              placeholder="0.50"
                              inputMode="decimal"
                            />
                          </label>
                          <label className="admin-field">
                            <span className="admin-field-label">Speed line 2 Y</span>
                            <input
                              value={draft.line2_y}
                              onChange={(event) => handleDraftChange(camera.id, "line2_y", event.target.value)}
                              className="admin-input"
                              placeholder="0.70"
                              inputMode="decimal"
                            />
                          </label>
                          <label className="admin-field">
                            <span className="admin-field-label">Line distance meters</span>
                            <input
                              value={draft.line_distance_meters}
                              onChange={(event) => handleDraftChange(camera.id, "line_distance_meters", event.target.value)}
                              className="admin-input"
                              placeholder="12"
                              inputMode="decimal"
                            />
                          </label>
                          <label className="admin-field">
                            <span className="admin-field-label">Line tolerance px</span>
                            <input
                              value={draft.line_tolerance_pixels}
                              onChange={(event) => handleDraftChange(camera.id, "line_tolerance_pixels", event.target.value)}
                              className="admin-input"
                              placeholder="15"
                              inputMode="numeric"
                            />
                          </label>
                        </div>
                      </div>

                      <div className="admin-field">
                        <span className="admin-field-label">Traffic management tuning</span>
                        <div className="grid gap-3 md:grid-cols-2">
                          <label className="admin-field">
                            <span className="admin-field-label">Stop speed threshold px</span>
                            <input
                              value={draft.stop_speed_threshold_px}
                              onChange={(event) => handleDraftChange(camera.id, "stop_speed_threshold_px", event.target.value)}
                              className="admin-input"
                              placeholder="2.0"
                              inputMode="decimal"
                            />
                          </label>
                          <label className="admin-field">
                            <span className="admin-field-label">Stop frames threshold</span>
                            <input
                              value={draft.stop_frames_threshold}
                              onChange={(event) => handleDraftChange(camera.id, "stop_frames_threshold", event.target.value)}
                              className="admin-input"
                              placeholder="5"
                              inputMode="numeric"
                            />
                          </label>
                          <label className="admin-field">
                            <span className="admin-field-label">Stop line distance px</span>
                            <input
                              value={draft.stop_line_distance_px}
                              onChange={(event) => handleDraftChange(camera.id, "stop_line_distance_px", event.target.value)}
                              className="admin-input"
                              placeholder="80"
                              inputMode="decimal"
                            />
                          </label>
                          <label className="admin-field">
                            <span className="admin-field-label">Initial active lane</span>
                            <input
                              value={draft.initial_active_lane}
                              onChange={(event) => handleDraftChange(camera.id, "initial_active_lane", event.target.value)}
                              className="admin-input"
                              placeholder="north"
                            />
                          </label>
                          <label className="admin-field">
                            <span className="admin-field-label">Min green time</span>
                            <input
                              value={draft.min_green_time}
                              onChange={(event) => handleDraftChange(camera.id, "min_green_time", event.target.value)}
                              className="admin-input"
                              placeholder="10"
                              inputMode="decimal"
                            />
                          </label>
                          <label className="admin-field">
                            <span className="admin-field-label">Max green time</span>
                            <input
                              value={draft.max_green_time}
                              onChange={(event) => handleDraftChange(camera.id, "max_green_time", event.target.value)}
                              className="admin-input"
                              placeholder="25"
                              inputMode="decimal"
                            />
                          </label>
                          <label className="admin-field">
                            <span className="admin-field-label">Yellow time</span>
                            <input
                              value={draft.yellow_time}
                              onChange={(event) => handleDraftChange(camera.id, "yellow_time", event.target.value)}
                              className="admin-input"
                              placeholder="3"
                              inputMode="decimal"
                            />
                          </label>
                          <label className="admin-field">
                            <span className="admin-field-label">Queue weight</span>
                            <input
                              value={draft.priority_queue_weight}
                              onChange={(event) => handleDraftChange(camera.id, "priority_queue_weight", event.target.value)}
                              className="admin-input"
                              placeholder="0.7"
                              inputMode="decimal"
                            />
                          </label>
                          <label className="admin-field">
                            <span className="admin-field-label">Wait weight</span>
                            <input
                              value={draft.priority_wait_weight}
                              onChange={(event) => handleDraftChange(camera.id, "priority_wait_weight", event.target.value)}
                              className="admin-input"
                              placeholder="0.3"
                              inputMode="decimal"
                            />
                          </label>
                          <label className="admin-field">
                            <span className="admin-field-label">Fairness weight</span>
                            <input
                              value={draft.fairness_weight}
                              onChange={(event) => handleDraftChange(camera.id, "fairness_weight", event.target.value)}
                              className="admin-input"
                              placeholder="0.1"
                              inputMode="decimal"
                            />
                          </label>
                          <label className="admin-field">
                            <span className="admin-field-label">Max priority score</span>
                            <input
                              value={draft.max_priority_score}
                              onChange={(event) => handleDraftChange(camera.id, "max_priority_score", event.target.value)}
                              className="admin-input"
                              placeholder="100"
                              inputMode="decimal"
                            />
                          </label>
                        </div>
                      </div>

                      <div className="admin-card-links">
                        {camera.location_link ? (
                          <a
                            href={camera.location_link}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="admin-card-link"
                          >
                            Open map link
                          </a>
                        ) : null}
                        {camera.video_url ? (
                          <a
                            href={camera.video_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="admin-card-link"
                          >
                            Open source clip
                          </a>
                        ) : null}
                      </div>

                      <div className="admin-card-footer">
                        <div className="admin-card-state">
                          {isDirty ? <span className="admin-state-pill admin-state-pill--dirty">Pending changes</span> : null}
                          {isSaved ? <span className="admin-state-pill admin-state-pill--saved">Saved</span> : null}
                        </div>

                        <div className="admin-card-actions">
                          <button
                            type="button"
                            className="admin-action-btn admin-action-btn--ghost"
                            onClick={() => handleReset(camera)}
                            disabled={!isDirty || isSaving || isRemoving}
                          >
                            Reset
                          </button>
                          <button
                            type="button"
                            className="admin-action-btn admin-action-btn--danger"
                            onClick={() => void handleRemove(camera)}
                            disabled={isSaving || isRemoving}
                          >
                            {isRemoving ? "Removing…" : "Remove feed"}
                          </button>
                          <button
                            type="button"
                            className="admin-action-btn admin-action-btn--primary"
                            onClick={() => void handleSave(camera.id)}
                            disabled={!isDirty || isSaving || isRemoving}
                          >
                            {isSaving ? "Saving…" : "Save changes"}
                          </button>
                        </div>
                      </div>
                    </div>
                  </section>
                );
              })}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
