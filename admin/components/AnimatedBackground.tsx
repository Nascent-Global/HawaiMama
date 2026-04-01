"use client";

import { useEffect, useMemo, useState } from "react";
import Particles, { initParticlesEngine } from "@tsparticles/react";
import { loadSlim } from "@tsparticles/slim";

export default function AnimatedBackground() {
  const [engineReady, setEngineReady] = useState(false);

  useEffect(() => {
    initParticlesEngine(async (engine) => {
      await loadSlim(engine);
    }).then(() => setEngineReady(true));
  }, []);

  const options = useMemo(
    () => ({
      background: {
        color: { value: "#f4f7ff" },
      },
      fullScreen: {
        enable: false,
      },
      fpsLimit: 60,
      detectRetina: true,
      particles: {
        color: { value: ["#7dd3fc", "#a78bfa", "#c4b5fd"] },
        links: {
          color: "#cbd5e1",
          distance: 140,
          enable: true,
          opacity: 0.65,
          width: 1.2,
        },
        move: {
          direction: "none" as const,
          enable: true,
          outModes: { default: "out" as const },
          random: false,
          speed: 1,
          straight: false,
        },
        number: {
          density: { enable: true, area: 900 },
          value: 70,
        },
        opacity: { value: 0.85 },
        shape: { type: "circle" as const },
        size: { value: { min: 1.2, max: 3.5 } },
      },
      interactivity: {
        events: {
          onHover: {
            enable: true,
            mode: "grab" as const,
          },
          resize: { enable: true },
        },
        modes: {
          grab: { distance: 150, links: { opacity: 0.8 } },
        },
      },
    }),
    []
  );

  return (
    <div
      className="pointer-events-none fixed inset-0 z-0"
      aria-hidden
    >
      {engineReady ? (
        <Particles
          id="bg-particles"
          className="h-full w-full"
          options={options}
        />
      ) : (
        <div className="h-full w-full bg-[#f4f7ff]" />
      )}
    </div>
  );
}
