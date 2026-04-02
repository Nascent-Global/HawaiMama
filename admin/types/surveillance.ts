/** Live surveillance feed card (CCTV → dashboard). */
export type SurveillanceFeed = {
  id: string;
  stream_video: string;
  /** Optional poster while video loads (from `public/`, e.g. `/images/…`). */
  poster?: string;
  /** Optional downloadable/reference video for the same camera. */
  videoUrl?: string;
  address: string;
  /** Map link or deep link string, e.g. maps://… or https://maps.google.com/… */
  location: string;
};
