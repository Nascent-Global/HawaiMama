export default function AnimatedBackground() {
  return (
    <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden" aria-hidden>
      <div className="absolute inset-0 gov-grid" />
      <div className="absolute inset-x-0 top-0 h-24 bg-[linear-gradient(90deg,#c1272d_0%,#c1272d_24%,#003893_24%,#003893_100%)] opacity-95" />
      <div className="absolute inset-x-0 top-24 h-px bg-[rgba(18,35,61,0.2)]" />
      <div className="absolute right-0 top-0 h-72 w-72 rounded-full bg-[rgba(0,56,147,0.08)] blur-3xl" />
      <div className="absolute bottom-0 left-0 h-80 w-80 rounded-full bg-[rgba(193,39,45,0.08)] blur-3xl" />
    </div>
  );
}
