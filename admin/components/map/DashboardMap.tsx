"use client";

import dynamic from "next/dynamic";

// Dynamically import the map to disable SSR.
// react-leaflet heavily strictly requires `window` to be defined.
const MapClient = dynamic(() => import("./MapClient"), { 
    ssr: false,
    loading: () => (
      <div className="w-full h-full flex items-center justify-center bg-gray-100 rounded-lg animate-pulse">
        <span className="text-gray-500 font-medium">Loading Map Data...</span>
      </div>
    )
});

interface DashboardMapProps {
  onSelectCamera?: (feedId: string) => void;
}

export default function DashboardMap({ onSelectCamera }: DashboardMapProps) {
  return <MapClient onSelectCamera={onSelectCamera} />;
}
