"use client";

/* eslint-disable @next/next/no-img-element */

import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { getViolations, verifyViolation } from "@/lib/api";
import type { ViolationLog } from "@/types/violation";

function isStreamUrl(url: string): boolean {
  return url.includes("/camera/") && url.endsWith("/stream");
}

function evidenceVideoLabel(violation: ViolationLog): string {
  if (!violation.videoUrl) {
    return "";
  }
  if (violation.evidenceClipUrl && violation.videoUrl === violation.evidenceClipUrl) {
    return "Evidence clip";
  }
  if (isStreamUrl(violation.videoUrl)) {
    return "Processed live stream";
  }
  return "Source clip";
}

function formatTimestamp(value: string) {
  const date = new Date(value);
  return {
    time: date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    date: date.toLocaleDateString("en-NP", { day: "numeric", month: "short", year: "numeric" }),
  };
}

function MetaItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="border-b border-[var(--gov-line)] py-2 last:border-b-0">
      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--gov-muted)]">{label}</div>
      <div className="mt-1 text-sm text-[var(--gov-ink)]">{value}</div>
    </div>
  );
}

export default function ViolationLogsSection({ canVerify = false }: { canVerify?: boolean }) {
  const [violations, setViolations] = useState<ViolationLog[]>([]);
  const [selected, setSelected] = useState<ViolationLog | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [verifyingId, setVerifyingId] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        setIsLoading(true);
        setError(null);
        const data = await getViolations();
        setViolations(data);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Failed to load violations");
      } finally {
        setIsLoading(false);
      }
    }

    void load();
  }, []);

  const selectedScreenshots = useMemo(
    () =>
      selected
        ? [selected.screenshot1Url, selected.screenshot2Url, selected.screenshot3Url].filter(Boolean)
        : [],
    [selected],
  );

  const handleVerify = async (id: string) => {
    try {
      setVerifyingId(id);
      const result = await verifyViolation(id);
      setViolations((prev) => prev.map((item) => (item.id === id ? result.violation : item)));
      setSelected((prev) => (prev && prev.id === id ? result.violation : prev));
    } catch (verifyError) {
      setError(verifyError instanceof Error ? verifyError.message : "Failed to verify violation");
    } finally {
      setVerifyingId(null);
    }
  };

  return (
    <section className="flex h-full min-h-[640px] flex-col overflow-hidden border border-[var(--gov-line)] bg-[var(--gov-paper)]">
      <header className="border-b-4 border-[var(--gov-blue)] bg-[var(--gov-paper-alt)] px-4 py-3 sm:px-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--gov-red)]">
              Enforcement Register
            </p>
            <h1 className="mt-1 text-xl font-bold text-[var(--gov-ink)] [font-family:var(--font-heading)]">
              Violation Logs
            </h1>
          </div>
          <div className="inline-flex items-center gap-2 border border-[var(--gov-line)] bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)]">
            <span>{violations.length}</span>
            <span>Records</span>
          </div>
        </div>
      </header>

      {error ? (
        <div className="border-b border-[var(--gov-red)] bg-[rgba(193,39,45,0.08)] px-4 py-2 text-sm text-[var(--gov-red-dark)]">
          {error}
        </div>
      ) : null}

      <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(0,1.2fr)_minmax(360px,0.9fr)]">
        <div className="gov-scrollbar min-h-0 overflow-auto border-r border-[var(--gov-line)]">
          <div className="hidden grid-cols-[120px_minmax(0,1fr)_130px_120px] border-b border-[var(--gov-line-strong)] bg-[var(--gov-highlight)] px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--gov-muted)] md:grid">
            <span>Plate</span>
            <span>Case Summary</span>
            <span>Status</span>
            <span>Time</span>
          </div>

          {isLoading ? (
            <div className="px-4 py-8 text-sm text-[var(--gov-muted)]">Loading violation records...</div>
          ) : null}

          {!isLoading && violations.length === 0 ? (
            <div className="px-4 py-8 text-sm text-[var(--gov-muted)]">No violation records available.</div>
          ) : null}

          <div className="divide-y divide-[var(--gov-line)]">
            {violations.map((violation) => {
              const stamp = formatTimestamp(violation.timestamp);
              const isSelected = selected?.id === violation.id;
              return (
                <button
                  key={violation.id}
                  type="button"
                  onClick={() => setSelected(violation)}
                  className={`grid w-full gap-3 px-4 py-3 text-left transition hover:bg-[var(--gov-highlight)] md:grid-cols-[120px_minmax(0,1fr)_130px_120px] ${
                    isSelected ? "bg-[var(--gov-highlight)]" : "bg-white"
                  }`}
                >
                  <div>
                    <div className="inline-flex border border-[var(--gov-red)] bg-[rgba(193,39,45,0.1)] px-2 py-1 font-mono text-xs font-bold tracking-[0.2em] text-[var(--gov-red-dark)]">
                      {violation.licensePlate}
                    </div>
                  </div>
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-[var(--gov-ink)]">
                      {violation.ownerName || violation.driverName}
                    </div>
                    <div className="mt-1 truncate text-sm text-[var(--gov-muted)]">{violation.title}</div>
                    <div className="mt-1 truncate text-xs text-[var(--gov-muted)]">
                      {violation.cameraId?.toUpperCase() || "CAM"} | {violation.cameraLocation || violation.tempAddress}
                    </div>
                  </div>
                  <div className="flex items-start">
                    <span
                      className={`inline-flex border px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.15em] ${
                        violation.verified
                          ? "border-emerald-700 bg-emerald-50 text-emerald-800"
                          : "border-[var(--gov-blue)] bg-[rgba(0,56,147,0.08)] text-[var(--gov-blue)]"
                      }`}
                    >
                      {violation.verified ? "Verified" : "Pending"}
                    </span>
                  </div>
                  <div className="text-xs text-[var(--gov-muted)]">
                    <div>{stamp.time}</div>
                    <div className="mt-1">{stamp.date}</div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <div className="gov-scrollbar min-h-0 overflow-auto bg-[var(--gov-paper-alt)]">
          {selected ? (
            <div className="px-4 py-4 sm:px-5">
              <div className="flex items-start justify-between gap-3 border-b border-[var(--gov-line-strong)] pb-3">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--gov-red)]">
                    Case File
                  </p>
                  <h2 className="mt-1 text-lg font-bold text-[var(--gov-ink)] [font-family:var(--font-heading)]">
                    {selected.title}
                  </h2>
                  <div className="mt-2 inline-flex border border-[var(--gov-red)] bg-[rgba(193,39,45,0.1)] px-2 py-1 font-mono text-xs font-bold tracking-[0.22em] text-[var(--gov-red-dark)]">
                    {selected.licensePlate}
                  </div>
                </div>
                <button
                  type="button"
                  className="border border-[var(--gov-line-strong)] bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)] hover:border-[var(--gov-blue)] hover:text-[var(--gov-blue)]"
                  onClick={() => setSelected(null)}
                >
                  Close
                </button>
              </div>

              {selected.isMockData ? (
                <div className="mt-4 border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                  Demo data only. This record is not from a live DoTM system.
                </div>
              ) : null}

              <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_260px]">
                <div className="space-y-4">
                  {selectedScreenshots.length > 0 ? (
                    <div className={`grid gap-2 ${selectedScreenshots.length === 1 ? "grid-cols-1" : "grid-cols-3"}`}>
                      {selectedScreenshots.map((screenshot, index) => (
                        <img
                          key={screenshot}
                          src={screenshot}
                          alt={`Evidence screenshot ${index + 1}`}
                          className="h-28 w-full border border-[var(--gov-line)] object-cover"
                        />
                      ))}
                    </div>
                  ) : null}

                  {selected.videoUrl ? (
                    <div className="border border-[var(--gov-line)] bg-black">
                      <div className="flex items-center justify-between border-b border-[rgba(255,255,255,0.16)] px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-white/80">
                        <span>{evidenceVideoLabel(selected) || "Evidence"}</span>
                        {selected.sourceVideoUrl && selected.videoUrl !== selected.sourceVideoUrl ? (
                          <a
                            href={selected.sourceVideoUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-white underline underline-offset-4"
                          >
                            Open source clip
                          </a>
                        ) : null}
                      </div>
                      {isStreamUrl(selected.videoUrl) ? (
                        <img src={selected.videoUrl} alt={selected.title} className="w-full" />
                      ) : (
                        <video controls className="w-full">
                          <source src={selected.videoUrl} type="video/mp4" />
                        </video>
                      )}
                    </div>
                  ) : null}

                  <div className="border border-[var(--gov-line)] bg-white px-4 py-3 text-sm leading-6 text-[var(--gov-ink)]">
                    {selected.description}
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {selected.locationLink ? (
                      <a
                        href={selected.locationLink}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="border border-[var(--gov-blue)] px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--gov-blue)] hover:bg-[rgba(0,56,147,0.06)]"
                      >
                        Open map
                      </a>
                    ) : null}
                    {!selected.verified && canVerify ? (
                      <button
                        type="button"
                        className="bg-[var(--gov-blue)] px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-white hover:bg-[var(--gov-blue-dark)] disabled:opacity-60"
                        disabled={verifyingId === selected.id}
                        onClick={() => void handleVerify(selected.id)}
                      >
                        {verifyingId === selected.id ? "Verifying..." : "Verify and Generate Challan"}
                      </button>
                    ) : null}
                    {!selected.verified && !canVerify ? (
                      <span className="border border-[var(--gov-line-strong)] bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)]">
                        Read only
                      </span>
                    ) : null}
                    {selected.verified ? (
                      <span className="border border-emerald-700 bg-emerald-50 px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-emerald-800">
                        Verified
                      </span>
                    ) : null}
                  </div>
                </div>

                <aside className="border border-[var(--gov-line)] bg-white px-4 py-3">
                  <div className="border-b border-[var(--gov-line)] pb-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--gov-blue)]">
                    Registry Metadata
                  </div>
                  <div className="mt-2">
                    <MetaItem label="Owner" value={selected.ownerName || selected.driverName} />
                    <MetaItem label="Camera" value={selected.cameraId?.toUpperCase() || "Unknown feed"} />
                    <MetaItem
                      label="Location"
                      value={
                        selected.cameraLocationLink ? (
                          <a
                            href={selected.cameraLocationLink}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-[var(--gov-blue)] underline underline-offset-4"
                          >
                            {selected.cameraLocation || selected.tempAddress}
                          </a>
                        ) : (
                          selected.cameraLocation || selected.tempAddress
                        )
                      }
                    />
                    <MetaItem label="Owner Address" value={selected.ownerAddress || selected.tempAddress} />
                    <MetaItem label="Vehicle Color" value={selected.vehicleColor || "Unknown"} />
                    <MetaItem label="Registration Date" value={selected.registrationDate || "Unknown"} />
                    <MetaItem label="Evidence Source" value={selected.evidenceProvider || "local"} />
                    <MetaItem label="Playback" value={evidenceVideoLabel(selected) || "Unavailable"} />
                  </div>
                </aside>
              </div>
            </div>
          ) : (
            <div className="px-4 py-8 sm:px-5">
              <div className="border border-dashed border-[var(--gov-line-strong)] bg-white px-4 py-6 text-sm text-[var(--gov-muted)]">
                Select a violation record from the register to inspect evidence, location, and verification status.
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
