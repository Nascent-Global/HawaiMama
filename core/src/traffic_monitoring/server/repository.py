from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from psycopg import Connection, connect
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


def default_database_url() -> str:
    return os.environ.get(
        "TRAFFIC_MONITORING_DATABASE_URL",
        os.environ.get(
            "HAWAIMAMA_DATABASE_URL",
            "postgresql://hawaimama:hawaimama_dev@localhost:5433/hawaimama",
        ),
    )


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _utc_now_iso() -> str:
    return _utc_now().isoformat().replace("+00:00", "Z")


def _coerce_json(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return value


def _coerce_timestamp(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _normalize_demo_media(path: str | None, *, fallback: str) -> str:
    if not path:
        return fallback
    if path.startswith("/images/violation") or path.startswith("/videos/violation"):
        return fallback
    return path


@dataclass(frozen=True, slots=True)
class SeedPayloads:
    violations: list[dict[str, object]]
    accidents: list[dict[str, object]]
    challans: list[dict[str, object]]


class AdminRepository:
    def __init__(self, database_url: str, *, project_root: Path) -> None:
        self.database_url = database_url
        self.project_root = project_root

    def initialize(
        self,
        cameras: dict[str, dict[str, object]],
        seed_payloads: SeedPayloads,
    ) -> None:
        with self._connect() as connection:
            self._create_tables(connection)
            self._sync_cameras(connection, cameras)
            self._seed_demo_data(connection, seed_payloads)
            connection.commit()

    def sync_cameras(self, cameras: dict[str, dict[str, object]]) -> None:
        with self._connect() as connection:
            self._create_tables(connection)
            self._sync_cameras(connection, cameras)
            connection.commit()

    def list_cameras(self) -> list[dict[str, Any]]:
        query = """
        SELECT camera_id, location, status, system_mode, source, metadata_json
        FROM cameras
        WHERE status <> 'offline'
        ORDER BY camera_id
        """
        with self._connect() as connection:
            rows = connection.execute(query).fetchall()
        payload: list[dict[str, Any]] = []
        for row in rows:
            source = str(row["source"])
            location = str(row["location"])
            payload.append(
                {
                    "id": row["camera_id"],
                    "file_name": Path(source).name,
                    "location": location,
                    "status": row["status"],
                    "system_mode": row["system_mode"],
                    "mode_label": (
                        "Traffic light mode"
                        if row["system_mode"] == "traffic_management_mode"
                        else "Enforcement mode"
                    ),
                    "source": source,
                    "stream_url": f"/camera/{row['camera_id']}/stream",
                    "video_url": self._source_video_url(source),
                    "address": location,
                    "location_link": f"https://maps.google.com/?q={location.replace(' ', '+')}",
                }
            )
        return payload

    def list_surveillance_feeds(self) -> list[dict[str, Any]]:
        return [
            {
                "id": camera["id"],
                "stream_video": camera["stream_url"],
                "poster": None,
                "address": camera["address"],
                "location": camera["location_link"],
                "videoUrl": camera["video_url"],
            }
            for camera in self.list_cameras()
        ]

    def update_camera_config(
        self,
        camera_id: str,
        *,
        system_mode: str | None = None,
        location: str | None = None,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT camera_id, location, status, system_mode, source, metadata_json
                FROM cameras
                WHERE camera_id = %s
                """,
                (camera_id,),
            ).fetchone()
            if row is None:
                return None

            next_location = location.strip() if location and location.strip() else row["location"]
            next_mode = system_mode or row["system_mode"]
            connection.execute(
                """
                UPDATE cameras
                SET location = %s,
                    system_mode = %s,
                    updated_at = %s
                WHERE camera_id = %s
                """,
                (next_location, next_mode, _utc_now(), camera_id),
            )
            connection.commit()
        for camera in self.list_cameras():
            if camera["id"] == camera_id:
                return camera
        return None

    def update_camera(
        self,
        camera_id: str,
        *,
        location: str | None = None,
        system_mode: str | None = None,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT camera_id, location, status, system_mode, source, metadata_json
                FROM cameras
                WHERE camera_id = %s
                """,
                (camera_id,),
            ).fetchone()
            if row is None:
                return None

            metadata = _coerce_json(row["metadata_json"], {})
            next_location = location.strip() if location is not None else str(row["location"])
            next_system_mode = system_mode or str(row["system_mode"])
            updated_at = _utc_now()
            connection.execute(
                """
                UPDATE cameras
                SET location = %s,
                    system_mode = %s,
                    updated_at = %s
                WHERE camera_id = %s
                """,
                (next_location, next_system_mode, updated_at, camera_id),
            )
            connection.commit()
            return {
                "id": row["camera_id"],
                "file_name": Path(str(row["source"])).name,
                "location": next_location,
                "status": row["status"],
                "system_mode": next_system_mode,
                "mode_label": (
                    "Traffic light mode"
                    if next_system_mode == "traffic_management_mode"
                    else "Enforcement mode"
                ),
                "source": row["source"],
                "stream_url": f"/camera/{row['camera_id']}/stream",
                "video_url": self._source_video_url(str(row["source"])),
                "address": next_location,
                "location_link": metadata.get("location_link")
                or f"https://maps.google.com/?q={next_location.replace(' ', '+')}",
            }

    def list_violations(self) -> list[dict[str, Any]]:
        return self._list_payload_table("violations", order_by="event_time DESC, created_at DESC")

    def get_violation(self, violation_id: str) -> dict[str, Any] | None:
        return self._get_payload_row("violations", violation_id)

    def verify_violation(self, violation_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, payload_json, challan_id
                FROM violations
                WHERE id = %s
                """,
                (violation_id,),
            ).fetchone()
            if row is None:
                return None

            payload = _coerce_json(row["payload_json"], {})
            payload["verified"] = True
            payload["updatedAt"] = _utc_now_iso()

            challan_payload: dict[str, Any] | None = None
            challan_id = row["challan_id"]
            if challan_id:
                existing = connection.execute(
                    "SELECT payload_json FROM challans WHERE id = %s",
                    (challan_id,),
                ).fetchone()
                challan_payload = _coerce_json(existing["payload_json"], None) if existing else None
            else:
                challan_payload = self._build_challan_from_violation(payload)
                challan_id = challan_payload["id"]
                connection.execute(
                    """
                    INSERT INTO challans (id, violation_id, created_at, payload_json)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        challan_id,
                        violation_id,
                        _coerce_timestamp(challan_payload["metadata"]["createdAt"]),
                        Jsonb(challan_payload),
                    ),
                )

            connection.execute(
                """
                UPDATE violations
                SET verified = TRUE,
                    challan_id = %s,
                    updated_at = %s,
                    payload_json = %s
                WHERE id = %s
                """,
                (
                    challan_id,
                    _coerce_timestamp(payload["updatedAt"]),
                    Jsonb(payload),
                    violation_id,
                ),
            )
            connection.commit()
            return {"violation": payload, "challan": challan_payload}

    def list_accidents(self) -> list[dict[str, Any]]:
        return self._list_payload_table("accidents", order_by="event_time DESC, created_at DESC")

    def get_accident(self, accident_id: str) -> dict[str, Any] | None:
        return self._get_payload_row("accidents", accident_id)

    def verify_accident(self, accident_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM accidents
                WHERE id = %s
                """,
                (accident_id,),
            ).fetchone()
            if row is None:
                return None

            payload = _coerce_json(row["payload_json"], {})
            payload["verified"] = True
            payload["updatedAt"] = _utc_now_iso()
            connection.execute(
                """
                UPDATE accidents
                SET verified = TRUE,
                    updated_at = %s,
                    payload_json = %s
                WHERE id = %s
                """,
                (
                    _coerce_timestamp(payload["updatedAt"]),
                    Jsonb(payload),
                    accident_id,
                ),
            )
            connection.commit()
            return {"accident": payload}

    def list_challans(self) -> list[dict[str, Any]]:
        return self._list_payload_table("challans", order_by="created_at DESC")

    def get_challan(self, challan_id: str) -> dict[str, Any] | None:
        return self._get_payload_row("challans", challan_id)

    def ingest_violation_event(
        self,
        payload: dict[str, Any],
        *,
        source_event_key: str,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT payload_json
                FROM violations
                WHERE source_event_key = %s
                """,
                (source_event_key,),
            ).fetchone()
            if existing is not None:
                return _coerce_json(existing["payload_json"], {})

            connection.execute(
                """
                INSERT INTO violations (
                    id,
                    event_time,
                    verified,
                    source_event_key,
                    challan_id,
                    created_at,
                    updated_at,
                    payload_json
                )
                VALUES (%s, %s, FALSE, %s, NULL, %s, %s, %s)
                """,
                (
                    payload["id"],
                    _coerce_timestamp(payload["timestamp"]),
                    source_event_key,
                    _coerce_timestamp(payload["createdAt"]),
                    _coerce_timestamp(payload["updatedAt"]),
                    Jsonb(payload),
                ),
            )
            connection.commit()
            return payload

    def _connect(self) -> Connection[Any]:
        return connect(self.database_url, row_factory=dict_row)

    def _create_tables(self, connection: Connection[Any]) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS cameras (
                camera_id TEXT PRIMARY KEY,
                location TEXT NOT NULL,
                status TEXT NOT NULL,
                system_mode TEXT NOT NULL,
                source TEXT NOT NULL,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS violations (
                id TEXT PRIMARY KEY,
                event_time TIMESTAMPTZ NOT NULL,
                verified BOOLEAN NOT NULL DEFAULT FALSE,
                source_event_key TEXT UNIQUE,
                challan_id TEXT,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                payload_json JSONB NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS accidents (
                id TEXT PRIMARY KEY,
                event_time TIMESTAMPTZ NOT NULL,
                verified BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                payload_json JSONB NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS challans (
                id TEXT PRIMARY KEY,
                violation_id TEXT,
                created_at TIMESTAMPTZ NOT NULL,
                payload_json JSONB NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS violations_event_time_idx ON violations (event_time DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS accidents_event_time_idx ON accidents (event_time DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS challans_created_at_idx ON challans (created_at DESC)"
        )

    def _sync_cameras(
        self,
        connection: Connection[Any],
        cameras: dict[str, dict[str, object]],
    ) -> None:
        now = _utc_now()
        camera_ids = list(cameras)
        if camera_ids:
            placeholders = ", ".join(["%s"] * len(camera_ids))
            connection.execute(
                f"DELETE FROM cameras WHERE camera_id NOT IN ({placeholders})",
                tuple(camera_ids),
            )
        else:
            connection.execute("DELETE FROM cameras")
        for camera_id, camera in cameras.items():
            metadata = {
                "intersection_id": camera.get("intersection_id"),
                "lanes": camera.get("lanes", []),
                "location_link": camera.get("location_link"),
                "frame_skip": camera.get("frame_skip"),
                "resolution": camera.get("resolution"),
                "fps_limit": camera.get("fps_limit"),
            }
            connection.execute(
                """
                INSERT INTO cameras (
                    camera_id,
                    location,
                    status,
                    system_mode,
                    source,
                    metadata_json,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (camera_id) DO UPDATE SET
                    source = EXCLUDED.source,
                    metadata_json = EXCLUDED.metadata_json,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    camera_id,
                    str(camera.get("location", camera_id)),
                    str(camera.get("status", "online")),
                    str(camera.get("system_mode", "enforcement_mode")),
                    str(camera.get("source", "")),
                    Jsonb(metadata),
                    now,
                    now,
                ),
            )

    def _seed_demo_data(
        self,
        connection: Connection[Any],
        seed_payloads: SeedPayloads,
    ) -> None:
        if self._table_count(connection, "violations") == 0:
            for payload in seed_payloads.violations:
                seeded = self._normalize_seed_violation(payload)
                connection.execute(
                    """
                    INSERT INTO violations (
                        id,
                        event_time,
                        verified,
                        source_event_key,
                        challan_id,
                        created_at,
                        updated_at,
                        payload_json
                    )
                    VALUES (%s, %s, %s, NULL, NULL, %s, %s, %s)
                    """,
                    (
                        seeded["id"],
                        _coerce_timestamp(seeded["timestamp"]),
                        bool(seeded.get("verified", False)),
                        _coerce_timestamp(seeded["createdAt"]),
                        _coerce_timestamp(seeded["updatedAt"]),
                        Jsonb(seeded),
                    ),
                )

        if self._table_count(connection, "accidents") == 0:
            for payload in seed_payloads.accidents:
                seeded = self._normalize_seed_accident(payload)
                connection.execute(
                    """
                    INSERT INTO accidents (
                        id,
                        event_time,
                        verified,
                        created_at,
                        updated_at,
                        payload_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        seeded["id"],
                        _coerce_timestamp(seeded["timestamp"]),
                        bool(seeded.get("verified", False)),
                        _coerce_timestamp(seeded["createdAt"]),
                        _coerce_timestamp(seeded["updatedAt"]),
                        Jsonb(seeded),
                    ),
                )

        if self._table_count(connection, "challans") == 0:
            for payload in seed_payloads.challans:
                seeded = self._normalize_seed_challan(payload)
                connection.execute(
                    """
                    INSERT INTO challans (id, violation_id, created_at, payload_json)
                    VALUES (%s, NULL, %s, %s)
                    """,
                    (
                        seeded["id"],
                        _coerce_timestamp(seeded["metadata"]["createdAt"]),
                        Jsonb(seeded),
                    ),
                )

    def _normalize_seed_violation(self, payload: dict[str, Any]) -> dict[str, Any]:
        seeded = dict(payload)
        now = _utc_now_iso()
        seeded["cameraId"] = seeded.get("cameraId", "cam1")
        seeded["trackId"] = seeded.get("trackId", 0)
        seeded["vehicleType"] = seeded.get("vehicleType", "motorcycle")
        seeded["violationCode"] = seeded.get("violationCode", "no_helmet")
        seeded["screenshot1Url"] = _normalize_demo_media(
            str(seeded.get("screenshot1Url") or ""),
            fallback="/images/license-checking.jpg",
        )
        seeded["screenshot2Url"] = _normalize_demo_media(
            str(seeded.get("screenshot2Url") or ""),
            fallback="/images/alcohol-test.jpg",
        )
        seeded["screenshot3Url"] = _normalize_demo_media(
            str(seeded.get("screenshot3Url") or ""),
            fallback="/images/sirjana-chowk.jpg",
        )
        seeded["videoUrl"] = _normalize_demo_media(
            str(seeded.get("videoUrl") or ""),
            fallback="/videos/tudikhel-road-video.mp4",
        )
        seeded["createdAt"] = seeded.get("createdAt", seeded.get("timestamp", now))
        seeded["updatedAt"] = seeded.get("updatedAt", seeded["createdAt"])
        return seeded

    def _normalize_seed_accident(self, payload: dict[str, Any]) -> dict[str, Any]:
        seeded = dict(payload)
        now = _utc_now_iso()
        seeded["cameraId"] = seeded.get("cameraId", "cam2")
        seeded["trackId"] = seeded.get("trackId", 0)
        seeded["incidentType"] = seeded.get("incidentType", "collision")
        seeded["screenshot1Url"] = _normalize_demo_media(
            str(seeded.get("screenshot1Url") or ""),
            fallback="/images/pokhara-fewa-lake.jpg",
        )
        seeded["screenshot2Url"] = _normalize_demo_media(
            str(seeded.get("screenshot2Url") or ""),
            fallback="/images/dummy-police-holding-board.jpg",
        )
        seeded["screenshot3Url"] = _normalize_demo_media(
            str(seeded.get("screenshot3Url") or ""),
            fallback="/images/sirjana-chowk.jpg",
        )
        seeded["videoUrl"] = _normalize_demo_media(
            str(seeded.get("videoUrl") or ""),
            fallback="/videos/road-ahead-drone-motion.mp4",
        )
        seeded["createdAt"] = seeded.get("createdAt", seeded.get("timestamp", now))
        seeded["updatedAt"] = seeded.get("updatedAt", seeded["createdAt"])
        return seeded

    def _normalize_seed_challan(self, payload: dict[str, Any]) -> dict[str, Any]:
        seeded = dict(payload)
        evidence = dict(seeded.get("evidence", {}))
        images = [
            _normalize_demo_media(str(item), fallback="/images/license-checking.jpg")
            for item in evidence.get("images", [])
        ]
        evidence["images"] = images or ["/images/license-checking.jpg"]
        evidence["video"] = _normalize_demo_media(
            str(evidence.get("video") or ""),
            fallback="/videos/tudikhel-road-video.mp4",
        )
        seeded["evidence"] = evidence
        metadata = dict(seeded.get("metadata", {}))
        metadata["createdAt"] = metadata.get("createdAt", _utc_now_iso())
        metadata["updatedAt"] = metadata.get("updatedAt", metadata["createdAt"])
        seeded["metadata"] = metadata
        return seeded

    def _table_count(self, connection: Connection[Any], table_name: str) -> int:
        row = connection.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
        return int(row["count"]) if row else 0

    def _list_payload_table(self, table_name: str, *, order_by: str) -> list[dict[str, Any]]:
        query = f"SELECT payload_json FROM {table_name} ORDER BY {order_by}"
        with self._connect() as connection:
            rows = connection.execute(query).fetchall()
        return [_coerce_json(row["payload_json"], {}) for row in rows]

    def _get_payload_row(self, table_name: str, record_id: str) -> dict[str, Any] | None:
        query = f"SELECT payload_json FROM {table_name} WHERE id = %s"
        with self._connect() as connection:
            row = connection.execute(query, (record_id,)).fetchone()
        if row is None:
            return None
        return _coerce_json(row["payload_json"], {})

    def _build_challan_from_violation(self, violation: dict[str, Any]) -> dict[str, Any]:
        created_at = _utc_now_iso()
        challan_id = str(uuid4())
        ticket_number = f"HM-{challan_id[:8].upper()}"
        offense_title = str(violation.get("title", "Traffic Violation"))
        issue_date_ad = str(violation.get("timestamp", created_at))[:10]
        issue_date_bs = issue_date_ad
        fine_amount = 1500 if violation.get("violationCode") == "no_helmet" else 2500
        return {
            "id": challan_id,
            "ticket": {
                "ticketNumber": ticket_number,
                "issueDateBS": issue_date_bs,
                "issueDateAD": issue_date_ad,
                "time": str(violation.get("timestamp", created_at))[11:16] or "00:00",
            },
            "authority": {
                "country": "Nepal",
                "ministry": "Ministry of Home Affairs",
                "office": "Traffic Police Department",
            },
            "owner": {
                "fullName": str(violation.get("driverName", "Unknown Driver")),
                "age": int(violation.get("age", 0) or 0),
                "address": str(violation.get("tempAddress", "Unknown Address")),
                "contactNumber": "9800000000",
            },
            "vehicle": {
                "registrationNumber": str(violation.get("licensePlate", "UNKNOWN")),
                "provinceCode": "Gandaki",
                "vehicleType": str(violation.get("vehicleType", "vehicle")),
                "model": "Pending verification",
                "color": "Unknown",
            },
            "license": {
                "licenseNumber": "Pending verification",
                "category": "Unknown",
                "expiryDate": "Unknown",
            },
            "offense": {
                "title": offense_title,
                "sectionCode": str(violation.get("violationCode", "traffic_code")),
                "description": str(violation.get("description", "")),
                "fineAmount": fine_amount,
                "pointsDeducted": 2,
            },
            "location": {
                "place": str(violation.get("tempAddress", "Unknown Location")),
                "district": "Kaski",
                "mapLink": str(violation.get("locationLink", "")),
                "coordinates": {
                    "lat": 28.2096,
                    "lng": 83.9856,
                },
            },
            "officer": {
                "name": "HawaiMama Demo Officer",
                "rank": "Inspector",
                "badgeNumber": "HM-001",
                "signature": "HawaiMama",
            },
            "payment": {
                "status": "pending",
                "method": "cash",
                "transactionId": f"TX-{challan_id[:10].upper()}",
                "paidAt": None,
            },
            "evidence": {
                "images": [
                    value
                    for value in [
                        violation.get("screenshot1Url"),
                        violation.get("screenshot2Url"),
                        violation.get("screenshot3Url"),
                    ]
                    if value
                ],
                "video": str(violation.get("videoUrl", "")),
                "notes": "Generated from verified traffic violation event.",
            },
            "metadata": {
                "createdAt": created_at,
                "updatedAt": created_at,
                "source": "ai-extracted",
            },
            "violationId": violation.get("id"),
        }

    def _source_video_url(self, source: str) -> str:
        path = Path(source)
        if path.parent.name == "surveillance":
            return f"/surveillance-media/{path.name}"
        return f"/inputs/{path.name}"
