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

import DashboardMap from "@/components/map/DashboardMap";

type NavKey = "overview" | "live" | "violations" | "accidents" | "challan";

const navItems: { key: NavKey; label: string }[] = [
  { key: "overview", label: "Map Overview" },
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

  if (!detail && systemEnabled && feed.processedVideoUrl) {
    return (
      <video
        key={mediaKey}
        className="h-full w-full object-cover"
        src={feed.processedVideoUrl}
        autoPlay
        muted
        loop
        playsInline
        preload="metadata"
      />
    );
  }

  if (!detail && systemEnabled) {
    return (
      <div className="flex h-full items-center justify-center bg-slate-900 px-6 text-center text-sm text-white/70">
        Processed output unavailable for this feed.
      </div>
    );
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

function FeedTile({
  feed,
  systemEnabled,
  onOpen,
}: {
  feed: SurveillanceFeed;
  systemEnabled: boolean;
  onOpen: (feedId: string) => void;
}) {
  return (
    <article className="overflow-hidden border border-[var(--gov-line)] bg-white shadow-[0_10px_28px_rgba(18,35,61,0.08)] transition hover:-translate-y-0.5 hover:shadow-[0_14px_34px_rgba(18,35,61,0.12)]">
      <div className="flex items-center justify-between border-b border-[var(--gov-line)] bg-[var(--gov-paper-alt)] px-4 py-3">
        <div className="min-w-0">
          <div className="truncate text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--gov-red)]">
            {systemEnabled ? "Processed system output" : "Raw surveillance feed"}
          </div>
          <div className="mt-1 truncate text-base font-bold uppercase tracking-[0.1em] text-[var(--gov-ink)]">{feed.id}</div>
        </div>
        <span className="inline-flex items-center gap-2 border border-[var(--gov-red)] bg-[rgba(193,39,45,0.08)] px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.15em] text-[var(--gov-red-dark)]">
          <span className="h-2 w-2 rounded-full bg-[var(--gov-red)]" />
          Live
        </span>
      </div>

      <button
        type="button"
        onClick={() => onOpen(feed.id)}
        className="block aspect-video w-full bg-black text-left"
      >
        <FeedMedia feed={feed} systemEnabled={systemEnabled} />
      </button>

      <div className="grid gap-3 border-t border-[var(--gov-line)] px-4 py-4 sm:grid-cols-[minmax(0,1fr)_auto]">
        <div className="min-w-0 space-y-2">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)]">Location</div>
            <div className="mt-1 truncate text-sm font-semibold text-[var(--gov-ink)]">{feed.location}</div>
          </div>
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)]">Address</div>
            <div className="mt-1 truncate text-sm text-[var(--gov-muted)]">{feed.address}</div>
          </div>
        </div>

        <div className="flex flex-wrap items-start gap-2 sm:justify-end">
          <button
            type="button"
            onClick={() => onOpen(feed.id)}
            className="border border-[var(--gov-blue)] bg-[var(--gov-blue)] px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-white hover:bg-[var(--gov-blue-dark)]"
          >
            Open Monitor
          </button>
          {feed.videoUrl ? (
            <a
              href={feed.videoUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="border border-[var(--gov-line-strong)] px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--gov-blue)] hover:border-[var(--gov-blue)]"
            >
              Source
            </a>
          ) : null}
          {feed.locationLink ? (
            <a
              href={feed.locationLink}
              target="_blank"
              rel="noopener noreferrer"
              className="border border-[var(--gov-line-strong)] px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--gov-blue)] hover:border-[var(--gov-blue)]"
            >
              Map
            </a>
          ) : null}
        </div>
      </div>
    </article>
  );
}

function FeedMonitor({
  feed,
  systemEnabled,
  onClose,
}: {
  feed: SurveillanceFeed;
  systemEnabled: boolean;
  onClose: () => void;
}) {
  return (
    <section className="overflow-hidden border border-[var(--gov-line-strong)] bg-white shadow-[0_16px_34px_rgba(18,35,61,0.12)]">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--gov-line)] bg-[var(--gov-paper-alt)] px-4 py-4 sm:px-5">
        <div className="min-w-0">
          <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--gov-red)]">
            Focus Monitor
          </div>
          <h2 className="mt-1 text-lg font-bold uppercase tracking-[0.08em] text-[var(--gov-ink)]">
            {feed.id}
          </h2>
          <div className="mt-2 text-sm text-[var(--gov-muted)]">
            {systemEnabled ? "Processed detection view for the selected feed." : "Raw source view for the selected feed."}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="border border-[var(--gov-line-strong)] bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)] hover:border-[var(--gov-blue)] hover:text-[var(--gov-blue)]"
        >
          Back to Grid
        </button>
      </div>

      <div className="grid gap-4 px-4 py-4 sm:px-5 xl:grid-cols-[minmax(0,1.3fr)_320px]">
        <div className="space-y-3">
          <div className="aspect-video overflow-hidden border border-[var(--gov-line)] bg-black">
            <FeedMedia feed={feed} systemEnabled={systemEnabled} detail />
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="border border-[var(--gov-line)] bg-[var(--gov-paper-alt)] px-4 py-3">
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)]">View Mode</div>
              <div className="mt-2 text-sm font-semibold text-[var(--gov-ink)]">
                {systemEnabled ? "Processed system output" : "Raw surveillance feed"}
              </div>
            </div>
            <div className="border border-[var(--gov-line)] bg-[var(--gov-paper-alt)] px-4 py-3">
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)]">Location</div>
              <div className="mt-2 text-sm font-semibold text-[var(--gov-ink)]">{feed.location}</div>
            </div>
            <div className="border border-[var(--gov-line)] bg-[var(--gov-paper-alt)] px-4 py-3">
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)]">Address</div>
              <div className="mt-2 text-sm text-[var(--gov-ink)]">{feed.address}</div>
            </div>
          </div>
        </div>

        <aside className="space-y-3 border border-[var(--gov-line)] bg-[var(--gov-paper-alt)] px-4 py-4">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--gov-blue)]">Feed Actions</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {feed.videoUrl ? (
                <a
                  href={feed.videoUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="border border-[var(--gov-line-strong)] bg-white px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--gov-blue)] hover:border-[var(--gov-blue)]"
                >
                  Open Source Video
                </a>
              ) : null}
              <a
                href={feed.stream_video}
                target="_blank"
                rel="noopener noreferrer"
                className="border border-[var(--gov-line-strong)] bg-white px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--gov-blue)] hover:border-[var(--gov-blue)]"
              >
                Open Processed Stream
              </a>
              {feed.locationLink ? (
                <a
                  href={feed.locationLink}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="border border-[var(--gov-line-strong)] bg-white px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--gov-blue)] hover:border-[var(--gov-blue)]"
                >
                  Open Map
                </a>
              ) : null}
            </div>
          </div>

          <div className="border-t border-[var(--gov-line)] pt-3">
            <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--gov-blue)]">Monitor Notes</div>
            <div className="mt-3 space-y-2 text-sm leading-6 text-[var(--gov-muted)]">
              <p>
                Processed mode uses the backend detection stream for this specific camera. Keeping this monitor open is what drives live violation generation for the selected feed.
              </p>
              <p>
                Raw mode shows the uploaded surveillance source directly so you can compare the original video against the annotated system output.
              </p>
            </div>
          </div>
        </aside>
      </div>
    </section>
  );
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

export default function LiveSurveillanceDashboard() {
  const { admin, logout } = useAdminSession();
  const [nav, setNav] = useState<NavKey>("overview");
  const [feeds, setFeeds] = useState<SurveillanceFeed[]>([]);
  const [selectedFeedId, setSelectedFeedId] = useState<string | null>(null);
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
        if (item.key === "overview") return true; // anyone can view overview
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

  const selectedFeed = useMemo(
    () => feeds.find((feed) => feed.id === selectedFeedId) ?? null,
    [feeds, selectedFeedId],
  );

  const openFeedMonitor = (feedId: string) => {
    setSelectedFeedId(feedId);
    setSystemEnabled(true);
  };

  useEffect(() => {
    if (selectedFeedId && !selectedFeed) {
      const timer = window.setTimeout(() => setSelectedFeedId(null), 0);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, [selectedFeed, selectedFeedId]);

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

          {activeNav === "overview" ? (
             <div className="h-[800px] w-full border border-[var(--gov-line)] shadow-sm">
                <DashboardMap 
                  onSelectCamera={(feedId) => {
                    setNav("live");
                    openFeedMonitor(feedId);
                  }}
                />
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
                <>
                  {selectedFeed ? (
                    <FeedMonitor
                      feed={selectedFeed}
                      systemEnabled={systemEnabled}
                      onClose={() => setSelectedFeedId(null)}
                    />
                  ) : null}

                  {filteredFeeds.length > 0 ? (
                    <div className="grid gap-4 sm:grid-cols-2 2xl:grid-cols-3">
                      {filteredFeeds.map((feed) => (
                        <FeedTile
                          key={feed.id}
                          feed={feed}
                          systemEnabled={systemEnabled}
                          onOpen={openFeedMonitor}
                        />
                      ))}
                    </div>
                  ) : (
                    <div className="border border-dashed border-[var(--gov-line-strong)] bg-[var(--gov-paper-alt)] px-4 py-8 text-sm text-[var(--gov-muted)]">
                      No feeds matched the current search.
                    </div>
                  )}
                </>
              ) : null}
            </div>
          ) : null}
        </main>
      </div>
    </DashboardShell>
  );
}
