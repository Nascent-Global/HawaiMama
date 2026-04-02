import { z } from "zod";

/** Live surveillance feed card (CCTV -> dashboard). */
export const SurveillanceFeedSchema = z.object({
  id: z.string(),
  stream_video: z.string(),
  poster: z.string().nullable().optional(),
  videoUrl: z.string().optional(),
  processedVideoUrl: z.string().nullable().optional(),
  address: z.string(),
  location: z.string(),
});

export type SurveillanceFeed = z.infer<typeof SurveillanceFeedSchema>;
