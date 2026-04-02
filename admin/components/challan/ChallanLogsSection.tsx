"use client";

import React, { useState, useEffect } from 'react';
import { ChallanLog } from '@/types/challan';
import { getChallans } from '@/lib/api';

const ChallanLogsSection: React.FC = () => {
  const [challans, setChallans] = useState<ChallanLog[]>([]);
  const [selected, setSelected] = useState<ChallanLog | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        setIsLoading(true);
        setError(null);
        const data = await getChallans();
        setChallans(data as unknown as ChallanLog[]);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : 'Failed to load challans');
      } finally {
        setIsLoading(false);
      }
    }
    load();
  }, []);

  return (
    <div className="flex-1 flex flex-col items-stretch py-6 px-6 overflow-y-auto relative w-full h-full text-black bg-white rounded-lg shadow-inner">
      {!selected && (
        <>
          <h1 className="text-2xl font-bold mb-6">Challan Logs</h1>
          {isLoading && <div className="text-sm text-gray-500">Loading challans…</div>}
          {error && <div className="mb-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
          <div className="w-full space-y-4">
            {challans.map((c) => (
              <div
                key={c.id}
                className="flex items-center justify-between bg-white border border-gray-200 rounded-lg px-4 py-3 shadow-sm"
              >
                <div className="flex items-center space-x-4">
                  <div className="w-12 h-12 rounded-full bg-gray-200 flex items-center justify-center text-xl font-bold text-blue-600">
                    {c.owner.fullName[0].toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline space-x-3">
                      <h3 className="text-lg font-semibold text-gray-900 truncate">{c.owner.fullName}</h3>
                      <span className="text-sm text-gray-500">Age: {c.owner.age}</span>
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      <a
                        href={c.location.mapLink}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="underline"
                      >
                        {c.location.place}
                      </a>
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      challan id. {c.ticket.ticketNumber}
                    </div>
                  </div>
                </div>

                <div className="flex flex-col items-start min-w-[200px]">
                  <div className="text-sm font-semibold">{c.offense.title}</div>
                  <div className="text-sm text-gray-600">fees: RS {c.offense.fineAmount}</div>
                  <div className="mt-1 mb-2">
                    <span className="inline-block px-2 py-0.5 bg-red-300 text-white font-mono text-xs font-bold tracking-widest rounded-sm border border-red-400">
                      {c.vehicle.registrationNumber}
                    </span>
                  </div>
                  <div className="text-xs text-gray-400">
                    {c.ticket.time} | {c.ticket.issueDateBS}
                  </div>
                </div>

                <button
                  className="ml-4 px-4 py-2 border rounded text-sm font-medium bg-blue-50 hover:bg-blue-100"
                  onClick={() => setSelected(c)}
                >
                  view challan
                </button>
              </div>
            ))}
          </div>
        </>
      )}
      
      {selected && (
        <div className="absolute inset-0 z-10 bg-gray-100 flex flex-col items-center overflow-y-auto pt-8 pb-12 shadow-inner">
          <div className="w-full max-w-4xl bg-[#fefdfb] shadow-2xl border border-gray-300 rounded-sm flex flex-col relative mx-auto my-4 text-black font-serif">
            {/* Top Action Bar (Overlay or sticky) */}
            <div className="absolute top-0 w-full flex justify-end items-center px-4 py-2 border-b bg-[#fefdfb] border-gray-200 print:hidden sticky z-20 shadow-sm rounded-t-sm">
              <button
                className="px-4 py-1 text-xs border border-gray-300 rounded bg-white hover:bg-gray-50 mr-2 uppercase tracking-wide font-medium"
                onClick={() => window.print()}
              >
                Print
              </button>
              <button
                className="px-4 py-1 text-xs border border-gray-300 rounded bg-red-50 text-red-700 hover:bg-red-100 uppercase tracking-wide font-medium"
                onClick={() => setSelected(null)}
              >
                Close
              </button>
            </div>

            <div className="px-10 py-12 mt-10 w-full">
              {/* Header */}
              <div className="text-center mb-8 border-b-2 border-black pb-6 relative">
                <h3 className="text-xl font-bold uppercase tracking-widest">{selected.authority.country}</h3>
                <h4 className="text-lg font-bold">{selected.authority.ministry}</h4>
                <h2 className="text-2xl font-black mt-2 underline">{selected.authority.office}</h2>
                <h1 className="text-3xl font-black mt-4 uppercase tracking-[0.2em] text-red-700">Challan Details</h1>
              </div>

              {/* Top Record Info */}
              {selected.metadata.isMockData && (
                <div className="mb-4 rounded border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                  Demo data — not real DoTM records
                </div>
              )}
              <div className="flex justify-between items-start mb-6 text-sm font-bold border border-black p-4 bg-gray-50/50">
                <div className="space-y-1">
                  <div>TICKET NUMBER: <span className="text-red-700 text-lg tracking-wider">{selected.ticket.ticketNumber}</span></div>
                  <div>ISSUE DATE (BS): {selected.ticket.issueDateBS}</div>
                  <div>ISSUE DATE (AD): {selected.ticket.issueDateAD}</div>
                </div>
                <div className="space-y-1 text-right">
                  <div>ISSUE TIME: {selected.ticket.time}</div>
                  <div>PAYMENT: <span className="uppercase text-red-600">{selected.payment.status}</span></div>
                  <div className="text-xs text-gray-500">CHALLAN ID: {selected.id}</div>
                </div>
              </div>

              {/* Data Grid */}
              <div className="border-t-2 border-l-2 border-r-2 border-black border-b-2 text-sm leading-relaxed mb-8">
                
                {/* Driver Section */}
                <div className="grid grid-cols-1 md:grid-cols-2">
                  <div className="p-3 border-r border-b border-black">
                    <span className="font-bold mr-2 text-xs text-gray-500 uppercase tracking-wide block mb-1">Offender Details</span>
                    <div>Name: <span className="font-bold text-base">{selected.owner.fullName}</span></div>
                    <div>Age: {selected.owner.age} &nbsp;&nbsp;|&nbsp;&nbsp; Contact: {selected.owner.contactNumber}</div>
                    <div>Address: {selected.owner.address}</div>
                  </div>
                  <div className="p-3 border-b border-black">
                    <span className="font-bold mr-2 text-xs text-gray-500 uppercase tracking-wide block mb-1">License Details</span>
                    <div>License No: <span className="font-bold">{selected.license.licenseNumber}</span></div>
                    <div>Category: {selected.license.category} &nbsp;&nbsp;|&nbsp;&nbsp; Expires: {selected.license.expiryDate}</div>
                  </div>
                </div>

                {/* Vehicle Section */}
                <div className="grid grid-cols-1 md:grid-cols-2 bg-gray-50/30">
                  <div className="p-3 border-r border-b border-black">
                    <span className="font-bold mr-2 text-xs text-gray-500 uppercase tracking-wide block mb-1">Vehicle Details</span>
                    <div>Reg. Number: <span className="font-bold text-lg">{selected.vehicle.registrationNumber}</span></div>
                    <div>Type: {selected.vehicle.vehicleType} ({selected.vehicle.color})</div>
                    <div>Model: {selected.vehicle.model}</div>
                  </div>
                  <div className="p-3 border-b border-black flex flex-col justify-center items-center">
                    <div className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-1">Fine Amount (RS)</div>
                    <div className="text-4xl font-black text-red-700">RS {selected.offense.fineAmount}/-</div>
                  </div>
                </div>

                {/* Offense Section */}
                <div className="p-4 border-b border-black">
                    <span className="font-bold mr-2 text-xs text-gray-500 uppercase tracking-wide block mb-2">Offense Record</span>
                    <div className="mb-2">
                      Section Ref: <span className="font-bold">{selected.offense.sectionCode}</span> &nbsp;&nbsp;|&nbsp;&nbsp;
                      Points Deducted: <span className="font-bold text-red-600">{selected.offense.pointsDeducted}</span>
                    </div>
                    <div>Offense Title: <span className="font-bold underline">{selected.offense.title}</span></div>
                    <div className="mt-2 text-gray-800 bg-gray-100 p-2 italic border-l-4 border-gray-400">
                      &quot;{selected.offense.description}&quot;
                    </div>
                    <div className="mt-3">Location: <strong>{selected.location.place}, {selected.location.district}</strong></div>
                </div>

                {/* Officer Section */}
                <div className="grid grid-cols-1 md:grid-cols-2">
                  <div className="p-4 border-r border-black">
                     <span className="font-bold mr-2 text-xs text-gray-500 uppercase tracking-wide block mb-2">Issuing Authority</span>
                     <div>Officer Name: {selected.officer.name}</div>
                     <div>Rank: {selected.officer.rank}</div>
                     <div>Badge Number: {selected.officer.badgeNumber}</div>
                  </div>
                  <div className="p-4 flex flex-col items-center justify-end relative h-32">
                     <div className="absolute right-8 top-4 opacity-10 border-4 border-black rounded-full w-24 h-24 flex items-center justify-center transform -rotate-12 pointer-events-none">
                       <span className="font-black text-xs text-center border-t border-b border-black py-1">OFFICIAL<br/>SEAL</span>
                     </div>
                     <div className="italic text-2xl font-[signature] opacity-70 mb-2">{selected.officer.signature}</div>
                     <div className="w-48 border-t border-black border-dashed pt-1 text-center font-bold text-xs">OFFICER SIGNATURE</div>
                  </div>
                </div>

              </div>

              {/* Informational paragraph */}
              <div className="text-justify text-xs text-gray-500 leading-tight">
                This is a computer-generated challan based on {selected.metadata.source} evidence. Payment must be cleared within 35 days of issuance to avoid late penalties. Failure to comply may lead to license suspension and legal action. For dispute resolution, contact the central traffic authority immediately.
              </div>

            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ChallanLogsSection;
