"use client";

/* eslint-disable @next/next/no-img-element */

import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";
import { useDeferredValue, useEffect, useMemo, useState } from "react";
import AccidentLogsSection from "@/components/accident/AccidentLogsSection";
import ChallanLogsSection from "@/components/challan/ChallanLogsSection";
import ViolationLogsSection from "@/components/violation/ViolationLogsSection";
import { getSurveillanceFeeds } from "@/lib/api";
import { canAccessPermission, useAdminSession } from "@/lib/auth";
import type { SurveillanceFeed } from "@/types/surveillance";

type NavKey = "live" | "violations" | "accidents" | "challan";

const navItems: { key: NavKey; label: string }[] = [
  { key: "live", label: "Live surveillance" },
  { key: "violations", label: "Violation logs" },
  { key: "accidents", label: "Accident logs" },
  { key: "challan", label: "Challan logs" },
];

function SearchIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <circle cx="11" cy="11" r="8" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  );
}

function FeedMedia({
  feed,
  systemEnabled,
  detail = false,
}: {
  feed: SurveillanceFeed;
  systemEnabled: boolean;
  detail?: boolean;
}) {
  const mediaKey = `${feed.id}-${systemEnabled ? "system" : "raw"}-${detail ? "detail" : "grid"}`;

  if (systemEnabled && detail) {
    return <img key={mediaKey} className="h-full w-full object-cover" src={feed.stream_video} alt={`System output at ${feed.address}`} />;
  }

  if (!detail && feed.previewVideoUrl) {
    return (
      <video
        key={mediaKey}
        className="h-full w-full object-cover"
        src={feed.previewVideoUrl}
        autoPlay
        muted
        loop
        playsInline
        preload="metadata"
      />
    );
  }

  if (feed.videoUrl) {
    return (
      <video
        key={mediaKey}
        className="h-full w-full object-cover"
        src={feed.videoUrl}
        autoPlay
        muted
        loop
        playsInline
        preload="metadata"
        controls={detail}
      />
    );
  }

  return <div className="flex h-full items-center justify-center bg-slate-900 text-sm text-white/70">Video unavailable</div>;
}

function DashboardShell({
  title,
  subtitle,
  children,
  rightSlot,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  rightSlot?: ReactNode;
}) {
  return (
    <div className="grid min-h-[calc(100dvh-32px)] grid-rows-[auto_1fr] overflow-hidden border border-[var(--gov-line-strong)] bg-[var(--gov-paper)] shadow-[0_20px_45px_rgba(18,35,61,0.08)]">
      <header className="border-b border-[var(--gov-line-strong)] bg-[var(--gov-paper-alt)]">
        <div className="h-2 w-full bg-[linear-gradient(90deg,#c1272d_0%,#c1272d_20%,#003893_20%,#003893_100%)]" />
        <div className="flex flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-5">
          <div className="flex items-center gap-4">
            <div className="flex h-14 w-14 items-center justify-center border border-[var(--gov-line)] bg-white p-2">
              <Image src="/logo.png" alt="Hawai Mama" width={44} height={44} className="h-auto w-auto max-h-10 max-w-10 object-contain" priority />
            </div>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--gov-red)]">Traffic Operations System</p>
              <h1 className="mt-1 text-xl font-bold text-[var(--gov-ink)] [font-family:var(--font-heading)]">{title}</h1>
              <p className="mt-1 text-sm text-[var(--gov-muted)]">{subtitle}</p>
            </div>
          </div>
          {rightSlot}
        </div>
      </header>
      {children}
    </div>
  );
}

function SessionBlock({
  name,
  role,
  onLogout,
}: {
  name: string;
  role: string;
  onLogout: () => void;
}) {
  return (
    <div className="flex items-center gap-3 border border-[var(--gov-line)] bg-white px-3 py-2">
      <div className="text-right">
        <div className="text-sm font-semibold text-[var(--gov-ink)]">{name}</div>
        <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--gov-muted)]">{role}</div>
      </div>
      <button
        type="button"
        className="border border-[var(--gov-line-strong)] px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)] hover:border-[var(--gov-red)] hover:text-[var(--gov-red-dark)]"
        onClick={onLogout}
      >
        Logout
      </button>
    </div>
  );
}

function FeedRegistry({
  feeds,
  selectedId,
  onSelect,
  systemEnabled,
}: {
  feeds: SurveillanceFeed[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  systemEnabled: boolean;
}) {
  return (
    <div className="gov-scrollbar min-h-0 overflow-auto border border-[var(--gov-line)] bg-white">
      <div className="hidden grid-cols-[180px_minmax(0,1fr)_140px_110px] border-b border-[var(--gov-line-strong)] bg-[var(--gov-highlight)] px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--gov-muted)] md:grid">
        <span>Camera</span>
        <span>Location</span>
        <span>Mode</span>
        <span>Status</span>
      </div>
      <div className="divide-y divide-[var(--gov-line)]">
        {feeds.map((feed) => {
          const isSelected = selectedId === feed.id;
          return (
            <button
              key={feed.id}
              type="button"
              className={`grid w-full gap-3 px-4 py-3 text-left transition hover:bg-[var(--gov-highlight)] md:grid-cols-[180px_minmax(0,1fr)_140px_110px] ${
                isSelected ? "bg-[var(--gov-highlight)]" : "bg-white"
              }`}
              onClick={() => onSelect(feed.id)}
            >
              <div className="min-w-0">
                <div className="text-sm font-semibold uppercase tracking-[0.14em] text-[var(--gov-blue)]">{feed.id}</div>
                <div className="mt-1 truncate text-xs text-[var(--gov-muted)]">{feed.address}</div>
              </div>
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-[var(--gov-ink)]">{feed.location}</div>
                <div className="mt-1 truncate text-xs text-[var(--gov-muted)]">{feed.locationLink || "Map link not configured"}</div>
              </div>
              <div className="text-xs font-semibold uppercase tracking-[0.15em] text-[var(--gov-muted)]">
                {systemEnabled ? "Processed" : "Raw stream"}
              </div>
              <div>
                <span className="inline-flex items-center gap-2 border border-[var(--gov-red)] bg-[rgba(193,39,45,0.08)] px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.15em] text-[var(--gov-red-dark)]">
                  <span className="h-2 w-2 rounded-full bg-[var(--gov-red)]" />
                  Live
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function FeedDetail({
  feed,
  systemEnabled,
}: {
  feed: SurveillanceFeed;
  systemEnabled: boolean;
}) {
  return (
    <section className="grid min-h-0 gap-4 lg:grid-cols-[minmax(0,1fr)_260px]">
      <div className="min-h-0 overflow-hidden border border-[var(--gov-line)] bg-white">
        <div className="flex items-center justify-between border-b border-[var(--gov-line)] bg-[var(--gov-paper-alt)] px-4 py-3">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--gov-red)]">Live Feed Viewer</div>
            <div className="mt-1 text-sm font-semibold text-[var(--gov-ink)]">{feed.address}</div>
          </div>
          <span className="border border-[var(--gov-blue)] bg-[rgba(0,56,147,0.08)] px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.15em] text-[var(--gov-blue)]">
            {systemEnabled ? "System output" : "Raw footage"}
          </span>
        </div>
        <div className="aspect-video bg-black">
          <FeedMedia feed={feed} systemEnabled={systemEnabled} detail />
        </div>
      </div>

      <aside className="border border-[var(--gov-line)] bg-[var(--gov-paper-alt)] px-4 py-4">
        <div className="border-b border-[var(--gov-line)] pb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--gov-blue)]">
          Feed Metadata
        </div>
        <dl className="mt-3 space-y-3 text-sm">
          <div>
            <dt className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)]">Location</dt>
            <dd className="mt-1 text-[var(--gov-ink)]">{feed.location}</dd>
          </div>
          <div>
            <dt className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)]">Address</dt>
            <dd className="mt-1 text-[var(--gov-ink)]">{feed.address}</dd>
          </div>
          <div>
            <dt className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)]">Map</dt>
            <dd className="mt-1">
              {feed.locationLink ? (
                <a href={feed.locationLink} target="_blank" rel="noopener noreferrer" className="text-[var(--gov-blue)] underline underline-offset-4">
                  Open location
                </a>
              ) : (
                <span className="text-[var(--gov-muted)]">Not configured</span>
              )}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)]">Source clip</dt>
            <dd className="mt-1">
              {feed.videoUrl ? (
                <a href={feed.videoUrl} target="_blank" rel="noopener noreferrer" className="text-[var(--gov-blue)] underline underline-offset-4">
                  Open source video
                </a>
              ) : (
                <span className="text-[var(--gov-muted)]">Unavailable</span>
              )}
            </dd>
          </div>
        </dl>
      </aside>
    </section>
  );
}

export default function LiveSurveillanceDashboard() {
  const { admin, logout } = useAdminSession();
  const [nav, setNav] = useState<NavKey>("live");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [feeds, setFeeds] = useState<SurveillanceFeed[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [systemEnabled, setSystemEnabled] = useState(false);
  const [isLoadingFeeds, setIsLoadingFeeds] = useState(true);
  const [feedError, setFeedError] = useState<string | null>(null);
  const deferredSearchQuery = useDeferredValue(searchQuery);

  const canViewLive = canAccessPermission(admin, "can_view_live");
  const canManageFeeds = canAccessPermission(admin, "can_manage_feeds");
  const canViewViolations = canAccessPermission(admin, "can_view_violations");
  const canVerifyViolations = canAccessPermission(admin, "can_verify_violations");
  const canViewAccidents = canAccessPermission(admin, "can_view_accidents");
  const canVerifyAccidents = canAccessPermission(admin, "can_verify_accidents");
  const canViewChallans = canAccessPermission(admin, "can_view_challans");

  const visibleNavItems = useMemo(
    () =>
      navItems.filter((item) => {
        if (item.key === "live") return canViewLive;
        if (item.key === "violations") return canViewViolations;
        if (item.key === "accidents") return canViewAccidents;
        if (item.key === "challan") return canViewChallans;
        return false;
      }),
    [canViewAccidents, canViewChallans, canViewLive, canViewViolations],
  );

  const activeNav = useMemo<NavKey | null>(() => {
    if (visibleNavItems.length === 0) return null;
    return visibleNavItems.some((item) => item.key === nav) ? nav : visibleNavItems[0].key;
  }, [nav, visibleNavItems]);

  useEffect(() => {
    if (!admin || !canViewLive) return;
    let active = true;

    void getSurveillanceFeeds()
      .then((data) => {
        if (active) {
          setFeeds(data);
          setFeedError(null);
        }
      })
      .catch((error) => {
        if (active) {
          setFeedError(error instanceof Error ? error.message : "Failed to load surveillance feeds");
        }
      })
      .finally(() => {
        if (active) {
          setIsLoadingFeeds(false);
        }
      });

    return () => {
      active = false;
    };
  }, [admin, canViewLive]);

  const filteredFeeds = useMemo(() => {
    const query = deferredSearchQuery.trim().toLowerCase();
    if (!query) return feeds;
    return feeds.filter((feed) => [feed.address, feed.location, feed.id].some((value) => value.toLowerCase().includes(query)));
  }, [deferredSearchQuery, feeds]);

  const selected = useMemo(() => feeds.find((item) => item.id === selectedId) ?? null, [feeds, selectedId]);

  return (
    <DashboardShell
      title="Administrative Dashboard"
      subtitle="Control room register for live surveillance, violations, accidents, and challan processing."
      rightSlot={
        <div className="flex flex-wrap items-center justify-end gap-3">
          {admin ? (
            <SessionBlock
              name={admin.full_name}
              role={admin.role === "superadmin" ? "Superadmin" : "Admin"}
              onLogout={() => void logout()}
            />
          ) : null}
          {canManageFeeds ? (
            <Link
              href="/admin"
              className="border border-[var(--gov-blue)] bg-[var(--gov-blue)] px-3 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-white hover:bg-[var(--gov-blue-dark)]"
            >
              Feed Admin
            </Link>
          ) : null}
        </div>
      }
    >
      <div className="grid min-h-0 lg:grid-cols-[250px_minmax(0,1fr)]">
        <aside className="border-r border-[var(--gov-line-strong)] bg-[var(--gov-paper-alt)]">
          <div className="border-b border-[var(--gov-line)] px-4 py-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--gov-red)]">Navigation</div>
            <nav className="mt-3 space-y-1">
              {visibleNavItems.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className={`w-full border px-3 py-3 text-left text-sm font-semibold uppercase tracking-[0.1em] transition ${
                    activeNav === item.key
                      ? "border-[var(--gov-blue)] bg-white text-[var(--gov-blue)]"
                      : "border-transparent text-[var(--gov-muted)] hover:border-[var(--gov-line)] hover:bg-white"
                  }`}
                  onClick={() => {
                    setNav(item.key);
                    setSelectedId(null);
                  }}
                >
                  {item.label}
                </button>
              ))}
            </nav>
          </div>

          <div className="border-b border-[var(--gov-line)] px-4 py-4">
            <label className="block">
              <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--gov-muted)]">Search Register</span>
              <span className="relative mt-2 flex items-center">
                <input
                  type="search"
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  placeholder="Feeds, wards, plates..."
                  className="w-full border border-[var(--gov-line-strong)] bg-white py-2 pl-3 pr-10 text-sm text-[var(--gov-ink)] outline-none placeholder:text-[var(--gov-muted)] focus:border-[var(--gov-blue)]"
                />
                <span className="pointer-events-none absolute right-3 text-[var(--gov-muted)]">
                  <SearchIcon />
                </span>
              </span>
            </label>
          </div>

          <div className="px-4 py-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--gov-muted)]">Output Mode</div>
            <div className="mt-3 grid gap-2">
              <button
                type="button"
                onClick={() => setSystemEnabled(false)}
                className={`border px-3 py-3 text-left text-sm font-semibold uppercase tracking-[0.1em] ${
                  !systemEnabled ? "border-[var(--gov-red)] bg-white text-[var(--gov-red-dark)]" : "border-[var(--gov-line)] text-[var(--gov-muted)]"
                }`}
              >
                Raw surveillance feed
              </button>
              <button
                type="button"
                onClick={() => setSystemEnabled(true)}
                className={`border px-3 py-3 text-left text-sm font-semibold uppercase tracking-[0.1em] ${
                  systemEnabled ? "border-[var(--gov-blue)] bg-white text-[var(--gov-blue)]" : "border-[var(--gov-line)] text-[var(--gov-muted)]"
                }`}
              >
                Processed system output
              </button>
            </div>
          </div>
        </aside>

        <main className="gov-scrollbar min-h-0 overflow-auto bg-[var(--gov-paper)] px-4 py-4 sm:px-5">
          {visibleNavItems.length === 0 ? (
            <div className="border border-dashed border-[var(--gov-line-strong)] bg-[var(--gov-paper-alt)] px-4 py-8 text-sm text-[var(--gov-muted)]">
              No sections have been assigned to this account yet.
            </div>
          ) : null}

          {activeNav === "violations" && canViewViolations ? <ViolationLogsSection canVerify={canVerifyViolations} /> : null}
          {activeNav === "accidents" && canViewAccidents ? <AccidentLogsSection canVerify={canVerifyAccidents} /> : null}
          {activeNav === "challan" && canViewChallans ? <ChallanLogsSection /> : null}

          {activeNav === "live" && canViewLive ? (
            <div className="space-y-4">
              <div className="grid gap-3 md:grid-cols-3">
                <div className="border border-[var(--gov-line)] bg-[var(--gov-paper-alt)] px-4 py-3">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--gov-muted)]">Active feeds</div>
                  <div className="mt-2 text-2xl font-bold text-[var(--gov-ink)]">{feeds.length}</div>
                </div>
                <div className="border border-[var(--gov-line)] bg-[var(--gov-paper-alt)] px-4 py-3">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--gov-muted)]">Filtered results</div>
                  <div className="mt-2 text-2xl font-bold text-[var(--gov-ink)]">{filteredFeeds.length}</div>
                </div>
                <div className="border border-[var(--gov-line)] bg-[var(--gov-paper-alt)] px-4 py-3">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--gov-muted)]">View mode</div>
                  <div className="mt-2 text-lg font-bold text-[var(--gov-ink)]">{systemEnabled ? "Processed system" : "Raw stream"}</div>
                </div>
              </div>

              {isLoadingFeeds ? (
                <div className="border border-dashed border-[var(--gov-line-strong)] bg-[var(--gov-paper-alt)] px-4 py-8 text-sm text-[var(--gov-muted)]">
                  Connecting to the surveillance stream server...
                </div>
              ) : null}

              {feedError ? (
                <div className="border border-[var(--gov-red)] bg-[rgba(193,39,45,0.08)] px-4 py-3 text-sm text-[var(--gov-red-dark)]">
                  {feedError}
                </div>
              ) : null}

              {!isLoadingFeeds && !feedError ? (
                <div className="grid gap-4 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.1fr)]">
                  <FeedRegistry
                    feeds={filteredFeeds}
                    selectedId={selectedId}
                    onSelect={setSelectedId}
                    systemEnabled={systemEnabled}
                  />
                  {selected ? (
                    <FeedDetail feed={selected} systemEnabled={systemEnabled} />
                  ) : (
                    <div className="border border-dashed border-[var(--gov-line-strong)] bg-[var(--gov-paper-alt)] px-4 py-8 text-sm text-[var(--gov-muted)]">
                      Select a feed from the registry to open the live viewer and metadata panel.
                    </div>
                  )}
                </div>
              ) : null}
            </div>
          ) : null}
        </main>
      </div>
    </DashboardShell>
  );
}
