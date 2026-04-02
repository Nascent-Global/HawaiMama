from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from psycopg import Connection, connect
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from traffic_monitoring.auth import create_session_token, hash_session_token, verify_password


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


class AdminRepository:
    def __init__(self, database_url: str, *, project_root: Path) -> None:
        self.database_url = database_url
        self.project_root = project_root

    def initialize(
        self,
        cameras: dict[str, dict[str, object]],
        *,
        bootstrap_admins: list[dict[str, Any]] | None = None,
    ) -> None:
        with self._connect() as connection:
            self._create_tables(connection)
            self._sync_cameras(connection, cameras)
            self._ensure_admin_accounts(connection, bootstrap_admins or [])
            connection.commit()

    def sync_cameras(self, cameras: dict[str, dict[str, object]]) -> None:
        with self._connect() as connection:
            self._create_tables(connection)
            self._sync_cameras(connection, cameras)
            connection.commit()

    def list_admin_accounts(self) -> list[dict[str, Any]]:
        query = """
        SELECT id, username, full_name, role, is_active, all_locations, allowed_locations_json, permissions_json
        FROM admins
        ORDER BY role DESC, username ASC
        """
        with self._connect() as connection:
            rows = connection.execute(query).fetchall()
        return [self._serialize_admin(row) for row in rows]

    def create_admin_account(
        self,
        *,
        username: str,
        full_name: str,
        password_hash: str,
        role: str,
        is_active: bool,
        all_locations: bool,
        allowed_locations: list[str],
        permissions: dict[str, Any],
    ) -> dict[str, Any]:
        admin_id = str(uuid4())
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO admins (
                    id,
                    username,
                    full_name,
                    password_hash,
                    role,
                    is_active,
                    all_locations,
                    allowed_locations_json,
                    permissions_json,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    admin_id,
                    username,
                    full_name,
                    password_hash,
                    role,
                    is_active,
                    all_locations,
                    Jsonb(allowed_locations),
                    Jsonb(permissions),
                    now,
                    now,
                ),
            )
            connection.commit()
            row = connection.execute(
                """
                SELECT id, username, full_name, role, is_active, all_locations, allowed_locations_json, permissions_json
                FROM admins
                WHERE id = %s
                """,
                (admin_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Failed to create admin account")
        return self._serialize_admin(row)

    def update_admin_account(
        self,
        admin_id: str,
        *,
        full_name: str | None = None,
        password_hash: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
        all_locations: bool | None = None,
        allowed_locations: list[str] | None = None,
        permissions: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM admins
                WHERE id = %s
                """,
                (admin_id,),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE admins
                SET full_name = %s,
                    password_hash = %s,
                    role = %s,
                    is_active = %s,
                    all_locations = %s,
                    allowed_locations_json = %s,
                    permissions_json = %s,
                    updated_at = %s
                WHERE id = %s
                """,
                (
                    full_name or row["full_name"],
                    password_hash or row["password_hash"],
                    role or row["role"],
                    row["is_active"] if is_active is None else is_active,
                    row["all_locations"] if all_locations is None else all_locations,
                    Jsonb(
                        _coerce_json(row["allowed_locations_json"], [])
                        if allowed_locations is None
                        else allowed_locations
                    ),
                    Jsonb(
                        _coerce_json(row["permissions_json"], {})
                        if permissions is None
                        else permissions
                    ),
                    _utc_now(),
                    admin_id,
                ),
            )
            connection.commit()
        return self.get_admin_account(admin_id)

    def get_admin_account(self, admin_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, username, full_name, role, is_active, all_locations, allowed_locations_json, permissions_json
                FROM admins
                WHERE id = %s
                """,
                (admin_id,),
            ).fetchone()
        if row is None:
            return None
        return self._serialize_admin(row)

    def authenticate_admin(self, username: str, password: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM admins
                WHERE lower(username) = lower(%s)
                """,
                (username,),
            ).fetchone()
        if row is None or not row["is_active"]:
            return None
        if not verify_password(password, row["password_hash"]):
            return None
        return self._serialize_admin(row)

    def create_admin_session(self, admin_id: str, *, ttl_hours: int = 24) -> str:
        token = create_session_token()
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO admin_sessions (id, admin_id, token_hash, expires_at, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    str(uuid4()),
                    admin_id,
                    hash_session_token(token),
                    now + timedelta(hours=ttl_hours),
                    now,
                ),
            )
            connection.commit()
        return token

    def get_session_admin(self, token: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT a.id, a.username, a.full_name, a.role, a.is_active, a.all_locations, a.allowed_locations_json, a.permissions_json
                FROM admin_sessions s
                JOIN admins a ON a.id = s.admin_id
                WHERE s.token_hash = %s
                  AND s.expires_at > %s
                  AND a.is_active = TRUE
                """,
                (hash_session_token(token), _utc_now()),
            ).fetchone()
        if row is None:
            return None
        return self._serialize_admin(row)

    def revoke_session(self, token: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM admin_sessions WHERE token_hash = %s",
                (hash_session_token(token),),
            )
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
                    "processed_video_url": self._processed_video_url(str(row["camera_id"])),
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
                "processedVideoUrl": camera.get("processed_video_url"),
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
                "processed_video_url": self._processed_video_url(str(row["camera_id"])),
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
            CREATE TABLE IF NOT EXISTS admins (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                all_locations BOOLEAN NOT NULL DEFAULT FALSE,
                allowed_locations_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                permissions_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_sessions (
                id TEXT PRIMARY KEY,
                admin_id TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL
            )
            """
        )
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
            "CREATE INDEX IF NOT EXISTS admin_sessions_expires_at_idx ON admin_sessions (expires_at)"
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
                    location = EXCLUDED.location,
                    status = EXCLUDED.status,
                    system_mode = EXCLUDED.system_mode,
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

    def _ensure_admin_accounts(
        self,
        connection: Connection[Any],
        accounts: list[dict[str, Any]],
    ) -> None:
        now = _utc_now()
        for account in accounts:
            row = connection.execute(
                """
                SELECT id
                FROM admins
                WHERE lower(username) = lower(%s)
                """,
                (account["username"],),
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO admins (
                        id,
                        username,
                        full_name,
                        password_hash,
                        role,
                        is_active,
                        all_locations,
                        allowed_locations_json,
                        permissions_json,
                        created_at,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(uuid4()),
                        account["username"],
                        account["full_name"],
                        account["password_hash"],
                        account["role"],
                        bool(account.get("is_active", True)),
                        bool(account.get("all_locations", False)),
                        Jsonb(account.get("allowed_locations", [])),
                        Jsonb(account.get("permissions", {})),
                        now,
                        now,
                    ),
                )
                continue
            connection.execute(
                """
                UPDATE admins
                SET full_name = %s,
                    password_hash = %s,
                    role = %s,
                    is_active = %s,
                    all_locations = %s,
                    allowed_locations_json = %s,
                    permissions_json = %s,
                    updated_at = %s
                WHERE lower(username) = lower(%s)
                """,
                (
                    account["full_name"],
                    account["password_hash"],
                    account["role"],
                    bool(account.get("is_active", True)),
                    bool(account.get("all_locations", False)),
                    Jsonb(account.get("allowed_locations", [])),
                    Jsonb(account.get("permissions", {})),
                    now,
                    account["username"],
                ),
            )

    def _serialize_admin(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "username": row["username"],
            "full_name": row["full_name"],
            "role": row["role"],
            "is_active": bool(row["is_active"]),
            "all_locations": bool(row["all_locations"]),
            "allowed_locations": list(_coerce_json(row["allowed_locations_json"], [])),
            "permissions": dict(_coerce_json(row["permissions_json"], {})),
        }

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
        violation_code = str(violation.get("violationCode", "traffic_code"))
        offense_policy = {
            "no_helmet": {
                "title": "Not wearing a helmet or seatbelt",
                "fine_amount": 1000,
                "points_deducted": 1,
                "notes": "Mapped to Nepal Traffic Police safety equipment fine schedule.",
            },
            "wrong_lane": {
                "title": "Lane Discipline Violation",
                "fine_amount": 1500,
                "points_deducted": 2,
                "notes": "Mapped to Nepal Traffic Police lane discipline fine schedule.",
            },
            "overspeed": {
                "title": "Overspeeding",
                "fine_amount": 1500,
                "points_deducted": 3,
                "notes": (
                    "Mapped to the base Nepal Traffic Police overspeed fine because "
                    "severity bands are not yet configured in the backend."
                ),
            },
        }.get(
            violation_code,
            {
                "title": str(violation.get("title", "Traffic Violation")),
                "fine_amount": 0,
                "points_deducted": 0,
                "notes": (
                    "No Nepal Traffic Police fine rule is mapped yet for this violation code "
                    "in the current backend policy table."
                ),
            },
        )
        offense_title = str(offense_policy["title"])
        issue_date_ad = str(violation.get("timestamp", created_at))[:10]
        issue_date_bs = issue_date_ad
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
                "fullName": str(violation.get("ownerName") or violation.get("driverName", "Unknown Driver")),
                "age": int(violation.get("age", 0) or 0),
                "address": str(violation.get("ownerAddress") or violation.get("tempAddress", "Unknown Address")),
                "contactNumber": str(violation.get("ownerContactNumber", "9800000000")),
            },
            "vehicle": {
                "registrationNumber": str(violation.get("licensePlate", "UNKNOWN")),
                "provinceCode": "Gandaki",
                "vehicleType": str(violation.get("vehicleType", "vehicle")),
                "model": "Pending verification",
                "color": str(violation.get("vehicleColor", "Unknown")),
            },
            "license": {
                "licenseNumber": "Pending verification",
                "category": "Unknown",
                "expiryDate": "Unknown",
            },
            "offense": {
                "title": offense_title,
                "sectionCode": violation_code,
                "description": str(violation.get("description", "")),
                "fineAmount": int(offense_policy["fine_amount"]),
                "pointsDeducted": int(offense_policy["points_deducted"]),
            },
            "location": {
                "place": str(
                    violation.get("cameraLocation")
                    or violation.get("tempAddress")
                    or "Unknown Location"
                ),
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
                "notes": str(offense_policy["notes"]),
            },
            "metadata": {
                "createdAt": created_at,
                "updatedAt": created_at,
                "source": "ai-extracted",
                "isMockData": bool(violation.get("isMockData", True)),
            },
            "violationId": violation.get("id"),
        }

    def _source_video_url(self, source: str) -> str:
        path = Path(source)
        if path.parent.name == "surveillance":
            return f"/surveillance-media/{path.name}"
        return f"/inputs/{path.name}"

    def _processed_video_url(self, camera_id: str) -> str | None:
        candidate = self.project_root / "surveillance" / "output" / f"{camera_id}.mp4"
        if candidate.exists():
            return f"/surveillance-output/{camera_id}.mp4"
        return None
