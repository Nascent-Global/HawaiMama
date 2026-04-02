"use client";

/* eslint-disable @next/next/no-img-element */

import React, { useState, useEffect } from 'react';
import { ViolationLog } from '@/types/violation';
import { getViolations, verifyViolation } from '@/lib/api';

function isStreamUrl(url: string): boolean {
  return url.includes('/camera/') && url.endsWith('/stream');
}

function evidenceVideoLabel(violation: ViolationLog): string {
  if (!violation.videoUrl) {
    return '';
  }
  if (violation.evidenceClipUrl && violation.videoUrl === violation.evidenceClipUrl) {
    return 'Evidence clip';
  }
  if (isStreamUrl(violation.videoUrl)) {
    return 'Live processed stream';
  }
  return 'Source clip';
}

const ViolationLogsSection: React.FC = () => {
  const [violations, setViolations] = useState<ViolationLog[]>([]);
  const [selected, setSelected] = useState<ViolationLog | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [verifyingId, setVerifyingId] = useState<string | null>(null);
  const selectedScreenshots = selected
    ? [selected.screenshot1Url, selected.screenshot2Url, selected.screenshot3Url].filter(Boolean)
    : [];

  useEffect(() => {
    async function load() {
      try {
        setIsLoading(true);
        setError(null);
        const data = await getViolations();
        setViolations(data);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : 'Failed to load violations');
      } finally {
        setIsLoading(false);
      }
    }
    load();
  }, []);

  const handleVerify = async (id: string) => {
    try {
      setVerifyingId(id);
      const result = await verifyViolation(id);
      setViolations((prev) =>
        prev.map((v) => (v.id === id ? result.violation : v))
      );
      setSelected((prev) => (prev && prev.id === id ? result.violation : prev));
    } catch (verifyError) {
      setError(verifyError instanceof Error ? verifyError.message : 'Failed to verify violation');
    } finally {
      setVerifyingId(null);
    }
  };

  return (
    <div className="flex-1 flex flex-col items-stretch py-6 px-6 overflow-y-auto relative w-full h-full text-black bg-white rounded-lg shadow-inner">
        {!selected && (
          <>
            <h1 className="text-2xl font-bold mb-6">Violation Logs</h1>
            {isLoading && <div className="text-sm text-gray-500">Loading violations…</div>}
            {error && <div className="mb-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
            <div className="w-full space-y-4">
              {violations.map((v) => (
                <div
                  key={v.id}
                  className="flex items-center justify-between bg-white border border-gray-200 rounded-lg px-4 py-3 shadow-sm"
                >
                  <div className="flex items-center space-x-4">
                    <div className="w-12 h-12 rounded-full bg-gray-200 flex items-center justify-center text-xl font-bold text-blue-600">
                      {v.driverName[0]}
                    </div>
                    <div className="flex-1 min-w-0">
                    <div className="flex items-baseline space-x-3">
                        <h3 className="text-lg font-semibold text-gray-900 truncate">{v.ownerName || v.driverName}</h3>
                      </div>
                      <div className="mt-1 mb-2">
                        <span className="inline-block px-3 py-1 bg-red-300 text-white font-mono text-xs font-bold tracking-widest rounded-md border-b-2 border-r-2 border-red-500 shadow-sm">
                          {v.licensePlate}
                        </span>
                      </div>
                      <div className="text-xs text-gray-500">
                        <a
                          href={v.locationLink}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="underline"
                        >
                          {v.tempAddress}
                        </a>
                      </div>
                      <div className="text-sm font-medium mt-1">{v.title}</div>
                      <div className="text-xs text-gray-400">
                        {new Date(v.timestamp).toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit',
                        })}{' '}
                        | {new Date(v.timestamp).toLocaleDateString('en-NP', { day: 'numeric', month: 'short', year: 'numeric' })}
                      </div>
                    </div>
                  </div>
                  <button
                    className="ml-4 px-4 py-2 border rounded text-sm font-medium bg-blue-50 hover:bg-blue-100"
                    onClick={() => setSelected(v)}
                  >
                    more detail
                  </button>
                </div>
              ))}
            </div>
          </>
        )}
        {selected && (
          <div className="absolute inset-0 z-10 bg-white flex flex-col overflow-y-auto">
            <div className="flex justify-between items-center px-6 py-4 border-b">
              <div>
                <div className="text-lg font-semibold">{selected.title}</div>
                <div className="mt-2 mb-2">
                  <span className="inline-block px-3 py-1 bg-yellow-300 text-gray-900 font-mono text-sm font-bold tracking-widest rounded-md border-b-2 border-r-2 border-yellow-500 shadow-sm rotate-[1deg]">
                    {selected.licensePlate}
                  </span>
                </div>
                <div className="text-xs text-gray-400 mt-1">
                  {new Date(selected.timestamp).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}{' '}
                  | {new Date(selected.timestamp).toLocaleDateString('en-NP', { day: 'numeric', month: 'short', year: 'numeric' })}
                </div>
              </div>
              <button
                className="text-gray-500 border px-3 py-1 rounded hover:bg-gray-100"
                onClick={() => setSelected(null)}
              >
                close
              </button>
            </div>
            <div className="p-6 flex-1 overflow-y-auto">
              <div className="flex items-center space-x-4 mb-4">
                <div className="w-14 h-14 rounded-full bg-gray-200 flex items-center justify-center text-2xl font-bold text-blue-600">
                  {selected.driverName[0]}
                </div>
                <div>
                  <div className="font-semibold">{selected.ownerName || selected.driverName}</div>
                  <div className="text-xs text-gray-500">{selected.licensePlate}</div>
                  <div className="mt-1 text-xs text-gray-500">
                    {[selected.cameraId?.toUpperCase(), selected.cameraLocation || selected.tempAddress]
                      .filter(Boolean)
                      .join(' · ')}
                  </div>
                </div>
              </div>
              {selected.isMockData && (
                <div className="mb-4 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                  Demo data — not real DoTM records
                </div>
              )}
              <div className="mb-4 grid gap-3 rounded border border-gray-200 bg-gray-50 p-4 text-sm text-gray-700 md:grid-cols-2">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">Camera</div>
                  <div>{selected.cameraId?.toUpperCase() || 'Unknown feed'}</div>
                </div>
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">Location</div>
                  {selected.cameraLocationLink ? (
                    <a
                      href={selected.cameraLocationLink}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-600 underline"
                    >
                      {selected.cameraLocation || selected.tempAddress}
                    </a>
                  ) : (
                    <div>{selected.cameraLocation || selected.tempAddress}</div>
                  )}
                </div>
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">Owner Address</div>
                  <div>{selected.ownerAddress || selected.tempAddress}</div>
                </div>
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">Evidence Source</div>
                  <div className="capitalize">{selected.evidenceProvider || 'local'}</div>
                </div>
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">Playback</div>
                  <div>{evidenceVideoLabel(selected) || 'Unavailable'}</div>
                </div>
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">Vehicle Color</div>
                  <div>{selected.vehicleColor || 'Unknown'}</div>
                </div>
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">Registration Date</div>
                  <div>{selected.registrationDate || 'Unknown'}</div>
                </div>
              </div>
              {selectedScreenshots.length > 0 && (
                <div className={`grid gap-2 mb-4 ${selectedScreenshots.length === 1 ? 'grid-cols-1' : 'grid-cols-3'}`}>
                  {selectedScreenshots.map((screenshot, index) => (
                    <img
                      key={screenshot}
                      src={screenshot}
                      alt={`Screenshot ${index + 1}`}
                      className="rounded border object-cover h-24 w-full"
                    />
                  ))}
                </div>
              )}
              {selected.videoUrl && (
                <div className="mb-4">
                  <div className="mb-2 flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-gray-500">
                    <span>{evidenceVideoLabel(selected)}</span>
                    {selected.sourceVideoUrl && selected.videoUrl !== selected.sourceVideoUrl && (
                      <a
                        href={selected.sourceVideoUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 underline normal-case tracking-normal"
                      >
                        Open source clip
                      </a>
                    )}
                  </div>
                  {isStreamUrl(selected.videoUrl) ? (
                    <div className="overflow-hidden rounded border bg-black">
                      <img
                        src={selected.videoUrl}
                        alt={`Live stream for ${selected.title}`}
                        className="w-full"
                      />
                    </div>
                  ) : (
                    <video controls className="w-full rounded border">
                      <source src={selected.videoUrl} type="video/mp4" />
                      Your browser does not support the video tag.
                    </video>
                  )}
                </div>
              )}
              <div className="mb-4 text-gray-700">{selected.description}</div>
              <div className="flex items-center space-x-4">
                <a
                  href={selected.locationLink}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 underline"
                >
                  View on Map
                </a>
                {!selected.verified && (
                  <button
                    className="px-4 py-2 bg-[#3B82F6] text-white rounded font-medium hover:bg-blue-700"
                    disabled={verifyingId === selected.id}
                    onClick={() => handleVerify(selected.id)}
                  >
                    {verifyingId === selected.id ? 'Verifying…' : 'Verify & Generate Challan'}
                  </button>
                )}
                {selected.verified && (
                  <span className="px-3 py-1 bg-green-100 text-green-700 rounded text-sm font-medium">
                    Verified & Challan Issued
                  </span>
                )}
              </div>
            </div>
          </div>
        )}
    </div>
  );
};

export default ViolationLogsSection;
