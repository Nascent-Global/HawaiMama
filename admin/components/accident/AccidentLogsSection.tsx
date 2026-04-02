"use client";

/* eslint-disable @next/next/no-img-element */

import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { getAccidents, verifyAccident } from "@/lib/api";
import type { AccidentLog } from "@/types/accident";

function isStreamUrl(url: string): boolean {
  return url.includes("/camera/") && url.endsWith("/stream");
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

export default function AccidentLogsSection({ canVerify = false }: { canVerify?: boolean }) {
  const [accidents, setAccidents] = useState<AccidentLog[]>([]);
  const [selected, setSelected] = useState<AccidentLog | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [verifyingId, setVerifyingId] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        setIsLoading(true);
        setError(null);
        const data = await getAccidents();
        setAccidents(data);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Failed to load accidents");
      } finally {
        setIsLoading(false);
      }
    }

    void load();
  }, []);

  const handleVerify = async (id: string) => {
    try {
      setVerifyingId(id);
      const result = await verifyAccident(id);
      setAccidents((prev) => prev.map((item) => (item.id === id ? result.accident : item)));
      setSelected((prev) => (prev && prev.id === id ? result.accident : prev));
    } catch (verifyError) {
      setError(verifyError instanceof Error ? verifyError.message : "Failed to verify accident");
    } finally {
      setVerifyingId(null);
    }
  };

  return (
    <section className="flex h-full min-h-[640px] flex-col overflow-hidden border border-[var(--gov-line)] bg-[var(--gov-paper)]">
      <header className="border-b-4 border-[var(--gov-red)] bg-[var(--gov-paper-alt)] px-4 py-3 sm:px-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--gov-blue)]">
              Incident Register
            </p>
            <h1 className="mt-1 text-xl font-bold text-[var(--gov-ink)] [font-family:var(--font-heading)]">
              Accident Logs
            </h1>
          </div>
          <div className="inline-flex items-center gap-2 border border-[var(--gov-line)] bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)]">
            <span>{accidents.length}</span>
            <span>Cases</span>
          </div>
        </div>
      </header>

      {error ? (
        <div className="border-b border-[var(--gov-red)] bg-[rgba(193,39,45,0.08)] px-4 py-2 text-sm text-[var(--gov-red-dark)]">
          {error}
        </div>
      ) : null}

      <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.95fr)]">
        <div className="gov-scrollbar min-h-0 overflow-auto border-r border-[var(--gov-line)]">
          <div className="hidden grid-cols-[160px_minmax(0,1fr)_110px_120px] border-b border-[var(--gov-line-strong)] bg-[var(--gov-highlight)] px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--gov-muted)] md:grid">
            <span>Vehicle</span>
            <span>Incident Summary</span>
            <span>Status</span>
            <span>Time</span>
          </div>

          {isLoading ? <div className="px-4 py-8 text-sm text-[var(--gov-muted)]">Loading accident records...</div> : null}
          {!isLoading && accidents.length === 0 ? (
            <div className="px-4 py-8 text-sm text-[var(--gov-muted)]">No accident records available.</div>
          ) : null}

          <div className="divide-y divide-[var(--gov-line)]">
            {accidents.map((accident) => {
              const stamp = formatTimestamp(accident.timestamp);
              const isSelected = selected?.id === accident.id;
              return (
                <button
                  key={accident.id}
                  type="button"
                  onClick={() => setSelected(accident)}
                  className={`grid w-full gap-3 px-4 py-3 text-left transition hover:bg-[var(--gov-highlight)] md:grid-cols-[160px_minmax(0,1fr)_110px_120px] ${
                    isSelected ? "bg-[var(--gov-highlight)]" : "bg-white"
                  }`}
                >
                  <div>
                    <div className="inline-flex border border-[var(--gov-red)] bg-[rgba(193,39,45,0.1)] px-2 py-1 font-mono text-xs font-bold tracking-[0.2em] text-[var(--gov-red-dark)]">
                      {accident.licensePlate}
                    </div>
                  </div>
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-[var(--gov-ink)]">{accident.driverName}</div>
                    <div className="mt-1 truncate text-sm text-[var(--gov-muted)]">{accident.title}</div>
                    <div className="mt-1 truncate text-xs text-[var(--gov-muted)]">{accident.tempAddress}</div>
                  </div>
                  <div className="flex items-start">
                    <span
                      className={`inline-flex border px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.15em] ${
                        accident.verified
                          ? "border-emerald-700 bg-emerald-50 text-emerald-800"
                          : "border-[var(--gov-blue)] bg-[rgba(0,56,147,0.08)] text-[var(--gov-blue)]"
                      }`}
                    >
                      {accident.verified ? "Reported" : "Pending"}
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
                    Case Assessment
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

              <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_260px]">
                <div className="space-y-4">
                  <div className="grid gap-2 sm:grid-cols-3">
                    <img src={selected.screenshot1Url} alt="Accident evidence 1" className="h-28 w-full border border-[var(--gov-line)] object-cover" />
                    <img src={selected.screenshot2Url} alt="Accident evidence 2" className="h-28 w-full border border-[var(--gov-line)] object-cover" />
                    <img src={selected.screenshot3Url} alt="Accident evidence 3" className="h-28 w-full border border-[var(--gov-line)] object-cover" />
                  </div>

                  <div className="border border-[var(--gov-line)] bg-black">
                    {isStreamUrl(selected.videoUrl) ? (
                      <img src={selected.videoUrl} alt={selected.title} className="w-full" />
                    ) : (
                      <video controls className="w-full">
                        <source src={selected.videoUrl} type="video/mp4" />
                      </video>
                    )}
                  </div>

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
                        {verifyingId === selected.id ? "Verifying..." : "Verify and Issue Report"}
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
                    Driver and Incident Data
                  </div>
                  <div className="mt-2">
                    <MetaItem label="Driver" value={selected.driverName} />
                    <MetaItem label="Date of Birth" value={new Date(selected.dob).toLocaleDateString()} />
                    <MetaItem label="Blood Group" value={selected.bloodGroup} />
                    <MetaItem label="Age" value={selected.age} />
                    <MetaItem label="Temporary Address" value={selected.tempAddress} />
                    <MetaItem label="Permanent Address" value={selected.permAddress} />
                  </div>
                </aside>
              </div>
            </div>
          ) : (
            <div className="px-4 py-8 sm:px-5">
              <div className="border border-dashed border-[var(--gov-line-strong)] bg-white px-4 py-6 text-sm text-[var(--gov-muted)]">
                Select an accident record from the register to inspect the evidence and report status.
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
