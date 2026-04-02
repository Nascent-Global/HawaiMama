import { z } from 'zod';

export const ChallanSchema = z.object({
  id: z.string(),
  ticket: z.object({
    ticketNumber: z.string(),
    issueDateBS: z.string(),
    issueDateAD: z.string(),
    time: z.string(),
  }),
  authority: z.object({
    country: z.string(),
    ministry: z.string(),
    office: z.string(),
  }),
  owner: z.object({
    fullName: z.string(),
    age: z.number(),
    address: z.string(),
    contactNumber: z.string(),
  }),
  vehicle: z.object({
    registrationNumber: z.string(),
    provinceCode: z.string(),
    vehicleType: z.string(),
    model: z.string(),
    color: z.string(),
  }),
  license: z.object({
    licenseNumber: z.string(),
    category: z.string(),
    expiryDate: z.string(),
  }),
  offense: z.object({
    title: z.string(),
    sectionCode: z.string(),
    description: z.string(),
    fineAmount: z.number(),
    pointsDeducted: z.number(),
  }),
  location: z.object({
    place: z.string(),
    district: z.string(),
    mapLink: z.string(),
    coordinates: z.object({
      lat: z.number(),
      lng: z.number(),
    }),
  }),
  officer: z.object({
    name: z.string(),
    rank: z.string(),
    badgeNumber: z.string(),
    signature: z.string(),
  }),
  payment: z.object({
    status: z.enum(['pending', 'paid', 'overdue']),
    method: z.string(),
    transactionId: z.string(),
    paidAt: z.string().nullable(),
  }),
  evidence: z.object({
    images: z.array(z.string()),
    video: z.string(),
    notes: z.string(),
  }),
  metadata: z.object({
    createdAt: z.string(),
    updatedAt: z.string(),
    source: z.enum(['manual', 'ai-extracted']),
  }),
});

export type ChallanLog = z.infer<typeof ChallanSchema>;
