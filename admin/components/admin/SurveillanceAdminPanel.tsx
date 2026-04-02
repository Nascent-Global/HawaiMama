"use client";

/* eslint-disable @next/next/no-img-element */

import Image from "next/image";
import Link from "next/link";
import {
  useDeferredValue,
  useMemo,
  useRef,
  useState,
} from "react";
import { createCameraConfig, deleteCameraConfig, getCameraConfigs, updateCameraConfig } from "@/lib/api";
import type { SurveillanceCameraConfig } from "@/types/camera-config";

type CameraDraft = {
  location: string;
  system_mode: SurveillanceCameraConfig["system_mode"];
};

type Drafts = Record<string, CameraDraft>;
type ModeFilter = "all" | SurveillanceCameraConfig["system_mode"];

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

function createDrafts(cameras: SurveillanceCameraConfig[]): Drafts {
  return Object.fromEntries(
    cameras.map((camera) => [
      camera.id,
      {
        location: camera.location,
        system_mode: camera.system_mode,
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

export default function SurveillanceAdminPanel({
  initialCameras = [],
  initialError = null,
}: {
  initialCameras?: SurveillanceCameraConfig[];
  initialError?: string | null;
}) {
  const [cameras, setCameras] = useState<SurveillanceCameraConfig[]>(initialCameras);
  const [drafts, setDrafts] = useState<Drafts>(createDrafts(initialCameras));
  const [searchQuery, setSearchQuery] = useState("");
  const [modeFilter, setModeFilter] = useState<ModeFilter>("all");
  const [isLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(initialError);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [savedId, setSavedId] = useState<string | null>(null);
  const [uploadLocation, setUploadLocation] = useState("");
  const [uploadMode, setUploadMode] = useState<SurveillanceCameraConfig["system_mode"]>("enforcement_mode");
  const [selectedUploadFile, setSelectedUploadFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const deferredSearchQuery = useDeferredValue(searchQuery);

  const refreshCameras = async () => {
    try {
      setIsRefreshing(true);
      setError(null);
      const data = await getCameraConfigs();
      setCameras(data);
      setDrafts(createDrafts(data));
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Failed to load surveillance configuration",
      );
    } finally {
      setIsRefreshing(false);
    }
  };

  const visibleCameras = useMemo(() => {
    const query = deferredSearchQuery.trim().toLowerCase();

    return cameras.filter((camera) => {
      const draft = drafts[camera.id] ?? {
        location: camera.location,
        system_mode: camera.system_mode,
      };
      const matchesMode =
        modeFilter === "all" || draft.system_mode === modeFilter;
      const haystack = [
        camera.id,
        draft.location,
        camera.file_name,
        camera.address,
      ]
        .join(" ")
        .toLowerCase();
      const matchesSearch = !query || haystack.includes(query);

      return matchesMode && matchesSearch;
    });
  }, [cameras, deferredSearchQuery, drafts, modeFilter]);

  const dirtyCount = useMemo(
    () =>
      cameras.reduce((count, camera) => {
        const draft = drafts[camera.id];
        if (!draft) {
          return count;
        }
        return draft.location !== camera.location ||
          draft.system_mode !== camera.system_mode
          ? count + 1
          : count;
      }, 0),
    [cameras, drafts],
  );

  const enforcementCount = useMemo(
    () =>
      cameras.filter((camera) => camera.system_mode === "enforcement_mode")
        .length,
    [cameras],
  );

  const trafficCount = useMemo(
    () =>
      cameras.filter(
        (camera) => camera.system_mode === "traffic_management_mode",
      ).length,
    [cameras],
  );

  const handleDraftChange = (
    cameraId: string,
    field: keyof CameraDraft,
    value: string,
  ) => {
    setSavedId((current) => (current === cameraId ? null : current));
    setDrafts((current) => ({
      ...current,
      [cameraId]: {
        ...(current[cameraId] ?? { location: "", system_mode: "enforcement_mode" }),
        [field]: value,
      } as CameraDraft,
    }));
  };

  const handleReset = (camera: SurveillanceCameraConfig) => {
    setSavedId((current) => (current === camera.id ? null : current));
    setDrafts((current) => ({
      ...current,
      [camera.id]: {
        location: camera.location,
        system_mode: camera.system_mode,
      },
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
      const updated = await updateCameraConfig(cameraId, draft);
      setCameras((current) =>
        current.map((camera) => (camera.id === cameraId ? updated : camera)),
      );
      setDrafts((current) => ({
        ...current,
        [cameraId]: {
          location: updated.location,
          system_mode: updated.system_mode,
        },
      }));
      setSavedId(cameraId);
    } catch (saveError) {
      setError(
        saveError instanceof Error
          ? saveError.message
          : "Failed to save surveillance configuration",
      );
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
      setError(
        uploadError instanceof Error
          ? uploadError.message
          : "Failed to add surveillance feed",
      );
    } finally {
      setIsUploading(false);
    }
  };

  const handleRemove = async (camera: SurveillanceCameraConfig) => {
    const confirmed = window.confirm(
      `Remove ${camera.id.toUpperCase()} from the surveillance registry?`,
    );
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
      setError(
        removeError instanceof Error
          ? removeError.message
          : "Failed to remove surveillance feed",
      );
    } finally {
      setRemovingId(null);
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
              <p className="logo-strip-tagline">
                Surveillance feed control, tuned for the hackathon demo desk
              </p>
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

          <div className="admin-toolbar-actions">
            <button
              type="button"
              className="admin-toolbar-btn admin-toolbar-btn--subtle"
              onClick={() => void refreshCameras()}
              disabled={isRefreshing}
            >
              <RefreshIcon />
              <span>{isRefreshing ? "Refreshing…" : "Refresh feeds"}</span>
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
              Every card below is backed by the Python camera registry. Operators can
              rename the feed and switch its runtime mode without editing server code.
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
                <span className="admin-upload-file">
                  {selectedUploadFile?.name || "No file selected"}
                </span>
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

            <div className="admin-checklist">
              <p className="admin-checklist-title">Operator notes</p>
              <ul className="admin-checklist-list">
                <li>Use enforcement mode for plate, speed, helmet, and challan workflows.</li>
                <li>Use traffic light mode for intersection monitoring and flow management.</li>
                <li>Refresh after adding or renaming surveillance videos on the backend.</li>
              </ul>
            </div>
          </section>
        </aside>

        <div className="dash-main admin-main">
          {error ? (
            <div className="admin-alert admin-alert--error" role="alert">
              {error}
            </div>
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
                const draft = drafts[camera.id] ?? {
                  location: camera.location,
                  system_mode: camera.system_mode,
                };
                const isDirty =
                  draft.location !== camera.location ||
                  draft.system_mode !== camera.system_mode;
                const isSaving = savingId === camera.id;
                const isRemoving = removingId === camera.id;
                const isSaved = savedId === camera.id && !isDirty;

                return (
                  <section key={camera.id} className="admin-feed-card">
                    <div className="admin-feed-preview">
                      <img
                        src={camera.stream_url}
                        alt={`Live surveillance preview for ${camera.location}`}
                        className="admin-feed-image"
                      />
                      <div className="admin-feed-overlay">
                        <span className="admin-feed-status">{camera.status}</span>
                        <span className="admin-feed-mode-chip">
                          {draft.system_mode === "enforcement_mode"
                            ? "Enforcement"
                            : "Traffic light"}
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
                          onChange={(event) =>
                            handleDraftChange(camera.id, "location", event.target.value)
                          }
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
                                onClick={() =>
                                  handleDraftChange(camera.id, "system_mode", option.value)
                                }
                              >
                                <span>{option.label}</span>
                                <small>{option.helper}</small>
                              </button>
                            );
                          })}
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
                          {isDirty ? (
                            <span className="admin-state-pill admin-state-pill--dirty">
                              Pending changes
                            </span>
                          ) : null}
                          {isSaved ? (
                            <span className="admin-state-pill admin-state-pill--saved">
                              Saved
                            </span>
                          ) : null}
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
