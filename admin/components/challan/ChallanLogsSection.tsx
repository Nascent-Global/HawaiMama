"use client";

import type { ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { getChallans } from "@/lib/api";
import type { ChallanLog } from "@/types/challan";

function valueOrPlaceholder(value: string | null | undefined, fallback = "Not captured") {
  return value && value.trim() ? value : fallback;
}

function LedgerItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="border-b border-[var(--gov-line)] py-2 last:border-b-0">
      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--gov-muted)]">{label}</div>
      <div className="mt-1 text-sm text-[var(--gov-ink)]">{value}</div>
    </div>
  );
}

export default function ChallanLogsSection() {
  const [challans, setChallans] = useState<ChallanLog[]>([]);
  const [selected, setSelected] = useState<ChallanLog | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const printRef = useRef<HTMLDivElement | null>(null);

  const handlePrint = () => {
    if (!selected || !printRef.current) return;

    const printHtml = `
      <html>
        <head>
          <title>Challan - ${selected.ticket.ticketNumber}</title>
          <style>
            body { font-family: Inter, sans-serif; margin: 0; padding: 12px; color: #0f172a; background: #f8fafc; }
            .printable { width: 100%; }
            .border { border: 1px solid #cbd5e1; }
            .border-b-4 { border-bottom-width: 4px; }
            .text-center { text-align: center; }
            .text-sm { font-size: 0.875rem; }
            .text-lg { font-size: 1.125rem; }
            .text-xl { font-size: 1.25rem; }
            .font-bold { font-weight: 700; }
            .uppercase { text-transform: uppercase; }
            .tracking-[0.22em], .tracking-[0.24em] { letter-spacing: 0.22em; }
            .py-4 { padding-top: 1rem; padding-bottom: 1rem; }
            .px-6 { padding-left: 1.5rem; padding-right: 1.5rem; }
            .p-4 { padding: 1rem; }
            .bg-white { background: white; }
          </style>
        </head>
        <body>
          <div class="printable">${printRef.current.innerHTML}</div>
        </body>
      </html>
    `;

    const printWindow = window.open("", "_blank", "width=900,height=800");
    if (!printWindow) return;

    printWindow.document.open();
    printWindow.document.write(printHtml);
    printWindow.document.close();
    printWindow.focus();

    setTimeout(() => {
      printWindow.print();
      printWindow.close();
    }, 250);
  };

  useEffect(() => {
    async function load() {
      try {
        setIsLoading(true);
        setError(null);
        const data = await getChallans();
        setChallans(data as unknown as ChallanLog[]);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Failed to load challans");
      } finally {
        setIsLoading(false);
      }
    }

    void load();
  }, []);

  return (
    <section className="flex h-full min-h-[640px] flex-col overflow-hidden border border-[var(--gov-line)] bg-[var(--gov-paper)]">
      <header className="border-b-4 border-[var(--gov-red)] bg-[var(--gov-paper-alt)] px-4 py-3 sm:px-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--gov-blue)]">
              Revenue and Notice Register
            </p>
            <h1 className="mt-1 text-xl font-bold text-[var(--gov-ink)] [font-family:var(--font-heading)]">
              Challan Logs
            </h1>
          </div>
          <div className="inline-flex items-center gap-2 border border-[var(--gov-line)] bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)]">
            <span>{challans.length}</span>
            <span>Notices</span>
          </div>
        </div>
      </header>

      {error ? (
        <div className="border-b border-[var(--gov-red)] bg-[rgba(193,39,45,0.08)] px-4 py-2 text-sm text-[var(--gov-red-dark)]">
          {error}
        </div>
      ) : null}

      <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(0,1fr)_minmax(400px,1.05fr)]">
        <div className="gov-scrollbar min-h-0 overflow-auto border-r border-[var(--gov-line)]">
          <div className="hidden grid-cols-[150px_minmax(0,1fr)_120px_120px] border-b border-[var(--gov-line-strong)] bg-[var(--gov-highlight)] px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--gov-muted)] md:grid">
            <span>Ticket</span>
            <span>Offender</span>
            <span>Fine</span>
            <span>Status</span>
          </div>

          {isLoading ? <div className="px-4 py-8 text-sm text-[var(--gov-muted)]">Loading challan notices...</div> : null}
          {!isLoading && challans.length === 0 ? (
            <div className="px-4 py-8 text-sm text-[var(--gov-muted)]">No challan notices available.</div>
          ) : null}

          <div className="divide-y divide-[var(--gov-line)]">
            {challans.map((challan) => {
              const isSelected = selected?.id === challan.id;
              return (
                <button
                  key={challan.id}
                  type="button"
                  onClick={() => setSelected(challan)}
                  className={`grid w-full gap-3 px-4 py-3 text-left transition hover:bg-[var(--gov-highlight)] md:grid-cols-[150px_minmax(0,1fr)_120px_120px] ${
                    isSelected ? "bg-[var(--gov-highlight)]" : "bg-white"
                  }`}
                >
                  <div className="space-y-1">
                    <div className="font-mono text-xs font-bold tracking-[0.16em] text-[var(--gov-red-dark)]">
                      {challan.ticket.ticketNumber}
                    </div>
                    <div className="text-xs text-[var(--gov-muted)]">{challan.ticket.issueDateBS}</div>
                  </div>
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-[var(--gov-ink)]">{challan.owner.fullName}</div>
                    <div className="mt-1 truncate text-sm text-[var(--gov-muted)]">{challan.offense.title}</div>
                    <div className="mt-1 truncate text-xs text-[var(--gov-muted)]">
                      {valueOrPlaceholder(challan.location.place)} | {challan.vehicle.registrationNumber}
                    </div>
                  </div>
                  <div className="text-sm font-semibold text-[var(--gov-ink)]">Rs {challan.offense.fineAmount}</div>
                  <div>
                    <span
                      className={`inline-flex border px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.15em] ${
                        challan.payment.status.toLowerCase() === "paid"
                          ? "border-emerald-700 bg-emerald-50 text-emerald-800"
                          : "border-[var(--gov-red)] bg-[rgba(193,39,45,0.08)] text-[var(--gov-red-dark)]"
                      }`}
                    >
                      {challan.payment.status}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <div className="gov-scrollbar min-h-0 overflow-auto bg-[var(--gov-paper-alt)]">
          {selected ? (
            <div className="px-4 py-4 sm:px-5" ref={printRef}>
              <div className="mb-4 flex items-start justify-between gap-3">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--gov-red)]">
                    Official Notice
                  </p>
                  <h2 className="mt-1 text-lg font-bold text-[var(--gov-ink)] [font-family:var(--font-heading)]">
                    Traffic Challan Document
                  </h2>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="border border-[var(--gov-line-strong)] bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)] hover:border-[var(--gov-blue)] hover:text-[var(--gov-blue)]"
                    onClick={handlePrint}
                  >
                    Print
                  </button>
                  <button
                    type="button"
                    className="border border-[var(--gov-line-strong)] bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--gov-muted)] hover:border-[var(--gov-blue)] hover:text-[var(--gov-blue)]"
                    onClick={() => setSelected(null)}
                  >
                    Close
                  </button>
                </div>
              </div>

              <div className="border border-[var(--gov-line-strong)] bg-white shadow-[0_12px_30px_rgba(18,35,61,0.06)]">
                <div className="border-b-4 border-[var(--gov-red)] px-6 py-6">
                  <div className="text-center">
                    <div className="text-sm font-semibold uppercase tracking-[0.24em] text-[var(--gov-blue)]">
                      {selected.authority.country}
                    </div>
                    {selected.authority.ministry ? (
                      <div className="mt-2 text-base font-semibold text-[var(--gov-ink)]">{selected.authority.ministry}</div>
                    ) : null}
                    {selected.authority.office ? (
                      <div className="mt-2 text-2xl font-bold text-[var(--gov-ink)] [font-family:var(--font-heading)]">
                        {selected.authority.office}
                      </div>
                    ) : null}
                    <div className="mt-4 inline-flex border border-[var(--gov-red)] bg-[rgba(193,39,45,0.08)] px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] text-[var(--gov-red-dark)]">
                      Challan Details
                    </div>
                  </div>
                </div>

                <div className="px-6 py-5">
                  {selected.metadata.isMockData ? (
                    <div className="mb-4 border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                      Demo data only. This notice is not from a live traffic authority ledger.
                    </div>
                  ) : null}

                  <div className="grid gap-4 border border-[var(--gov-line)] bg-[var(--gov-paper-alt)] p-4 md:grid-cols-2">
                    <LedgerItem label="Ticket Number" value={selected.ticket.ticketNumber} />
                    <LedgerItem label="Payment Status" value={selected.payment.status} />
                    <LedgerItem label="Issue Date BS" value={selected.ticket.issueDateBS} />
                    <LedgerItem label="Issue Date AD" value={selected.ticket.issueDateAD} />
                    <LedgerItem label="Issue Time" value={selected.ticket.time} />
                    <LedgerItem label="Challan ID" value={selected.id} />
                  </div>

                  <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1.05fr)_260px]">
                    <div className="space-y-4">
                      <div className="grid gap-4 border border-[var(--gov-line)] p-4 md:grid-cols-2">
                        <LedgerItem label="Offender Name" value={valueOrPlaceholder(selected.owner.fullName)} />
                        <LedgerItem label="Contact" value={valueOrPlaceholder(selected.owner.contactNumber)} />
                        <LedgerItem label="Address" value={valueOrPlaceholder(selected.owner.address)} />
                        <LedgerItem label="Age" value={selected.owner.age} />
                        <LedgerItem label="License Number" value={valueOrPlaceholder(selected.license.licenseNumber)} />
                        <LedgerItem
                          label="License Category"
                          value={`${valueOrPlaceholder(selected.license.category)} | Expires ${valueOrPlaceholder(selected.license.expiryDate)}`}
                        />
                      </div>

                      <div className="grid gap-4 border border-[var(--gov-line)] p-4 md:grid-cols-2">
                        <LedgerItem label="Vehicle Registration" value={valueOrPlaceholder(selected.vehicle.registrationNumber)} />
                        <LedgerItem
                          label="Vehicle Type"
                          value={`${valueOrPlaceholder(selected.vehicle.vehicleType, "Vehicle")} (${valueOrPlaceholder(selected.vehicle.color)})`}
                        />
                        <LedgerItem label="Vehicle Model" value={valueOrPlaceholder(selected.vehicle.model)} />
                        <LedgerItem label="Fine Amount" value={<span className="font-bold text-[var(--gov-red-dark)]">Rs {selected.offense.fineAmount}/-</span>} />
                      </div>

                      <div className="border border-[var(--gov-line)] p-4">
                        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--gov-muted)]">
                          Offense Record
                        </div>
                        <div className="mt-3 text-sm text-[var(--gov-ink)]">
                          <div>
                            Section Reference: <strong>{selected.offense.sectionCode}</strong>
                          </div>
                          <div className="mt-1">
                            Points Deducted: <strong className="text-[var(--gov-red-dark)]">{selected.offense.pointsDeducted}</strong>
                          </div>
                          <div className="mt-3 font-semibold">{selected.offense.title}</div>
                          <div className="mt-2 border-l-4 border-[var(--gov-blue)] bg-[var(--gov-highlight)] px-3 py-2 italic">
                            {selected.offense.description}
                          </div>
                          <div className="mt-3">
                            Location:{" "}
                            <strong>
                              {[selected.location.place, selected.location.district]
                                .filter((value) => value && value.trim())
                                .join(", ") || "Not captured"}
                            </strong>
                          </div>
                        </div>
                      </div>

                      <div className="grid gap-4 border border-[var(--gov-line)] p-4 md:grid-cols-2">
                        <LedgerItem label="Officer Name" value={valueOrPlaceholder(selected.officer.name)} />
                        <LedgerItem label="Rank" value={valueOrPlaceholder(selected.officer.rank)} />
                        <LedgerItem label="Badge Number" value={valueOrPlaceholder(selected.officer.badgeNumber)} />
                        <LedgerItem label="Evidence Source" value={selected.metadata.source} />
                      </div>

                      <div className="text-xs leading-6 text-[var(--gov-muted)]">
                        This is a computer-generated challan based on recorded traffic enforcement evidence. Payment should be cleared within 35 days of issuance to avoid late penalties. For dispute resolution, contact the issuing traffic office.
                      </div>
                    </div>

                    <aside className="border border-[var(--gov-line)] bg-[var(--gov-paper-alt)] px-4 py-4">
                      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--gov-blue)]">
                        Seal and Signature
                      </div>
                      <div className="mt-6 flex h-40 items-center justify-center border border-dashed border-[var(--gov-line-strong)] bg-white">
                        <div className="flex h-28 w-28 items-center justify-center rounded-full border-4 border-[var(--gov-blue)]/20 text-center text-xs font-semibold uppercase tracking-[0.12em] text-[var(--gov-blue)]">
                          Official
                          <br />
                          Seal
                        </div>
                      </div>
                      <div className="mt-8 border-t border-dashed border-[var(--gov-line-strong)] pt-2 text-center text-xs font-semibold uppercase tracking-[0.15em] text-[var(--gov-muted)]">
                        Officer Signature
                      </div>
                      <div className="mt-3 text-center text-xl text-[var(--gov-ink)]">
                        {selected.officer.signature || "Authorized Signatory"}
                      </div>
                    </aside>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="px-4 py-8 sm:px-5">
              <div className="border border-dashed border-[var(--gov-line-strong)] bg-white px-4 py-6 text-sm text-[var(--gov-muted)]">
                Select a challan notice from the register to inspect the printable document layout.
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
