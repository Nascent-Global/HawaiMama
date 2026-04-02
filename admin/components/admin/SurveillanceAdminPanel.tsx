"use client";

import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";
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

function SectionFrame({
  kicker,
  title,
  actions,
  children,
}: {
  kicker: string;
  title: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="border border-[var(--gov-line)] bg-white">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--gov-line)] bg-[var(--gov-paper-alt)] px-4 py-3">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--gov-red)]">{kicker}</div>
          <h2 className="mt-1 text-lg font-bold text-[var(--gov-ink)] [font-family:var(--font-heading)]">{title}</h2>
        </div>
        {actions}
      </div>
      <div className="px-4 py-4">{children}</div>
    </section>
  );
}

function StatCell({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="border border-[var(--gov-line)] bg-[var(--gov-paper-alt)] px-4 py-3">
      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--gov-muted)]">{label}</div>
      <div className="mt-2 text-2xl font-bold text-[var(--gov-ink)]">{value}</div>
    </div>
  );
}

function Field({
  label,
  children,
  wide = false,
}: {
  label: string;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <label className={`grid gap-2 ${wide ? "md:col-span-2" : ""}`}>
      <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)]">{label}</span>
      {children}
    </label>
  );
}

function textInputClass() {
  return "w-full border border-[var(--gov-line-strong)] bg-white px-3 py-2 text-sm text-[var(--gov-ink)] outline-none placeholder:text-[var(--gov-muted)] focus:border-[var(--gov-blue)]";
}

function checkboxClass() {
  return "h-4 w-4 rounded-none border-[var(--gov-line-strong)] text-[var(--gov-blue)] focus:ring-[var(--gov-blue)]";
}

function ModeButtons({
  value,
  onChange,
}: {
  value: SurveillanceCameraConfig["system_mode"];
  onChange: (value: SurveillanceCameraConfig["system_mode"]) => void;
}) {
  return (
    <div className="grid gap-2 md:grid-cols-2">
      {MODE_OPTIONS.map((option) => {
        const active = value === option.value;
        return (
          <button
            key={option.value}
            type="button"
            className={`border px-3 py-3 text-left ${
              active ? "border-[var(--gov-blue)] bg-[var(--gov-highlight)]" : "border-[var(--gov-line)] bg-white"
            }`}
            onClick={() => onChange(option.value)}
          >
            <div className="text-sm font-semibold text-[var(--gov-ink)]">{option.label}</div>
            <div className="mt-1 text-xs text-[var(--gov-muted)]">{option.helper}</div>
          </button>
        );
      })}
    </div>
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
  const [expandedCameraId, setExpandedCameraId] = useState<string | null>(null);
  const [expandedAccountId, setExpandedAccountId] = useState<string | null>(null);
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

  const activeFeedCount = useMemo(() => cameras.filter((camera) => camera.status === "active").length, [cameras]);

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
    <div className="grid min-h-[calc(100dvh-32px)] grid-rows-[auto_1fr] overflow-hidden border border-[var(--gov-line-strong)] bg-[var(--gov-paper)] shadow-[0_20px_45px_rgba(18,35,61,0.08)]" suppressHydrationWarning>
      <header className="border-b border-[var(--gov-line-strong)] bg-[var(--gov-paper-alt)]">
        <div className="h-2 w-full bg-[linear-gradient(90deg,#c1272d_0%,#c1272d_20%,#003893_20%,#003893_100%)]" />
        <div className="flex flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-5">
          <div className="flex items-center gap-4">
            <div className="flex h-14 w-14 items-center justify-center border border-[var(--gov-line)] bg-white p-2">
              <Image src="/logo.png" alt="Hawai Mama" width={44} height={44} className="h-auto w-auto max-h-10 max-w-10 object-contain" priority />
            </div>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--gov-red)]">Configuration Registry</p>
              <h1 className="mt-1 text-xl font-bold text-[var(--gov-ink)] [font-family:var(--font-heading)]">Feed and Access Administration</h1>
              <p className="mt-1 text-sm text-[var(--gov-muted)]">
                Government-style operational console for surveillance sources, runtime settings, and office permissions.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-3">
            <div className="relative">
              <input
                type="search"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="Search feeds, files, locations..."
                className={`${textInputClass()} min-w-[280px] pl-3 pr-10`}
              />
              <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[var(--gov-muted)]">
                <SearchIcon />
              </span>
            </div>
            {admin ? (
              <div className="flex items-center gap-3 border border-[var(--gov-line)] bg-white px-3 py-2">
                <div className="text-right">
                  <div className="text-sm font-semibold text-[var(--gov-ink)]">{admin.full_name}</div>
                  <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--gov-muted)]">
                    {admin.role === "superadmin" ? "Superadmin" : "Admin"}
                  </div>
                </div>
                <button
                  type="button"
                  className="border border-[var(--gov-line-strong)] px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)] hover:border-[var(--gov-red)] hover:text-[var(--gov-red-dark)]"
                  onClick={() => void logout()}
                >
                  Logout
                </button>
              </div>
            ) : null}
            <button
              type="button"
              className="inline-flex items-center gap-2 border border-[var(--gov-line-strong)] bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)] hover:border-[var(--gov-blue)] hover:text-[var(--gov-blue)]"
              onClick={() => {
                void refreshCameras();
                void refreshAccounts();
              }}
              disabled={isRefreshing || accountsLoading}
            >
              <RefreshIcon />
              <span>{isRefreshing || accountsLoading ? "Refreshing..." : "Refresh"}</span>
            </button>
            <Link
              href="/"
              className="border border-[var(--gov-blue)] bg-[var(--gov-blue)] px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-white hover:bg-[var(--gov-blue-dark)]"
            >
              Dashboard
            </Link>
          </div>
        </div>
      </header>

      <div className="gov-scrollbar min-h-0 overflow-auto px-4 py-4 sm:px-5">
        <div className="grid gap-3 md:grid-cols-5">
          <StatCell label="Total feeds" value={cameras.length} />
          <StatCell label="Active feeds" value={activeFeedCount} />
          <StatCell label="Enforcement" value={enforcementCount} />
          <StatCell label="Traffic mode" value={trafficCount} />
          <StatCell label="Unsaved drafts" value={dirtyCount} />
        </div>

        {error ? (
          <div className="mt-4 border border-[var(--gov-red)] bg-[rgba(193,39,45,0.08)] px-4 py-3 text-sm text-[var(--gov-red-dark)]">{error}</div>
        ) : null}
        {accountsError ? (
          <div className="mt-4 border border-[var(--gov-red)] bg-[rgba(193,39,45,0.08)] px-4 py-3 text-sm text-[var(--gov-red-dark)]">{accountsError}</div>
        ) : null}

        <div className="mt-4 grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
          <div className="space-y-4">
            <SectionFrame kicker="New Source" title="Add Surveillance Feed">
              <div className="grid gap-4">
                <Field label="Surveillance location">
                  <input
                    value={uploadLocation}
                    onChange={(event) => setUploadLocation(event.target.value)}
                    className={textInputClass()}
                    placeholder="Lakeside Gate 2"
                  />
                </Field>
                <Field label="Default mode">
                  <ModeButtons value={uploadMode} onChange={setUploadMode} />
                </Field>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="video/*,.mp4,.mov,.m4v,.webm,.avi,.mkv"
                  className="hidden"
                  onChange={(event) => setSelectedUploadFile(event.target.files?.[0] ?? null)}
                />
                <div className="border border-[var(--gov-line)] bg-[var(--gov-paper-alt)] px-3 py-3 text-sm text-[var(--gov-muted)]">
                  <div>{selectedUploadFile?.name || "No video file selected"}</div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="border border-[var(--gov-line-strong)] bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)] hover:border-[var(--gov-blue)] hover:text-[var(--gov-blue)]"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    Choose video
                  </button>
                  <button
                    type="button"
                    className="bg-[var(--gov-blue)] px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-white hover:bg-[var(--gov-blue-dark)] disabled:opacity-60"
                    onClick={() => void handleUpload()}
                    disabled={isUploading || !selectedUploadFile || !uploadLocation.trim()}
                  >
                    {isUploading ? "Adding..." : "Add feed"}
                  </button>
                </div>
              </div>
            </SectionFrame>

            <SectionFrame kicker="Feed Scope" title="Registry Filter">
              <div className="grid gap-2">
                {(["all", "enforcement_mode", "traffic_management_mode"] as const).map((value) => (
                  <button
                    key={value}
                    type="button"
                    className={`border px-3 py-3 text-left text-sm font-semibold uppercase tracking-[0.1em] ${
                      modeFilter === value
                        ? "border-[var(--gov-blue)] bg-[var(--gov-highlight)] text-[var(--gov-blue)]"
                        : "border-[var(--gov-line)] bg-white text-[var(--gov-muted)]"
                    }`}
                    onClick={() => setModeFilter(value)}
                  >
                    {value === "all" ? "All feeds" : value === "enforcement_mode" ? "Enforcement mode" : "Traffic mode"}
                  </button>
                ))}
              </div>
            </SectionFrame>
          </div>

          <div className="space-y-4">
            {canManageAdmins ? (
              <SectionFrame kicker="Office Access" title="Admin Accounts">
                <div className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
                  <div className="space-y-4 border border-[var(--gov-line)] bg-[var(--gov-paper-alt)] px-4 py-4">
                    <div className="text-sm font-semibold text-[var(--gov-ink)]">Create office admin</div>
                    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-1">
                      <Field label="Username">
                        <input
                          value={newAdmin.username}
                          onChange={(event) => setNewAdmin((current) => ({ ...current, username: event.target.value }))}
                          placeholder="ward7_admin"
                          className={textInputClass()}
                        />
                      </Field>
                      <Field label="Full name">
                        <input
                          value={newAdmin.full_name}
                          onChange={(event) => setNewAdmin((current) => ({ ...current, full_name: event.target.value }))}
                          placeholder="Ward 7 Operations Desk"
                          className={textInputClass()}
                        />
                      </Field>
                      <Field label="Temporary password">
                        <input
                          type="password"
                          value={newAdmin.password}
                          onChange={(event) => setNewAdmin((current) => ({ ...current, password: event.target.value }))}
                          placeholder="Create a password"
                          className={textInputClass()}
                        />
                      </Field>
                      <Field label="Role">
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
                          className={textInputClass()}
                        >
                          <option value="admin">Admin</option>
                          <option value="superadmin">Superadmin</option>
                        </select>
                      </Field>
                    </div>

                    <label className="flex items-center gap-3 text-sm text-[var(--gov-ink)]">
                      <input
                        type="checkbox"
                        className={checkboxClass()}
                        checked={newAdmin.is_active}
                        onChange={(event) => setNewAdmin((current) => ({ ...current, is_active: event.target.checked }))}
                      />
                      <span>Account is active</span>
                    </label>
                    <label className="flex items-center gap-3 text-sm text-[var(--gov-ink)]">
                      <input
                        type="checkbox"
                        className={checkboxClass()}
                        checked={newAdmin.role === "superadmin" || newAdmin.all_locations}
                        disabled={newAdmin.role === "superadmin"}
                        onChange={(event) => setNewAdmin((current) => ({ ...current, all_locations: event.target.checked }))}
                      />
                      <span>Can access every surveillance location</span>
                    </label>

                    {newAdmin.role !== "superadmin" && !newAdmin.all_locations ? (
                      <div>
                        <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)]">Allowed locations</div>
                        <div className="grid gap-2 sm:grid-cols-2">
                          {uniqueLocations.map((location) => (
                            <label key={location} className="flex items-center gap-3 border border-[var(--gov-line)] bg-white px-3 py-2 text-sm text-[var(--gov-ink)]">
                              <input
                                type="checkbox"
                                className={checkboxClass()}
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
                      <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)]">Permissions</div>
                      <div className="grid gap-2">
                        {PERMISSION_META.map((permission) => (
                          <label key={permission.key} className="flex gap-3 border border-[var(--gov-line)] bg-white px-3 py-3 text-sm text-[var(--gov-ink)]">
                            <input
                              type="checkbox"
                              className={`${checkboxClass()} mt-0.5`}
                              checked={newAdmin.role === "superadmin" || newAdmin.permissions[permission.key]}
                              disabled={newAdmin.role === "superadmin"}
                              onChange={(event) =>
                                setNewAdmin((current) => ({
                                  ...current,
                                  permissions: { ...current.permissions, [permission.key]: event.target.checked },
                                }))
                              }
                            />
                            <span>
                              <strong className="block">{permission.label}</strong>
                              <span className="mt-1 block text-xs text-[var(--gov-muted)]">{permission.helper}</span>
                            </span>
                          </label>
                        ))}
                      </div>
                    </div>

                    <button
                      type="button"
                      className="bg-[var(--gov-blue)] px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-white hover:bg-[var(--gov-blue-dark)] disabled:opacity-60"
                      disabled={!newAdmin.username.trim() || !newAdmin.full_name.trim() || !newAdmin.password || creatingAdmin}
                      onClick={() => void handleCreateAdmin()}
                    >
                      {creatingAdmin ? "Creating..." : "Create admin"}
                    </button>
                  </div>

                  <div className="min-h-[240px] border border-[var(--gov-line)] bg-white">
                    <div className="grid grid-cols-[minmax(0,1fr)_120px_120px] border-b border-[var(--gov-line-strong)] bg-[var(--gov-highlight)] px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--gov-muted)]">
                      <span>Account</span>
                      <span>Status</span>
                      <span>Actions</span>
                    </div>
                    {accountsLoading ? <div className="px-4 py-6 text-sm text-[var(--gov-muted)]">Loading admin accounts...</div> : null}
                    <div className="divide-y divide-[var(--gov-line)]">
                      {accounts.map((account) => {
                        const draft = accountDrafts[account.id] ?? createAdminDrafts([account])[account.id];
                        const expanded = expandedAccountId === account.id;
                        return (
                          <div key={account.id}>
                            <div className="grid items-center gap-3 px-4 py-3 md:grid-cols-[minmax(0,1fr)_120px_120px]">
                              <div>
                                <div className="text-sm font-semibold text-[var(--gov-ink)]">{account.username}</div>
                                <div className="mt-1 text-xs text-[var(--gov-muted)]">
                                  {draft.full_name} | {account.role === "superadmin" ? "Superadmin" : "Office admin"}
                                </div>
                              </div>
                              <div>
                                <span className={`inline-flex border px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.15em] ${
                                  draft.is_active
                                    ? "border-emerald-700 bg-emerald-50 text-emerald-800"
                                    : "border-[var(--gov-red)] bg-[rgba(193,39,45,0.08)] text-[var(--gov-red-dark)]"
                                }`}>
                                  {draft.is_active ? "Active" : "Disabled"}
                                </span>
                              </div>
                              <div className="flex justify-start md:justify-end">
                                <button
                                  type="button"
                                  className="border border-[var(--gov-line-strong)] px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)] hover:border-[var(--gov-blue)] hover:text-[var(--gov-blue)]"
                                  onClick={() => setExpandedAccountId(expanded ? null : account.id)}
                                >
                                  {expanded ? "Hide" : "Manage"}
                                </button>
                              </div>
                            </div>
                            {expanded ? (
                              <div className="border-t border-[var(--gov-line)] bg-[var(--gov-paper-alt)] px-4 py-4">
                                <div className="grid gap-4 xl:grid-cols-2">
                                  <Field label="Display name">
                                    <input
                                      value={draft.full_name}
                                      onChange={(event) =>
                                        setAccountDrafts((current) => ({
                                          ...current,
                                          [account.id]: { ...draft, full_name: event.target.value },
                                        }))
                                      }
                                      className={textInputClass()}
                                    />
                                  </Field>
                                  <Field label="Reset password">
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
                                      className={textInputClass()}
                                    />
                                  </Field>
                                </div>

                                <div className="mt-4 grid gap-3 md:grid-cols-2">
                                  <label className="flex items-center gap-3 text-sm text-[var(--gov-ink)]">
                                    <input
                                      type="checkbox"
                                      className={checkboxClass()}
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
                                  <label className="flex items-center gap-3 text-sm text-[var(--gov-ink)]">
                                    <input
                                      type="checkbox"
                                      className={checkboxClass()}
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
                                    <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)]">Allowed locations</div>
                                    <div className="grid gap-2 sm:grid-cols-2">
                                      {uniqueLocations.map((location) => (
                                        <label key={`${account.id}-${location}`} className="flex items-center gap-3 border border-[var(--gov-line)] bg-white px-3 py-2 text-sm text-[var(--gov-ink)]">
                                          <input
                                            type="checkbox"
                                            className={checkboxClass()}
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
                                  <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)]">Permissions</div>
                                  <div className="grid gap-2 xl:grid-cols-2">
                                    {PERMISSION_META.map((permission) => (
                                      <label key={`${account.id}-${permission.key}`} className="flex gap-3 border border-[var(--gov-line)] bg-white px-3 py-3 text-sm text-[var(--gov-ink)]">
                                        <input
                                          type="checkbox"
                                          className={`${checkboxClass()} mt-0.5`}
                                          checked={draft.role === "superadmin" || draft.permissions[permission.key]}
                                          disabled={draft.role === "superadmin"}
                                          onChange={(event) => handleDraftPermissionToggle(account.id, permission.key, event.target.checked)}
                                        />
                                        <span>
                                          <strong className="block">{permission.label}</strong>
                                          <span className="mt-1 block text-xs text-[var(--gov-muted)]">{permission.helper}</span>
                                        </span>
                                      </label>
                                    ))}
                                  </div>
                                </div>

                                <div className="mt-4 flex justify-end">
                                  <button
                                    type="button"
                                    className="bg-[var(--gov-blue)] px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-white hover:bg-[var(--gov-blue-dark)] disabled:opacity-60"
                                    disabled={savingAdminId === account.id}
                                    onClick={() => void handleSaveAdmin(account)}
                                  >
                                    {savingAdminId === account.id ? "Saving..." : "Save access"}
                                  </button>
                                </div>
                              </div>
                            ) : null}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </SectionFrame>
            ) : null}

            <SectionFrame
              kicker="Feed Register"
              title="Camera Configuration"
              actions={
                <span className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)]">
                  {visibleCameras.length} visible feeds
                </span>
              }
            >
              {isLoading ? <div className="py-6 text-sm text-[var(--gov-muted)]">Loading surveillance registry...</div> : null}
              {!isLoading && visibleCameras.length === 0 ? (
                <div className="border border-dashed border-[var(--gov-line-strong)] bg-[var(--gov-paper-alt)] px-4 py-8 text-sm text-[var(--gov-muted)]">
                  No feeds match the current search or mode filter.
                </div>
              ) : null}

              {!isLoading && visibleCameras.length > 0 ? (
                <div className="border border-[var(--gov-line)] bg-white">
                  <div className="hidden grid-cols-[140px_minmax(0,1fr)_150px_120px_120px] border-b border-[var(--gov-line-strong)] bg-[var(--gov-highlight)] px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--gov-muted)] md:grid">
                    <span>Feed ID</span>
                    <span>Location and File</span>
                    <span>Mode</span>
                    <span>Status</span>
                    <span>Actions</span>
                  </div>
                  <div className="divide-y divide-[var(--gov-line)]">
                    {visibleCameras.map((camera) => {
                      const draft = drafts[camera.id] ?? createCameraDraft(camera);
                      const isDirty = isCameraDraftDirty(camera, draft);
                      const isSaving = savingId === camera.id;
                      const isRemoving = removingId === camera.id;
                      const isSaved = savedId === camera.id && !isDirty;
                      const expanded = expandedCameraId === camera.id;

                      return (
                        <div key={camera.id}>
                          <div className="grid items-center gap-3 px-4 py-3 md:grid-cols-[140px_minmax(0,1fr)_150px_120px_120px]">
                            <div>
                              <div className="text-sm font-semibold uppercase tracking-[0.14em] text-[var(--gov-blue)]">{camera.id}</div>
                              <div className="mt-1 text-xs text-[var(--gov-muted)]">{camera.file_name}</div>
                            </div>
                            <div className="min-w-0">
                              <div className="truncate text-sm font-semibold text-[var(--gov-ink)]">{draft.location || "Unnamed feed"}</div>
                              <div className="mt-1 truncate text-xs text-[var(--gov-muted)]">{camera.address || "Configured through backend registry."}</div>
                            </div>
                            <div className="text-xs font-semibold uppercase tracking-[0.15em] text-[var(--gov-muted)]">
                              {draft.system_mode === "enforcement_mode" ? "Enforcement" : "Traffic light"}
                            </div>
                            <div className="flex items-center gap-2">
                              <span className={`inline-flex border px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.15em] ${
                                camera.status === "active"
                                  ? "border-emerald-700 bg-emerald-50 text-emerald-800"
                                  : "border-[var(--gov-red)] bg-[rgba(193,39,45,0.08)] text-[var(--gov-red-dark)]"
                              }`}>
                                {camera.status}
                              </span>
                              {isDirty ? (
                                <span className="inline-flex border border-[var(--gov-blue)] bg-[rgba(0,56,147,0.08)] px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.15em] text-[var(--gov-blue)]">
                                  Draft
                                </span>
                              ) : null}
                              {isSaved ? (
                                <span className="inline-flex border border-emerald-700 bg-emerald-50 px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.15em] text-emerald-800">
                                  Saved
                                </span>
                              ) : null}
                            </div>
                            <div className="flex justify-start md:justify-end">
                              <button
                                type="button"
                                className="border border-[var(--gov-line-strong)] px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)] hover:border-[var(--gov-blue)] hover:text-[var(--gov-blue)]"
                                onClick={() => setExpandedCameraId(expanded ? null : camera.id)}
                              >
                                {expanded ? "Hide" : "Edit"}
                              </button>
                            </div>
                          </div>

                          {expanded ? (
                            <div className="border-t border-[var(--gov-line)] bg-[var(--gov-paper-alt)] px-4 py-4">
                              <div className="grid gap-4 xl:grid-cols-[240px_minmax(0,1fr)]">
                                <div className="space-y-3">
                                  <div className="overflow-hidden border border-[var(--gov-line)] bg-black">
                                    {camera.video_url ? (
                                      <video src={camera.video_url} className="aspect-video w-full object-cover" muted autoPlay loop playsInline preload="metadata" />
                                    ) : (
                                      <div className="flex aspect-video items-center justify-center text-sm text-white/70">No preview</div>
                                    )}
                                  </div>
                                  <div className="space-y-2 text-sm">
                                    {camera.location_link ? (
                                      <a href={camera.location_link} target="_blank" rel="noopener noreferrer" className="block text-[var(--gov-blue)] underline underline-offset-4">
                                        Open map link
                                      </a>
                                    ) : null}
                                    {camera.video_url ? (
                                      <a href={camera.video_url} target="_blank" rel="noopener noreferrer" className="block text-[var(--gov-blue)] underline underline-offset-4">
                                        Open source clip
                                      </a>
                                    ) : null}
                                  </div>
                                </div>

                                <div className="space-y-4">
                                  <div className="grid gap-4 md:grid-cols-2">
                                    <Field label="Display name">
                                      <input
                                        value={draft.location}
                                        onChange={(event) => handleDraftChange(camera.id, "location", event.target.value)}
                                        className={textInputClass()}
                                        placeholder="Ward 4 Junction"
                                      />
                                    </Field>
                                    <Field label="Intersection ID">
                                      <input
                                        value={draft.intersection_id}
                                        onChange={(event) => handleDraftChange(camera.id, "intersection_id", event.target.value)}
                                        className={textInputClass()}
                                        placeholder="lakeside-main"
                                      />
                                    </Field>
                                    <Field label="Lane names" wide>
                                      <input
                                        value={draft.lanes_text}
                                        onChange={(event) => handleDraftChange(camera.id, "lanes_text", event.target.value)}
                                        className={textInputClass()}
                                        placeholder="north, south, east, west"
                                      />
                                    </Field>
                                  </div>

                                  <Field label="Operating mode">
                                    <ModeButtons value={draft.system_mode} onChange={(value) => handleDraftChange(camera.id, "system_mode", value)} />
                                  </Field>

                                  <div className="grid gap-4">
                                    <div className="border border-[var(--gov-line)] bg-white px-4 py-4">
                                      <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)]">Shared runtime tuning</div>
                                      <div className="grid gap-3 md:grid-cols-2">
                                        <Field label="Frame skip"><input value={draft.frame_skip} onChange={(event) => handleDraftChange(camera.id, "frame_skip", event.target.value)} className={textInputClass()} inputMode="numeric" placeholder="1" /></Field>
                                        <Field label="FPS limit"><input value={draft.fps_limit} onChange={(event) => handleDraftChange(camera.id, "fps_limit", event.target.value)} className={textInputClass()} inputMode="decimal" placeholder="12" /></Field>
                                        <Field label="Resolution width"><input value={draft.resolution_width} onChange={(event) => handleDraftChange(camera.id, "resolution_width", event.target.value)} className={textInputClass()} inputMode="numeric" placeholder="1280" /></Field>
                                        <Field label="Resolution height"><input value={draft.resolution_height} onChange={(event) => handleDraftChange(camera.id, "resolution_height", event.target.value)} className={textInputClass()} inputMode="numeric" placeholder="720" /></Field>
                                        <Field label="ROI config path"><input value={draft.roi_config_path} onChange={(event) => handleDraftChange(camera.id, "roi_config_path", event.target.value)} className={textInputClass()} placeholder="config/roi.json" /></Field>
                                        <div className="grid gap-3 content-start">
                                          <label className="flex items-center gap-3 text-sm text-[var(--gov-ink)]">
                                            <input type="checkbox" className={checkboxClass()} checked={draft.ocr_enabled} onChange={(event) => handleDraftChange(camera.id, "ocr_enabled", event.target.checked)} />
                                            <span>Enable OCR</span>
                                          </label>
                                          <label className="flex items-center gap-3 text-sm text-[var(--gov-ink)]">
                                            <input type="checkbox" className={checkboxClass()} checked={draft.ocr_debug} onChange={(event) => handleDraftChange(camera.id, "ocr_debug", event.target.checked)} />
                                            <span>OCR debug</span>
                                          </label>
                                        </div>
                                      </div>
                                    </div>

                                    <div className="border border-[var(--gov-line)] bg-white px-4 py-4">
                                      <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)]">Enforcement tuning</div>
                                      <div className="grid gap-3 md:grid-cols-2">
                                        <Field label="Detector confidence"><input value={draft.confidence_threshold} onChange={(event) => handleDraftChange(camera.id, "confidence_threshold", event.target.value)} className={textInputClass()} inputMode="decimal" placeholder="0.25" /></Field>
                                        <Field label="Plate confidence"><input value={draft.plate_confidence_threshold} onChange={(event) => handleDraftChange(camera.id, "plate_confidence_threshold", event.target.value)} className={textInputClass()} inputMode="decimal" placeholder="0.25" /></Field>
                                        <Field label="Character confidence"><input value={draft.char_confidence_threshold} onChange={(event) => handleDraftChange(camera.id, "char_confidence_threshold", event.target.value)} className={textInputClass()} inputMode="decimal" placeholder="0.20" /></Field>
                                        <Field label="Helmet confidence"><input value={draft.helmet_confidence_threshold} onChange={(event) => handleDraftChange(camera.id, "helmet_confidence_threshold", event.target.value)} className={textInputClass()} inputMode="decimal" placeholder="0.30" /></Field>
                                        <Field label="Overspeed threshold km/h"><input value={draft.overspeed_threshold_kmh} onChange={(event) => handleDraftChange(camera.id, "overspeed_threshold_kmh", event.target.value)} className={textInputClass()} inputMode="decimal" placeholder="60" /></Field>
                                        <Field label="Helmet stability frames"><input value={draft.helmet_stability_frames} onChange={(event) => handleDraftChange(camera.id, "helmet_stability_frames", event.target.value)} className={textInputClass()} inputMode="numeric" placeholder="5" /></Field>
                                        <Field label="Speed line 1 Y"><input value={draft.line1_y} onChange={(event) => handleDraftChange(camera.id, "line1_y", event.target.value)} className={textInputClass()} inputMode="decimal" placeholder="0.50" /></Field>
                                        <Field label="Speed line 2 Y"><input value={draft.line2_y} onChange={(event) => handleDraftChange(camera.id, "line2_y", event.target.value)} className={textInputClass()} inputMode="decimal" placeholder="0.70" /></Field>
                                        <Field label="Line distance meters"><input value={draft.line_distance_meters} onChange={(event) => handleDraftChange(camera.id, "line_distance_meters", event.target.value)} className={textInputClass()} inputMode="decimal" placeholder="12" /></Field>
                                        <Field label="Line tolerance px"><input value={draft.line_tolerance_pixels} onChange={(event) => handleDraftChange(camera.id, "line_tolerance_pixels", event.target.value)} className={textInputClass()} inputMode="numeric" placeholder="15" /></Field>
                                      </div>
                                    </div>

                                    <div className="border border-[var(--gov-line)] bg-white px-4 py-4">
                                      <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)]">Traffic management tuning</div>
                                      <div className="grid gap-3 md:grid-cols-2">
                                        <Field label="Stop speed threshold px"><input value={draft.stop_speed_threshold_px} onChange={(event) => handleDraftChange(camera.id, "stop_speed_threshold_px", event.target.value)} className={textInputClass()} inputMode="decimal" placeholder="2.0" /></Field>
                                        <Field label="Stop frames threshold"><input value={draft.stop_frames_threshold} onChange={(event) => handleDraftChange(camera.id, "stop_frames_threshold", event.target.value)} className={textInputClass()} inputMode="numeric" placeholder="5" /></Field>
                                        <Field label="Stop line distance px"><input value={draft.stop_line_distance_px} onChange={(event) => handleDraftChange(camera.id, "stop_line_distance_px", event.target.value)} className={textInputClass()} inputMode="decimal" placeholder="80" /></Field>
                                        <Field label="Initial active lane"><input value={draft.initial_active_lane} onChange={(event) => handleDraftChange(camera.id, "initial_active_lane", event.target.value)} className={textInputClass()} placeholder="north" /></Field>
                                        <Field label="Min green time"><input value={draft.min_green_time} onChange={(event) => handleDraftChange(camera.id, "min_green_time", event.target.value)} className={textInputClass()} inputMode="decimal" placeholder="10" /></Field>
                                        <Field label="Max green time"><input value={draft.max_green_time} onChange={(event) => handleDraftChange(camera.id, "max_green_time", event.target.value)} className={textInputClass()} inputMode="decimal" placeholder="25" /></Field>
                                        <Field label="Yellow time"><input value={draft.yellow_time} onChange={(event) => handleDraftChange(camera.id, "yellow_time", event.target.value)} className={textInputClass()} inputMode="decimal" placeholder="3" /></Field>
                                        <Field label="Queue weight"><input value={draft.priority_queue_weight} onChange={(event) => handleDraftChange(camera.id, "priority_queue_weight", event.target.value)} className={textInputClass()} inputMode="decimal" placeholder="0.7" /></Field>
                                        <Field label="Wait weight"><input value={draft.priority_wait_weight} onChange={(event) => handleDraftChange(camera.id, "priority_wait_weight", event.target.value)} className={textInputClass()} inputMode="decimal" placeholder="0.3" /></Field>
                                        <Field label="Fairness weight"><input value={draft.fairness_weight} onChange={(event) => handleDraftChange(camera.id, "fairness_weight", event.target.value)} className={textInputClass()} inputMode="decimal" placeholder="0.1" /></Field>
                                        <Field label="Max priority score"><input value={draft.max_priority_score} onChange={(event) => handleDraftChange(camera.id, "max_priority_score", event.target.value)} className={textInputClass()} inputMode="decimal" placeholder="100" /></Field>
                                      </div>
                                    </div>
                                  </div>

                                  <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--gov-line)] pt-4">
                                    <div className="flex flex-wrap gap-2">
                                      {isDirty ? (
                                        <span className="inline-flex border border-[var(--gov-blue)] bg-[rgba(0,56,147,0.08)] px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.15em] text-[var(--gov-blue)]">
                                          Pending changes
                                        </span>
                                      ) : null}
                                      {isSaved ? (
                                        <span className="inline-flex border border-emerald-700 bg-emerald-50 px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.15em] text-emerald-800">
                                          Saved
                                        </span>
                                      ) : null}
                                    </div>
                                    <div className="flex flex-wrap gap-2">
                                      <button
                                        type="button"
                                        className="border border-[var(--gov-line-strong)] bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)] hover:border-[var(--gov-blue)] hover:text-[var(--gov-blue)] disabled:opacity-60"
                                        onClick={() => handleReset(camera)}
                                        disabled={!isDirty || isSaving || isRemoving}
                                      >
                                        Reset
                                      </button>
                                      <button
                                        type="button"
                                        className="border border-[var(--gov-red)] bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--gov-red-dark)] hover:bg-[rgba(193,39,45,0.06)] disabled:opacity-60"
                                        onClick={() => void handleRemove(camera)}
                                        disabled={isSaving || isRemoving}
                                      >
                                        {isRemoving ? "Removing..." : "Remove"}
                                      </button>
                                      <button
                                        type="button"
                                        className="bg-[var(--gov-blue)] px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-white hover:bg-[var(--gov-blue-dark)] disabled:opacity-60"
                                        onClick={() => void handleSave(camera.id)}
                                        disabled={!isDirty || isSaving || isRemoving}
                                      >
                                        {isSaving ? "Saving..." : "Save"}
                                      </button>
                                    </div>
                                  </div>
                                </div>
                              </div>
                            </div>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : null}
            </SectionFrame>
          </div>
        </div>
      </div>
    </div>
  );
}
