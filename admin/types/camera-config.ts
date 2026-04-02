import { z } from "zod";

export const SurveillanceCameraConfigSchema = z.object({
  id: z.string(),
  file_name: z.string(),
  location: z.string(),
  status: z.string(),
  system_mode: z.enum(["enforcement_mode", "traffic_management_mode"]),
  source: z.string(),
  stream_url: z.string(),
  video_url: z.string(),
  address: z.string(),
  location_link: z.string(),
  mode_label: z.string().optional(),
});

export type SurveillanceCameraConfig = z.infer<typeof SurveillanceCameraConfigSchema>;
