import { z } from 'zod';

export const ViolationLogSchema = z.object({
  id: z.string(),
  title: z.string(),
  driverName: z.string(),
  age: z.number(),
  dob: z.string(),
  bloodGroup: z.string(),
  licensePlate: z.string(),
  tempAddress: z.string(),
  permAddress: z.string(),
  timestamp: z.string(),
  locationLink: z.string(),
  screenshot1Url: z.string(),
  screenshot2Url: z.string(),
  screenshot3Url: z.string(),
  videoUrl: z.string(),
  description: z.string(),
  verified: z.boolean(),
});

export type ViolationLog = z.infer<typeof ViolationLogSchema>;
