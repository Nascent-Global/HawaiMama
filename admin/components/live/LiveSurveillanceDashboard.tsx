"use client";

import Image from "next/image";
import { useMemo, useState } from "react";
import { mockSurveillanceFeeds } from "@/lib/mock-surveillance-feeds";
import type { SurveillanceFeed } from "@/types/surveillance";
import ViolationLogsSection from "@/components/violation/ViolationLogsSection";
import AccidentLogsSection from "@/components/accident/AccidentLogsSection";
import ChallanLogsSection from "@/components/challan/ChallanLogsSection";

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

function FeedCard({
  feed,
  onOpen,
}: {
  feed: SurveillanceFeed;
  onOpen: () => void;
}) {
  return (
    <article className="feed-card">
      <div 
        role="button" 
        tabIndex={0} 
        className="feed-card-inner" 
        onClick={onOpen}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onOpen(); }}
      >
        <div className="feed-video-wrap">
          <span className="feed-live-dot" title="Live" />
          <video
            className="feed-video"
            src={feed.stream_video}
            poster={feed.poster}
            autoPlay
            loop
            muted
            playsInline
            preload="metadata"
            aria-label={`Surveillance at ${feed.address}`}
          />
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
                onClick={(e) => e.stopPropagation()}
              >
                {feed.location}
              </a>
            ) : (
              <span className="feed-location-link feed-location-link--pseudo">
                {feed.location}
              </span>
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
}: {
  feed: SurveillanceFeed;
  onBack: () => void;
}) {
  return (
    <div className="feed-detail">
      <div className="feed-detail-video-wrap">
        <button type="button" className="feed-back" onClick={onBack}>
          &lt; back
        </button>
        <span className="feed-live-dot feed-live-dot--large" title="Live" />
        <video
          className="feed-detail-video"
          src={feed.stream_video}
          poster={feed.poster}
          autoPlay
          loop
          muted
          playsInline
          preload="metadata"
          aria-label={`Surveillance at ${feed.address}`}
        />
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
          <span className="feed-detail-location feed-detail-location--pseudo">
            {feed.location}
          </span>
        )}
        <span className="feed-expand-icon feed-expand-icon--detail" aria-hidden>
          &lt; &gt;
        </span>
      </footer>
    </div>
  );
}

export default function LiveSurveillanceDashboard() {
  const [nav, setNav] = useState<NavKey>("live");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const feeds = useMemo(() => mockSurveillanceFeeds, []);
  const selected = useMemo(
    () => feeds.find((f) => f.id === selectedId) ?? null,
    [feeds, selectedId]
  );

  return (
    <div className="dash-root">
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
              <p className="logo-strip-tagline">
                Smart Traffic Management and Incident Response System
              </p>
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
            />
            <SearchIcon />
          </div>
        </div>
      </div>

      <div className="dash-body">
        <aside className="dash-sidebar" aria-label="Sections">
          <nav className="dash-nav" aria-label="Main">
            {navItems.map((item) => (
              <button
                key={item.key}
                type="button"
                className={`dash-nav-btn${nav === item.key ? " dash-nav-btn--active" : ""}`}
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
          {nav === "violations" && (
            <ViolationLogsSection />
          )}

          {nav === "accidents" && (
            <AccidentLogsSection />
          )}

          {nav === "challan" && (
            <ChallanLogsSection />
          )}

          {nav !== "live" && nav !== "violations" && nav !== "accidents" && nav !== "challan" && (
            <div className="dash-placeholder card-glass">
              <h2 className="dash-placeholder-title">
                {navItems.find((n) => n.key === nav)?.label}
              </h2>
              <p>Section coming next — Live surveillance is wired first.</p>
            </div>
          )}

          {nav === "live" && !selected && (
            <div className="feed-grid-scroll">
              <div className="feed-grid">
                {feeds.map((feed) => (
                  <FeedCard
                    key={feed.id}
                    feed={feed}
                    onOpen={() => setSelectedId(feed.id)}
                  />
                ))}
              </div>
            </div>
          )}

          {nav === "live" && selected && (
            <FeedDetail feed={selected} onBack={() => setSelectedId(null)} />
          )}
        </div>
      </div>
    </div>
  );
}