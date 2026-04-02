"use server";

import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

export async function getViolations() {
  return await prisma.violationLog.findMany({
    orderBy: { timestamp: 'desc' },
  });
}

export async function verifyViolation(id: string) {
  return await prisma.violationLog.update({
    where: { id },
    data: { verified: true },
  });
}

export async function getAccidents() {
  return await prisma.accidentLog.findMany({
    orderBy: { timestamp: 'desc' },
  });
}

export async function verifyAccident(id: string) {
  return await prisma.accidentLog.update({
    where: { id },
    data: { verified: true },
  });
}

export async function getChallans() {
  const data = await prisma.challanLog.findMany({
    orderBy: { metaCreatedAt: 'desc' },
  });

  return data.map((c) => ({
    id: c.id,
    ticket: {
      ticketNumber: c.ticketNumber,
      issueDateBS: c.issueDateBS,
      issueDateAD: c.issueDateAD,
      time: c.time,
    },
    authority: {
      country: c.authorityCountry,
      ministry: c.authorityMinistry,
      office: c.authorityOffice,
    },
    owner: {
      fullName: c.ownerFullName,
      age: c.ownerAge,
      address: c.ownerAddress,
      contactNumber: c.ownerContactNumber,
    },
    vehicle: {
      registrationNumber: c.vehicleRegNo,
      provinceCode: c.vehicleProvince,
      vehicleType: c.vehicleType,
      model: c.vehicleModel,
      color: c.vehicleColor,
    },
    license: {
      licenseNumber: c.licenseNo,
      category: c.licenseCategory,
      expiryDate: c.licenseExpiry,
    },
    offense: {
      title: c.offenseTitle,
      sectionCode: c.offenseSection,
      description: c.offenseDescription,
      fineAmount: c.fineAmount,
      pointsDeducted: c.pointsDeducted,
    },
    location: {
      place: c.locationPlace,
      district: c.locationDistrict,
      mapLink: c.locationMapLink,
      coordinates: {
        lat: c.locationLat,
        lng: c.locationLng,
      },
    },
    officer: {
      name: c.officerName,
      rank: c.officerRank,
      badgeNumber: c.officerBadge,
      signature: c.officerSignature,
    },
    payment: {
      status: c.paymentStatus,
      method: c.paymentMethod,
      transactionId: c.paymentTxId,
      paidAt: c.paymentPaidAt,
    },
    evidence: {
      images: c.evidenceImages,
      video: c.evidenceVideo,
      notes: c.evidenceNotes,
    },
    metadata: {
      createdAt: c.metaCreatedAt,
      updatedAt: c.metaUpdatedAt,
      source: c.metaSource,
    },
  }));
}
