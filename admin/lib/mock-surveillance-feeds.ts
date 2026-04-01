import type { SurveillanceFeed } from "@/types/surveillance";

/** Mock streams and posters from `admin/public/videos` and `admin/public/images`. */
export const mockSurveillanceFeeds: SurveillanceFeed[] = [
  {
    id: "cam-sirjana-01",
    stream_video: "/videos/bikes-moving-static-shot.mp4",
    poster: "/images/sirjana-chowk.jpg",
    address: "Sirjana Chowk, Pokhara",
    location: "maps://pkr-sirjana-01",
  },
  {
    id: "cam-fewa-02",
    stream_video: "/videos/road-ahead-drone-motion.mp4",
    poster: "/images/pokhara-fewa-lake.jpg",
    address: "Lakeside — Fewa corridor",
    location: "https://maps.google.com/?q=Phewa+Lake+Pokhara",
  },
  {
    id: "cam-license-03",
    stream_video: "/videos/tudikhel-road-video.mp4",
    poster: "/images/license-checking.jpg",
    address: "Prithvi Marg checkpoint",
    location: "maps://pkr-prithvi-9921",
  },
  {
    id: "cam-machhapuchhre-04",
    stream_video: "/videos/time-lapse-with-machhapuchhre.mp4",
    poster: "/images/wave-from%20mitighar.jpg",
    address: "Mitighar approach",
    location: "https://maps.app.goo.gl/example",
  },
  {
    id: "cam-vertical-05",
    stream_video: "/videos/time-lapse-vertical.mp4",
    poster: "/images/dummy-police-holding-board.jpg",
    address: "Baglung Highway entry",
    location: "maps://baglung-hwy-44a",
  },
  {
    id: "cam-board-06",
    stream_video: "/videos/bikes-moving-static-shot.mp4",
    poster: "/images/alcohol-test.jpg",
    address: "New Road — traffic cell",
    location: "maps://newrd-7788",
  },
];
