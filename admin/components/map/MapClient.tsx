"use client";

import React, { useEffect, useState } from "react";
import type { GeoJsonObject } from "geojson";
import {
  MapContainer,
  TileLayer,
  GeoJSON,
  CircleMarker,
  Popup,
  Tooltip,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";

// Mock map points for demonstration. Sirjana Chowk is always mapped to the demo camera,
// other points are assigned a random feed so interactions always trigger live view.
const MOCK_OTHER_FEEDS = [
  "cam-fewa-02",
  "cam-license-03",
  "cam-machhapuchhre-04",
  "cam-vertical-05",
  "cam-board-06",
];

const CCTV_POINTS: CCTVPoint[] = [
  { name: "Sirjana Chowk", lat: 28.2118, lng: 83.9781, status: "Active", feedId: "cam-sirjana-01" },
  { name: "Lakeside (Fewa Corridor)", lat: 28.2105, lng: 83.9575, status: "Active", feedId: null },
  { name: "Prithvi Marg Checkpoint", lat: 28.2081, lng: 83.9880, status: "Active", feedId: null },
  { name: "Mitighar Approach", lat: 28.1994, lng: 83.9814, status: "Active", feedId: null },
  { name: "Zero Kilometer (Baglung Hwy)", lat: 28.2120, lng: 83.9705, status: "Active", feedId: null },
  { name: "New Road Traffic Cell", lat: 28.2045, lng: 83.9806, status: "Active", feedId: null },
  { name: "Birauta", lat: 28.1923, lng: 83.9782, status: "Active", feedId: null },
  { name: "Rastra Bank Chowk", lat: 28.2045, lng: 83.9806, status: "Active", feedId: null },
  { name: "Mustang Chowk", lat: 28.1994, lng: 83.9814, status: "Active", feedId: null },
];

function getDeterministicRandomFeedId(name: string): string {
  const hash = Array.from(name).reduce((acc, char) => (acc + char.charCodeAt(0)) % 1000, 0);
  return MOCK_OTHER_FEEDS[hash % MOCK_OTHER_FEEDS.length];
}


interface CCTVPoint {
  name: string;
  lat: number;
  lng: number;
  status: "Active" | "Inactive";
  feedId?: string | null;
}

interface MapClientProps {
  onSelectCamera?: (feedId: string) => void;
}

export default function MapClient({ onSelectCamera }: MapClientProps) {
  const [geoData, setGeoData] = useState<GeoJsonObject | null>(null);

  useEffect(() => {
    // Fetch the GeoJSON file we generated in the public folder
    fetch("/data/pokhara.geojson")
      .then((res) => res.json() as Promise<GeoJsonObject>)
      .then((data) => setGeoData(data))
      .catch((err) => console.error("Error loading GeoJSON", err));
  }, []);

  return (
    <div className="w-full h-full relative rounded-lg overflow-hidden border border-gray-200">
      <MapContainer
        center={[28.2096, 83.9856]} // Pokhara center
        zoom={13}
        scrollWheelZoom={true}
        className="w-full h-full z-0"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {/* Render Pokhara Municipality GeoJSON Boundary */}
        {geoData && (
          <GeoJSON
            data={geoData}
            style={() => ({
              color: "#3b82f6", // Blue outline
              weight: 2,
              fillColor: "#3b82f6",
              fillOpacity: 0.05, // Very light fill
            })}
          />
        )}

        {/* Render CCTV Points */}
        {CCTV_POINTS.map((pt, index) => {
          const assignedFeedId = pt.feedId || getDeterministicRandomFeedId(pt.name);
          const isActive = pt.status === "Active" && Boolean(assignedFeedId);

          return (
            <CircleMarker
              key={index}
              center={[pt.lat, pt.lng]}
              pathOptions={{ color: isActive ? "#ef4444" : "#9ca3af", fillColor: isActive ? "#ef4444" : "#9ca3af", fillOpacity: 0.8 }}
              radius={6}
              eventHandlers={{
                click: () => {
                  if (onSelectCamera && assignedFeedId) {
                    onSelectCamera(assignedFeedId);
                  }
                },
              }}
            >
              <Tooltip direction="top" offset={[0, -10]} opacity={1}>
                <span className="font-bold">{pt.name}</span>
              </Tooltip>
              <Popup>
                <div className="font-sans">
                  <h3 className="font-bold text-gray-900 border-b pb-1 mb-1">{pt.name}</h3>
                  <p className="text-sm text-gray-600">Type: PTZ Surveillance</p>
                  <p className={`text-sm font-semibold ${isActive ? "text-green-600" : "text-gray-400"}`}>• {pt.status}</p>
                  <button
                    className={`mt-2 w-full px-2 py-1 ${isActive ? "bg-blue-50 text-blue-700 hover:bg-blue-100" : "bg-gray-50 text-gray-400 cursor-not-allowed"} text-xs font-semibold rounded transition-colors`}
                    onClick={(e) => {
                      e.stopPropagation();
                      if (onSelectCamera && assignedFeedId) {
                        onSelectCamera(assignedFeedId);
                      }
                    }}
                    disabled={!isActive}
                  >
                    {isActive ? "View Live Feed" : "Feed Unavailable"}
                  </button>
                </div>
              </Popup>
            </CircleMarker>
          );
        })}
      </MapContainer>
    </div>
  );
}
