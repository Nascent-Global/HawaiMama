"use client";

/* eslint-disable @next/next/no-img-element */

import Image from "next/image";
import Link from "next/link";
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

function SystemToggle({
  enabled,
  onChange,
}: {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
}) {
  return (
    <label className="dash-system-toggle">
      <div className="dash-system-toggle-copy">
        <span className="dash-system-toggle-label">System Output</span>
        <span className="dash-system-toggle-hint">
          {enabled ? "Uses each feed's admin mode" : "Raw surveillance video"}
        </span>
      </div>
      <span
        className={`dash-system-toggle-track${
          enabled ? " dash-system-toggle-track--enabled" : ""
        }`}
      >
        <input
          type="checkbox"
          className="sr-only"
          checked={enabled}
          onChange={(event) => onChange(event.target.checked)}
          aria-label="Toggle processed surveillance system"
        />
        <span
          className={`dash-system-toggle-thumb${
            enabled ? " dash-system-toggle-thumb--enabled" : ""
          }`}
        />
      </span>
    </label>
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
  const className = detail ? "feed-detail-video" : "feed-video";
  const mediaKey = `${feed.id}-${systemEnabled ? "system" : "raw"}-${detail ? "detail" : "grid"}`;

  if (systemEnabled && detail) {
    return (
      <img
        key={mediaKey}
        className={className}
        src={feed.stream_video}
        alt={`System output at ${feed.address}`}
      />
    );
  }

  if (systemEnabled && feed.processedVideoUrl) {
    return (
      <video
        key={mediaKey}
        className={className}
        src={feed.processedVideoUrl}
        autoPlay
        muted
        loop
        playsInline
        preload="metadata"
        controls={detail}
      />
    );
  }

  if (systemEnabled && !detail) {
    return <div className={`${className} feed-video--empty`}>Processed preview unavailable</div>;
  }

  if (feed.videoUrl) {
    return (
      <video
        key={mediaKey}
        className={className}
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

  return <div className={`${className} feed-video--empty`}>Video unavailable</div>;
}

function FeedCard({
  feed,
  onOpen,
  systemEnabled,
}: {
  feed: SurveillanceFeed;
  onOpen: () => void;
  systemEnabled: boolean;
}) {
  return (
    <article className="feed-card">
      <div
        role="button"
        tabIndex={0}
        className="feed-card-inner"
        onClick={onOpen}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            onOpen();
          }
        }}
      >
        <div className="feed-video-wrap">
          <span className="feed-live-dot" title="Live" />
          <FeedMedia feed={feed} systemEnabled={systemEnabled} />
        </div>
        <footer className="feed-footer">
          <div className="feed-meta">
            <p className="feed-address">{feed.address}</p>
            {feed.location.startsWith("http") ? (
              <a
                className="feed-location-link"
                href={feed.location}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(event) => event.stopPropagation()}
              >
                {feed.location}
              </a>
            ) : (
              <span className="feed-location-link feed-location-link--pseudo">{feed.location}</span>
            )}
          </div>
          <span className="feed-expand-icon" aria-hidden>
            &lt; &gt;
          </span>
        </footer>
      </div>
    </article>
  );
}

function FeedDetail({
  feed,
  onBack,
  systemEnabled,
}: {
  feed: SurveillanceFeed;
  onBack: () => void;
  systemEnabled: boolean;
}) {
  return (
    <div className="feed-detail">
      <div className="feed-detail-video-wrap">
        <button type="button" className="feed-back" onClick={onBack}>
          &lt; back
        </button>
        <span className="feed-live-dot feed-live-dot--large" title="Live" />
        <FeedMedia feed={feed} systemEnabled={systemEnabled} detail />
      </div>
      <footer className="feed-detail-footer">
        <p className="feed-detail-address">{feed.address}</p>
        {feed.location.startsWith("http") ? (
          <a
            className="feed-detail-location"
            href={feed.location}
            target="_blank"
            rel="noopener noreferrer"
          >
            {feed.location}
          </a>
        ) : (
          <span className="feed-detail-location feed-detail-location--pseudo">{feed.location}</span>
        )}
        {feed.videoUrl ? (
          <a
            className="feed-detail-location"
            href={feed.videoUrl}
            target="_blank"
            rel="noopener noreferrer"
          >
            Open source clip
          </a>
        ) : null}
        <span className="feed-expand-icon feed-expand-icon--detail" aria-hidden>
          &lt; &gt;
        </span>
      </footer>
    </div>
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
        if (item.key === "live") {
          return canViewLive;
        }
        if (item.key === "violations") {
          return canViewViolations;
        }
        if (item.key === "accidents") {
          return canViewAccidents;
        }
        if (item.key === "challan") {
          return canViewChallans;
        }
        return false;
      }),
    [canViewAccidents, canViewChallans, canViewLive, canViewViolations],
  );

  const activeNav = useMemo<NavKey | null>(() => {
    if (visibleNavItems.length === 0) {
      return null;
    }
    return visibleNavItems.some((item) => item.key === nav) ? nav : visibleNavItems[0].key;
  }, [nav, visibleNavItems]);

  useEffect(() => {
    if (!admin || !canViewLive) {
      return;
    }
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
    if (!query) {
      return feeds;
    }
    return feeds.filter((feed) =>
      [feed.address, feed.location, feed.id].some((value) => value.toLowerCase().includes(query)),
    );
  }, [deferredSearchQuery, feeds]);

  const selected = useMemo(
    () => feeds.find((candidate) => candidate.id === selectedId) ?? null,
    [feeds, selectedId],
  );

  return (
    <div className="dash-root" suppressHydrationWarning>
      <div className="dash-top-bar">
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
              <p className="logo-strip-tagline">Smart Traffic Management and Incident Response System</p>
            </div>
          </div>
        </header>
        <div className="dash-toolbar dash-toolbar--inline">
          <div className="dash-search-wrap">
            <input
              type="search"
              className="dash-search"
              placeholder="Search cameras, wards, plate numbers…"
              aria-label="Search dashboard"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
            />
            <SearchIcon />
          </div>
          <SystemToggle enabled={systemEnabled} onChange={setSystemEnabled} />
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
          {canManageFeeds ? (
            <Link href="/admin" className="dash-utility-link">
              Feed Admin
            </Link>
          ) : null}
        </div>
      </div>

      <div className="dash-body">
        <aside className="dash-sidebar" aria-label="Sections">
          <nav className="dash-nav" aria-label="Main">
            {visibleNavItems.map((item) => (
              <button
                key={item.key}
                type="button"
                className={`dash-nav-btn${activeNav === item.key ? " dash-nav-btn--active" : ""}`}
                onClick={() => {
                  setNav(item.key);
                  setSelectedId(null);
                }}
              >
                <span className="dash-nav-btn-text">{item.label}</span>
              </button>
            ))}
          </nav>
        </aside>

        <div className="dash-main">
          {visibleNavItems.length === 0 ? (
            <div className="dash-placeholder card-glass">
              <h2 className="dash-placeholder-title">No sections assigned</h2>
              <p>Your account is active, but it has not been granted any panel permissions yet.</p>
            </div>
          ) : null}

          {activeNav === "violations" && canViewViolations ? (
            <ViolationLogsSection canVerify={canVerifyViolations} />
          ) : null}

          {activeNav === "accidents" && canViewAccidents ? (
            <AccidentLogsSection canVerify={canVerifyAccidents} />
          ) : null}

          {activeNav === "challan" && canViewChallans ? <ChallanLogsSection /> : null}

          {activeNav === "live" && canViewLive && !selected ? (
            <div className="feed-grid-scroll">
              {isLoadingFeeds ? (
                <div className="dash-placeholder card-glass">
                  <h2 className="dash-placeholder-title">Loading live feeds</h2>
                  <p>Connecting to the Python stream server.</p>
                </div>
              ) : null}
              {feedError ? (
                <div className="dash-placeholder card-glass">
                  <h2 className="dash-placeholder-title">Live feed unavailable</h2>
                  <p>{feedError}</p>
                </div>
              ) : null}
              <div className="feed-grid">
                {filteredFeeds.map((feed) => (
                  <FeedCard
                    key={feed.id}
                    feed={feed}
                    systemEnabled={systemEnabled}
                    onOpen={() => setSelectedId(feed.id)}
                  />
                ))}
              </div>
              {!isLoadingFeeds && !feedError && filteredFeeds.length === 0 ? (
                <div className="dash-placeholder card-glass">
                  <h2 className="dash-placeholder-title">No cameras matched</h2>
                  <p>Try a different search term.</p>
                </div>
              ) : null}
            </div>
          ) : null}

          {activeNav === "live" && canViewLive && selected ? (
            <FeedDetail feed={selected} systemEnabled={systemEnabled} onBack={() => setSelectedId(null)} />
          ) : null}
        </div>
      </div>
    </div>
  );
}
