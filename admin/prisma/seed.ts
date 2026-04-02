import { PrismaClient } from '@prisma/client';
import violationData from '../db/mock-violations.json';
import accidentData from '../db/mock-accidents.json';
import challanData from '../db/mock-challans.json';

const prisma = new PrismaClient();

async function main() {
  console.log('Start seeding...');

  await prisma.violationLog.deleteMany();
  for (const v of violationData) {
    await prisma.violationLog.create({
      data: {
        id: v.id,
        title: v.title,
        driverName: v.driverName,
        age: v.age,
        dob: new Date(v.dob),
        bloodGroup: v.bloodGroup,
        licensePlate: v.licensePlate,
        tempAddress: v.tempAddress,
        permAddress: v.permAddress,
        timestamp: new Date(v.timestamp),
        locationLink: v.locationLink,
        screenshot1Url: v.screenshot1Url,
        screenshot2Url: v.screenshot2Url,
        screenshot3Url: v.screenshot3Url,
        videoUrl: v.videoUrl,
        description: v.description,
        verified: v.verified,
      },
    });
  }
  console.log(`Seeded ${violationData.length} violations`);

  await prisma.accidentLog.deleteMany();
  for (const a of accidentData) {
    await prisma.accidentLog.create({
      data: {
        id: a.id,
        title: a.title,
        driverName: a.driverName,
        age: a.age,
        dob: new Date(a.dob),
        bloodGroup: a.bloodGroup,
        licensePlate: a.licensePlate,
        tempAddress: a.tempAddress,
        permAddress: a.permAddress,
        timestamp: new Date(a.timestamp),
        locationLink: a.locationLink,
        screenshot1Url: a.screenshot1Url,
        screenshot2Url: a.screenshot2Url,
        screenshot3Url: a.screenshot3Url,
        videoUrl: a.videoUrl,
        description: a.description,
        verified: a.verified,
      },
    });
  }
  console.log(`Seeded ${accidentData.length} accidents`);

  await prisma.challanLog.deleteMany();
  for (const c of challanData) {
    await prisma.challanLog.create({
      data: {
        id: c.id,
        ticketNumber: c.ticket.ticketNumber,
        issueDateBS: c.ticket.issueDateBS,
        issueDateAD: c.ticket.issueDateAD,
        time: c.ticket.time,
        authorityCountry: c.authority.country,
        authorityMinistry: c.authority.ministry,
        authorityOffice: c.authority.office,
        ownerFullName: c.owner.fullName,
        ownerAge: c.owner.age,
        ownerAddress: c.owner.address,
        ownerContactNumber: c.owner.contactNumber,
        vehicleRegNo: c.vehicle.registrationNumber,
        vehicleProvince: c.vehicle.provinceCode,
        vehicleType: c.vehicle.vehicleType,
        vehicleModel: c.vehicle.model,
        vehicleColor: c.vehicle.color,
        licenseNo: c.license.licenseNumber,
        licenseCategory: c.license.category,
        licenseExpiry: c.license.expiryDate,
        offenseTitle: c.offense.title,
        offenseSection: c.offense.sectionCode,
        offenseDescription: c.offense.description,
        fineAmount: c.offense.fineAmount,
        pointsDeducted: c.offense.pointsDeducted,
        locationPlace: c.location.place,
        locationDistrict: c.location.district,
        locationMapLink: c.location.mapLink,
        locationLat: c.location.coordinates.lat,
        locationLng: c.location.coordinates.lng,
        officerName: c.officer.name,
        officerRank: c.officer.rank,
        officerBadge: c.officer.badgeNumber,
        officerSignature: c.officer.signature,
        paymentStatus: c.payment.status,
        paymentMethod: c.payment.method,
        paymentTxId: c.payment.transactionId,
        paymentPaidAt: c.payment.paidAt,
        evidenceImages: c.evidence.images,
        evidenceVideo: c.evidence.video,
        evidenceNotes: c.evidence.notes,
        metaCreatedAt: c.metadata.createdAt,
        metaUpdatedAt: c.metadata.updatedAt,
        metaSource: c.metadata.source,
      },
    });
  }
  console.log(`Seeded ${challanData.length} challans`);

  console.log('Seeding finished.');
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
