import { z } from "zod";

/** Live surveillance feed card (CCTV -> dashboard). */
export const SurveillanceFeedSchema = z.object({
  id: z.string(),
  stream_video: z.string(),
  poster: z.string().nullable().optional(),
  videoUrl: z.string().optional(),
  previewVideoUrl: z.string().nullable().optional(),
  processedVideoUrl: z.string().nullable().optional(),
  address: z.string(),
  location: z.string(),
  locationLink: z.string().nullable().optional(),
});

export type SurveillanceFeed = z.infer<typeof SurveillanceFeedSchema>;
