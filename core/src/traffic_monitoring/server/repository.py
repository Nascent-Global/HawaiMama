from __future__ import annotations

import json
import os
import re
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


def _plate_prefix(value: str) -> str:
    parts = [part for part in re.split(r"[\s-]+", value.strip()) if part]
    return parts[0].upper() if parts else ""


def _camera_metadata_payload(camera: dict[str, object]) -> dict[str, Any]:
    return {
        "intersection_id": camera.get("intersection_id"),
        "lanes": camera.get("lanes", []),
        "location_link": camera.get("location_link"),
        "frame_skip": camera.get("frame_skip"),
        "resolution": camera.get("resolution"),
        "fps_limit": camera.get("fps_limit"),
        "ocr_enabled": camera.get("ocr_enabled"),
        "ocr_debug": camera.get("ocr_debug"),
        "roi_config_path": camera.get("roi_config_path"),
        "confidence_threshold": camera.get("confidence_threshold"),
        "plate_confidence_threshold": camera.get("plate_confidence_threshold"),
        "char_confidence_threshold": camera.get("char_confidence_threshold"),
        "helmet_confidence_threshold": camera.get("helmet_confidence_threshold"),
        "overspeed_threshold_kmh": camera.get("overspeed_threshold_kmh"),
        "line1_y": camera.get("line1_y"),
        "line2_y": camera.get("line2_y"),
        "line_distance_meters": camera.get("line_distance_meters"),
        "line_tolerance_pixels": camera.get("line_tolerance_pixels"),
        "helmet_stability_frames": camera.get("helmet_stability_frames"),
        "stop_speed_threshold_px": camera.get("stop_speed_threshold_px"),
        "stop_frames_threshold": camera.get("stop_frames_threshold"),
        "stop_line_distance_px": camera.get("stop_line_distance_px"),
        "min_green_time": camera.get("min_green_time"),
        "max_green_time": camera.get("max_green_time"),
        "yellow_time": camera.get("yellow_time"),
        "priority_queue_weight": camera.get("priority_queue_weight"),
        "priority_wait_weight": camera.get("priority_wait_weight"),
        "fairness_weight": camera.get("fairness_weight"),
        "max_priority_score": camera.get("max_priority_score"),
        "initial_active_lane": camera.get("initial_active_lane"),
    }


CAMERA_TYPED_METADATA_FIELDS: tuple[str, ...] = (
    "location_link",
    "frame_skip",
    "resolution",
    "fps_limit",
    "ocr_enabled",
    "ocr_debug",
    "intersection_id",
    "lanes",
    "roi_config_path",
    "confidence_threshold",
    "plate_confidence_threshold",
    "char_confidence_threshold",
    "helmet_confidence_threshold",
    "overspeed_threshold_kmh",
    "line1_y",
    "line2_y",
    "line_distance_meters",
    "line_tolerance_pixels",
    "helmet_stability_frames",
    "stop_speed_threshold_px",
    "stop_frames_threshold",
    "stop_line_distance_px",
    "min_green_time",
    "max_green_time",
    "yellow_time",
    "priority_queue_weight",
    "priority_wait_weight",
    "fairness_weight",
    "max_priority_score",
    "initial_active_lane",
)


def _camera_column_payload(camera: dict[str, object]) -> dict[str, Any]:
    payload = _camera_metadata_payload(camera)
    return {key: payload.get(key) for key in CAMERA_TYPED_METADATA_FIELDS}


def _split_camera_updates(metadata_updates: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    if not metadata_updates:
        return {}, {}
    typed = {key: value for key, value in metadata_updates.items() if key in CAMERA_TYPED_METADATA_FIELDS}
    extra = {key: value for key, value in metadata_updates.items() if key not in CAMERA_TYPED_METADATA_FIELDS}
    return typed, extra


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
        SELECT *
        FROM cameras
        WHERE status <> 'offline'
        ORDER BY camera_id
        """
        with self._connect() as connection:
            rows = connection.execute(query).fetchall()
        return [self._serialize_camera(row) for row in rows]

    def list_surveillance_feeds(self) -> list[dict[str, Any]]:
        return [
            {
                "id": camera["id"],
                "stream_video": camera["stream_url"],
                "poster": None,
                "address": camera["address"],
                "location": camera["location"],
                "locationLink": camera.get("location_link"),
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
        metadata_updates: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM cameras
                WHERE camera_id = %s
                """,
                (camera_id,),
            ).fetchone()
            if row is None:
                return None

            next_location = location.strip() if location and location.strip() else row["location"]
            next_mode = system_mode or row["system_mode"]
            typed_updates, metadata_only_updates = _split_camera_updates(metadata_updates)
            metadata = _coerce_json(row["metadata_json"], {})
            if metadata_only_updates:
                for key, value in metadata_only_updates.items():
                    metadata[key] = value
            connection.execute(
                """
                UPDATE cameras
                SET location = %s,
                    system_mode = %s,
                    location_link = %s,
                    frame_skip = %s,
                    resolution_json = %s,
                    fps_limit = %s,
                    ocr_enabled = %s,
                    ocr_debug = %s,
                    intersection_id = %s,
                    lanes_json = %s,
                    roi_config_path = %s,
                    confidence_threshold = %s,
                    plate_confidence_threshold = %s,
                    char_confidence_threshold = %s,
                    helmet_confidence_threshold = %s,
                    overspeed_threshold_kmh = %s,
                    line1_y = %s,
                    line2_y = %s,
                    line_distance_meters = %s,
                    line_tolerance_pixels = %s,
                    helmet_stability_frames = %s,
                    stop_speed_threshold_px = %s,
                    stop_frames_threshold = %s,
                    stop_line_distance_px = %s,
                    min_green_time = %s,
                    max_green_time = %s,
                    yellow_time = %s,
                    priority_queue_weight = %s,
                    priority_wait_weight = %s,
                    fairness_weight = %s,
                    max_priority_score = %s,
                    initial_active_lane = %s,
                    metadata_json = %s,
                    updated_at = %s
                WHERE camera_id = %s
                """,
                (
                    next_location,
                    next_mode,
                    typed_updates.get("location_link", row.get("location_link")),
                    typed_updates.get("frame_skip", row.get("frame_skip")),
                    Jsonb(typed_updates.get("resolution", _coerce_json(row.get("resolution_json"), None))),
                    typed_updates.get("fps_limit", row.get("fps_limit")),
                    typed_updates.get("ocr_enabled", row.get("ocr_enabled")),
                    typed_updates.get("ocr_debug", row.get("ocr_debug")),
                    typed_updates.get("intersection_id", row.get("intersection_id")),
                    Jsonb(typed_updates.get("lanes", _coerce_json(row.get("lanes_json"), []))),
                    typed_updates.get("roi_config_path", row.get("roi_config_path")),
                    typed_updates.get("confidence_threshold", row.get("confidence_threshold")),
                    typed_updates.get("plate_confidence_threshold", row.get("plate_confidence_threshold")),
                    typed_updates.get("char_confidence_threshold", row.get("char_confidence_threshold")),
                    typed_updates.get("helmet_confidence_threshold", row.get("helmet_confidence_threshold")),
                    typed_updates.get("overspeed_threshold_kmh", row.get("overspeed_threshold_kmh")),
                    typed_updates.get("line1_y", row.get("line1_y")),
                    typed_updates.get("line2_y", row.get("line2_y")),
                    typed_updates.get("line_distance_meters", row.get("line_distance_meters")),
                    typed_updates.get("line_tolerance_pixels", row.get("line_tolerance_pixels")),
                    typed_updates.get("helmet_stability_frames", row.get("helmet_stability_frames")),
                    typed_updates.get("stop_speed_threshold_px", row.get("stop_speed_threshold_px")),
                    typed_updates.get("stop_frames_threshold", row.get("stop_frames_threshold")),
                    typed_updates.get("stop_line_distance_px", row.get("stop_line_distance_px")),
                    typed_updates.get("min_green_time", row.get("min_green_time")),
                    typed_updates.get("max_green_time", row.get("max_green_time")),
                    typed_updates.get("yellow_time", row.get("yellow_time")),
                    typed_updates.get("priority_queue_weight", row.get("priority_queue_weight")),
                    typed_updates.get("priority_wait_weight", row.get("priority_wait_weight")),
                    typed_updates.get("fairness_weight", row.get("fairness_weight")),
                    typed_updates.get("max_priority_score", row.get("max_priority_score")),
                    typed_updates.get("initial_active_lane", row.get("initial_active_lane")),
                    Jsonb(metadata),
                    _utc_now(),
                    camera_id,
                ),
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
        metadata_updates: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM cameras
                WHERE camera_id = %s
                """,
                (camera_id,),
            ).fetchone()
            if row is None:
                return None

            typed_updates, metadata_only_updates = _split_camera_updates(metadata_updates)
            metadata = _coerce_json(row["metadata_json"], {})
            next_location = location.strip() if location is not None else str(row["location"])
            next_system_mode = system_mode or str(row["system_mode"])
            if metadata_only_updates:
                for key, value in metadata_only_updates.items():
                    metadata[key] = value
            updated_at = _utc_now()
            connection.execute(
                """
                UPDATE cameras
                SET location = %s,
                    system_mode = %s,
                    location_link = %s,
                    frame_skip = %s,
                    resolution_json = %s,
                    fps_limit = %s,
                    ocr_enabled = %s,
                    ocr_debug = %s,
                    intersection_id = %s,
                    lanes_json = %s,
                    roi_config_path = %s,
                    confidence_threshold = %s,
                    plate_confidence_threshold = %s,
                    char_confidence_threshold = %s,
                    helmet_confidence_threshold = %s,
                    overspeed_threshold_kmh = %s,
                    line1_y = %s,
                    line2_y = %s,
                    line_distance_meters = %s,
                    line_tolerance_pixels = %s,
                    helmet_stability_frames = %s,
                    stop_speed_threshold_px = %s,
                    stop_frames_threshold = %s,
                    stop_line_distance_px = %s,
                    min_green_time = %s,
                    max_green_time = %s,
                    yellow_time = %s,
                    priority_queue_weight = %s,
                    priority_wait_weight = %s,
                    fairness_weight = %s,
                    max_priority_score = %s,
                    initial_active_lane = %s,
                    metadata_json = %s,
                    updated_at = %s
                WHERE camera_id = %s
                """,
                (
                    next_location,
                    next_system_mode,
                    typed_updates.get("location_link", row.get("location_link")),
                    typed_updates.get("frame_skip", row.get("frame_skip")),
                    Jsonb(typed_updates.get("resolution", _coerce_json(row.get("resolution_json"), None))),
                    typed_updates.get("fps_limit", row.get("fps_limit")),
                    typed_updates.get("ocr_enabled", row.get("ocr_enabled")),
                    typed_updates.get("ocr_debug", row.get("ocr_debug")),
                    typed_updates.get("intersection_id", row.get("intersection_id")),
                    Jsonb(typed_updates.get("lanes", _coerce_json(row.get("lanes_json"), []))),
                    typed_updates.get("roi_config_path", row.get("roi_config_path")),
                    typed_updates.get("confidence_threshold", row.get("confidence_threshold")),
                    typed_updates.get("plate_confidence_threshold", row.get("plate_confidence_threshold")),
                    typed_updates.get("char_confidence_threshold", row.get("char_confidence_threshold")),
                    typed_updates.get("helmet_confidence_threshold", row.get("helmet_confidence_threshold")),
                    typed_updates.get("overspeed_threshold_kmh", row.get("overspeed_threshold_kmh")),
                    typed_updates.get("line1_y", row.get("line1_y")),
                    typed_updates.get("line2_y", row.get("line2_y")),
                    typed_updates.get("line_distance_meters", row.get("line_distance_meters")),
                    typed_updates.get("line_tolerance_pixels", row.get("line_tolerance_pixels")),
                    typed_updates.get("helmet_stability_frames", row.get("helmet_stability_frames")),
                    typed_updates.get("stop_speed_threshold_px", row.get("stop_speed_threshold_px")),
                    typed_updates.get("stop_frames_threshold", row.get("stop_frames_threshold")),
                    typed_updates.get("stop_line_distance_px", row.get("stop_line_distance_px")),
                    typed_updates.get("min_green_time", row.get("min_green_time")),
                    typed_updates.get("max_green_time", row.get("max_green_time")),
                    typed_updates.get("yellow_time", row.get("yellow_time")),
                    typed_updates.get("priority_queue_weight", row.get("priority_queue_weight")),
                    typed_updates.get("priority_wait_weight", row.get("priority_wait_weight")),
                    typed_updates.get("fairness_weight", row.get("fairness_weight")),
                    typed_updates.get("max_priority_score", row.get("max_priority_score")),
                    typed_updates.get("initial_active_lane", row.get("initial_active_lane")),
                    Jsonb(metadata),
                    updated_at,
                    camera_id,
                ),
            )
            connection.commit()
            next_row = dict(row)
            next_row["location"] = next_location
            next_row["system_mode"] = next_system_mode
            next_row["metadata_json"] = metadata
            for key, value in typed_updates.items():
                if key == "resolution":
                    next_row["resolution_json"] = value
                elif key == "lanes":
                    next_row["lanes_json"] = value
                else:
                    next_row[key] = value
            return self._serialize_camera(next_row)

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

    def ingest_accident_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT payload_json
                FROM accidents
                WHERE id = %s
                """,
                (payload["id"],),
            ).fetchone()
            if existing is not None:
                return _coerce_json(existing["payload_json"], {})

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
                VALUES (%s, %s, FALSE, %s, %s, %s)
                """,
                (
                    payload["id"],
                    _coerce_timestamp(payload["timestamp"]),
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
                location_link TEXT,
                frame_skip INTEGER,
                resolution_json JSONB,
                fps_limit DOUBLE PRECISION,
                ocr_enabled BOOLEAN,
                ocr_debug BOOLEAN,
                intersection_id TEXT,
                lanes_json JSONB,
                roi_config_path TEXT,
                confidence_threshold DOUBLE PRECISION,
                plate_confidence_threshold DOUBLE PRECISION,
                char_confidence_threshold DOUBLE PRECISION,
                helmet_confidence_threshold DOUBLE PRECISION,
                overspeed_threshold_kmh DOUBLE PRECISION,
                line1_y DOUBLE PRECISION,
                line2_y DOUBLE PRECISION,
                line_distance_meters DOUBLE PRECISION,
                line_tolerance_pixels INTEGER,
                helmet_stability_frames INTEGER,
                stop_speed_threshold_px DOUBLE PRECISION,
                stop_frames_threshold INTEGER,
                stop_line_distance_px DOUBLE PRECISION,
                min_green_time DOUBLE PRECISION,
                max_green_time DOUBLE PRECISION,
                yellow_time DOUBLE PRECISION,
                priority_queue_weight DOUBLE PRECISION,
                priority_wait_weight DOUBLE PRECISION,
                fairness_weight DOUBLE PRECISION,
                max_priority_score DOUBLE PRECISION,
                initial_active_lane TEXT,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """
        )
        self._ensure_camera_columns(connection)
        self._backfill_camera_columns_from_metadata(connection)
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
            existing = connection.execute(
                """
                SELECT *
                FROM cameras
                WHERE camera_id = %s
                """,
                (camera_id,),
            ).fetchone()
            metadata = _coerce_json(existing["metadata_json"], {}) if existing is not None else {}
            typed_columns = _camera_column_payload(camera)
            merged_columns = {
                key: value
                for key, value in typed_columns.items()
                if value is not None and value != []
            }
            connection.execute(
                """
                INSERT INTO cameras (
                    camera_id,
                    location,
                    status,
                    system_mode,
                    source,
                    location_link,
                    frame_skip,
                    resolution_json,
                    fps_limit,
                    ocr_enabled,
                    ocr_debug,
                    intersection_id,
                    lanes_json,
                    roi_config_path,
                    confidence_threshold,
                    plate_confidence_threshold,
                    char_confidence_threshold,
                    helmet_confidence_threshold,
                    overspeed_threshold_kmh,
                    line1_y,
                    line2_y,
                    line_distance_meters,
                    line_tolerance_pixels,
                    helmet_stability_frames,
                    stop_speed_threshold_px,
                    stop_frames_threshold,
                    stop_line_distance_px,
                    min_green_time,
                    max_green_time,
                    yellow_time,
                    priority_queue_weight,
                    priority_wait_weight,
                    fairness_weight,
                    max_priority_score,
                    initial_active_lane,
                    metadata_json,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (camera_id) DO UPDATE SET
                    source = EXCLUDED.source,
                    location = EXCLUDED.location,
                    status = EXCLUDED.status,
                    system_mode = EXCLUDED.system_mode,
                    location_link = COALESCE(EXCLUDED.location_link, cameras.location_link),
                    frame_skip = COALESCE(EXCLUDED.frame_skip, cameras.frame_skip),
                    resolution_json = COALESCE(EXCLUDED.resolution_json, cameras.resolution_json),
                    fps_limit = COALESCE(EXCLUDED.fps_limit, cameras.fps_limit),
                    ocr_enabled = COALESCE(EXCLUDED.ocr_enabled, cameras.ocr_enabled),
                    ocr_debug = COALESCE(EXCLUDED.ocr_debug, cameras.ocr_debug),
                    intersection_id = COALESCE(EXCLUDED.intersection_id, cameras.intersection_id),
                    lanes_json = COALESCE(EXCLUDED.lanes_json, cameras.lanes_json),
                    roi_config_path = COALESCE(EXCLUDED.roi_config_path, cameras.roi_config_path),
                    confidence_threshold = COALESCE(EXCLUDED.confidence_threshold, cameras.confidence_threshold),
                    plate_confidence_threshold = COALESCE(EXCLUDED.plate_confidence_threshold, cameras.plate_confidence_threshold),
                    char_confidence_threshold = COALESCE(EXCLUDED.char_confidence_threshold, cameras.char_confidence_threshold),
                    helmet_confidence_threshold = COALESCE(EXCLUDED.helmet_confidence_threshold, cameras.helmet_confidence_threshold),
                    overspeed_threshold_kmh = COALESCE(EXCLUDED.overspeed_threshold_kmh, cameras.overspeed_threshold_kmh),
                    line1_y = COALESCE(EXCLUDED.line1_y, cameras.line1_y),
                    line2_y = COALESCE(EXCLUDED.line2_y, cameras.line2_y),
                    line_distance_meters = COALESCE(EXCLUDED.line_distance_meters, cameras.line_distance_meters),
                    line_tolerance_pixels = COALESCE(EXCLUDED.line_tolerance_pixels, cameras.line_tolerance_pixels),
                    helmet_stability_frames = COALESCE(EXCLUDED.helmet_stability_frames, cameras.helmet_stability_frames),
                    stop_speed_threshold_px = COALESCE(EXCLUDED.stop_speed_threshold_px, cameras.stop_speed_threshold_px),
                    stop_frames_threshold = COALESCE(EXCLUDED.stop_frames_threshold, cameras.stop_frames_threshold),
                    stop_line_distance_px = COALESCE(EXCLUDED.stop_line_distance_px, cameras.stop_line_distance_px),
                    min_green_time = COALESCE(EXCLUDED.min_green_time, cameras.min_green_time),
                    max_green_time = COALESCE(EXCLUDED.max_green_time, cameras.max_green_time),
                    yellow_time = COALESCE(EXCLUDED.yellow_time, cameras.yellow_time),
                    priority_queue_weight = COALESCE(EXCLUDED.priority_queue_weight, cameras.priority_queue_weight),
                    priority_wait_weight = COALESCE(EXCLUDED.priority_wait_weight, cameras.priority_wait_weight),
                    fairness_weight = COALESCE(EXCLUDED.fairness_weight, cameras.fairness_weight),
                    max_priority_score = COALESCE(EXCLUDED.max_priority_score, cameras.max_priority_score),
                    initial_active_lane = COALESCE(EXCLUDED.initial_active_lane, cameras.initial_active_lane),
                    metadata_json = cameras.metadata_json,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    camera_id,
                    str(camera.get("location", camera_id)),
                    str(camera.get("status", "online")),
                    str(camera.get("system_mode", "enforcement_mode")),
                    str(camera.get("source", "")),
                    merged_columns.get("location_link"),
                    merged_columns.get("frame_skip"),
                    Jsonb(merged_columns.get("resolution")),
                    merged_columns.get("fps_limit"),
                    merged_columns.get("ocr_enabled"),
                    merged_columns.get("ocr_debug"),
                    merged_columns.get("intersection_id"),
                    Jsonb(merged_columns.get("lanes")),
                    merged_columns.get("roi_config_path"),
                    merged_columns.get("confidence_threshold"),
                    merged_columns.get("plate_confidence_threshold"),
                    merged_columns.get("char_confidence_threshold"),
                    merged_columns.get("helmet_confidence_threshold"),
                    merged_columns.get("overspeed_threshold_kmh"),
                    merged_columns.get("line1_y"),
                    merged_columns.get("line2_y"),
                    merged_columns.get("line_distance_meters"),
                    merged_columns.get("line_tolerance_pixels"),
                    merged_columns.get("helmet_stability_frames"),
                    merged_columns.get("stop_speed_threshold_px"),
                    merged_columns.get("stop_frames_threshold"),
                    merged_columns.get("stop_line_distance_px"),
                    merged_columns.get("min_green_time"),
                    merged_columns.get("max_green_time"),
                    merged_columns.get("yellow_time"),
                    merged_columns.get("priority_queue_weight"),
                    merged_columns.get("priority_wait_weight"),
                    merged_columns.get("fairness_weight"),
                    merged_columns.get("max_priority_score"),
                    merged_columns.get("initial_active_lane"),
                    Jsonb(metadata),
                    now,
                    now,
                ),
            )

    def _serialize_camera(self, row: dict[str, Any]) -> dict[str, Any]:
        source = str(row["source"])
        location = str(row["location"])
        metadata = _coerce_json(row["metadata_json"], {})
        lanes = _coerce_json(row.get("lanes_json"), metadata.get("lanes", []))
        resolution = _coerce_json(row.get("resolution_json"), metadata.get("resolution"))
        return {
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
            "location_link": row.get("location_link", metadata.get("location_link")),
            "frame_skip": row.get("frame_skip", metadata.get("frame_skip")),
            "resolution": resolution,
            "fps_limit": row.get("fps_limit", metadata.get("fps_limit")),
            "ocr_enabled": row.get("ocr_enabled", metadata.get("ocr_enabled")),
            "ocr_debug": row.get("ocr_debug", metadata.get("ocr_debug")),
            "intersection_id": row.get("intersection_id", metadata.get("intersection_id")),
            "lanes": list(lanes) if isinstance(lanes, list) else [],
            "roi_config_path": row.get("roi_config_path", metadata.get("roi_config_path")),
            "confidence_threshold": row.get("confidence_threshold", metadata.get("confidence_threshold")),
            "plate_confidence_threshold": row.get("plate_confidence_threshold", metadata.get("plate_confidence_threshold")),
            "char_confidence_threshold": row.get("char_confidence_threshold", metadata.get("char_confidence_threshold")),
            "helmet_confidence_threshold": row.get("helmet_confidence_threshold", metadata.get("helmet_confidence_threshold")),
            "overspeed_threshold_kmh": row.get("overspeed_threshold_kmh", metadata.get("overspeed_threshold_kmh")),
            "line1_y": row.get("line1_y", metadata.get("line1_y")),
            "line2_y": row.get("line2_y", metadata.get("line2_y")),
            "line_distance_meters": row.get("line_distance_meters", metadata.get("line_distance_meters")),
            "line_tolerance_pixels": row.get("line_tolerance_pixels", metadata.get("line_tolerance_pixels")),
            "helmet_stability_frames": row.get("helmet_stability_frames", metadata.get("helmet_stability_frames")),
            "stop_speed_threshold_px": row.get("stop_speed_threshold_px", metadata.get("stop_speed_threshold_px")),
            "stop_frames_threshold": row.get("stop_frames_threshold", metadata.get("stop_frames_threshold")),
            "stop_line_distance_px": row.get("stop_line_distance_px", metadata.get("stop_line_distance_px")),
            "min_green_time": row.get("min_green_time", metadata.get("min_green_time")),
            "max_green_time": row.get("max_green_time", metadata.get("max_green_time")),
            "yellow_time": row.get("yellow_time", metadata.get("yellow_time")),
            "priority_queue_weight": row.get("priority_queue_weight", metadata.get("priority_queue_weight")),
            "priority_wait_weight": row.get("priority_wait_weight", metadata.get("priority_wait_weight")),
            "fairness_weight": row.get("fairness_weight", metadata.get("fairness_weight")),
            "max_priority_score": row.get("max_priority_score", metadata.get("max_priority_score")),
            "initial_active_lane": row.get("initial_active_lane", metadata.get("initial_active_lane")),
        }

    def _ensure_camera_columns(self, connection: Connection[Any]) -> None:
        for statement in (
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS location_link TEXT",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS frame_skip INTEGER",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS resolution_json JSONB",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS fps_limit DOUBLE PRECISION",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS ocr_enabled BOOLEAN",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS ocr_debug BOOLEAN",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS intersection_id TEXT",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS lanes_json JSONB",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS roi_config_path TEXT",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS confidence_threshold DOUBLE PRECISION",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS plate_confidence_threshold DOUBLE PRECISION",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS char_confidence_threshold DOUBLE PRECISION",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS helmet_confidence_threshold DOUBLE PRECISION",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS overspeed_threshold_kmh DOUBLE PRECISION",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS line1_y DOUBLE PRECISION",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS line2_y DOUBLE PRECISION",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS line_distance_meters DOUBLE PRECISION",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS line_tolerance_pixels INTEGER",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS helmet_stability_frames INTEGER",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS stop_speed_threshold_px DOUBLE PRECISION",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS stop_frames_threshold INTEGER",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS stop_line_distance_px DOUBLE PRECISION",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS min_green_time DOUBLE PRECISION",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS max_green_time DOUBLE PRECISION",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS yellow_time DOUBLE PRECISION",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS priority_queue_weight DOUBLE PRECISION",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS priority_wait_weight DOUBLE PRECISION",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS fairness_weight DOUBLE PRECISION",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS max_priority_score DOUBLE PRECISION",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS initial_active_lane TEXT",
        ):
            connection.execute(statement)

    def _backfill_camera_columns_from_metadata(self, connection: Connection[Any]) -> None:
        connection.execute(
            """
            UPDATE cameras
            SET
                location_link = COALESCE(location_link, metadata_json->>'location_link'),
                frame_skip = COALESCE(frame_skip, NULLIF(metadata_json->>'frame_skip', '')::INTEGER),
                resolution_json = COALESCE(resolution_json, metadata_json->'resolution'),
                fps_limit = COALESCE(fps_limit, NULLIF(metadata_json->>'fps_limit', '')::DOUBLE PRECISION),
                ocr_enabled = COALESCE(ocr_enabled, NULLIF(metadata_json->>'ocr_enabled', '')::BOOLEAN),
                ocr_debug = COALESCE(ocr_debug, NULLIF(metadata_json->>'ocr_debug', '')::BOOLEAN),
                intersection_id = COALESCE(intersection_id, metadata_json->>'intersection_id'),
                lanes_json = COALESCE(lanes_json, metadata_json->'lanes'),
                roi_config_path = COALESCE(roi_config_path, metadata_json->>'roi_config_path'),
                confidence_threshold = COALESCE(confidence_threshold, NULLIF(metadata_json->>'confidence_threshold', '')::DOUBLE PRECISION),
                plate_confidence_threshold = COALESCE(plate_confidence_threshold, NULLIF(metadata_json->>'plate_confidence_threshold', '')::DOUBLE PRECISION),
                char_confidence_threshold = COALESCE(char_confidence_threshold, NULLIF(metadata_json->>'char_confidence_threshold', '')::DOUBLE PRECISION),
                helmet_confidence_threshold = COALESCE(helmet_confidence_threshold, NULLIF(metadata_json->>'helmet_confidence_threshold', '')::DOUBLE PRECISION),
                overspeed_threshold_kmh = COALESCE(overspeed_threshold_kmh, NULLIF(metadata_json->>'overspeed_threshold_kmh', '')::DOUBLE PRECISION),
                line1_y = COALESCE(line1_y, NULLIF(metadata_json->>'line1_y', '')::DOUBLE PRECISION),
                line2_y = COALESCE(line2_y, NULLIF(metadata_json->>'line2_y', '')::DOUBLE PRECISION),
                line_distance_meters = COALESCE(line_distance_meters, NULLIF(metadata_json->>'line_distance_meters', '')::DOUBLE PRECISION),
                line_tolerance_pixels = COALESCE(line_tolerance_pixels, NULLIF(metadata_json->>'line_tolerance_pixels', '')::INTEGER),
                helmet_stability_frames = COALESCE(helmet_stability_frames, NULLIF(metadata_json->>'helmet_stability_frames', '')::INTEGER),
                stop_speed_threshold_px = COALESCE(stop_speed_threshold_px, NULLIF(metadata_json->>'stop_speed_threshold_px', '')::DOUBLE PRECISION),
                stop_frames_threshold = COALESCE(stop_frames_threshold, NULLIF(metadata_json->>'stop_frames_threshold', '')::INTEGER),
                stop_line_distance_px = COALESCE(stop_line_distance_px, NULLIF(metadata_json->>'stop_line_distance_px', '')::DOUBLE PRECISION),
                min_green_time = COALESCE(min_green_time, NULLIF(metadata_json->>'min_green_time', '')::DOUBLE PRECISION),
                max_green_time = COALESCE(max_green_time, NULLIF(metadata_json->>'max_green_time', '')::DOUBLE PRECISION),
                yellow_time = COALESCE(yellow_time, NULLIF(metadata_json->>'yellow_time', '')::DOUBLE PRECISION),
                priority_queue_weight = COALESCE(priority_queue_weight, NULLIF(metadata_json->>'priority_queue_weight', '')::DOUBLE PRECISION),
                priority_wait_weight = COALESCE(priority_wait_weight, NULLIF(metadata_json->>'priority_wait_weight', '')::DOUBLE PRECISION),
                fairness_weight = COALESCE(fairness_weight, NULLIF(metadata_json->>'fairness_weight', '')::DOUBLE PRECISION),
                max_priority_score = COALESCE(max_priority_score, NULLIF(metadata_json->>'max_priority_score', '')::DOUBLE PRECISION),
                initial_active_lane = COALESCE(initial_active_lane, metadata_json->>'initial_active_lane')
            """
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
        registration_number = str(violation.get("licensePlate", "")).strip()
        owner_name = str(violation.get("ownerName") or violation.get("driverName") or "").strip()
        owner_address = str(violation.get("ownerAddress") or violation.get("tempAddress") or "").strip()
        owner_contact_number = str(violation.get("ownerContactNumber") or "").strip()
        vehicle_color = str(violation.get("vehicleColor") or "").strip()
        camera_location = str(violation.get("cameraLocation") or "").strip()
        map_link = str(violation.get("locationLink") or "").strip()
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
                "ministry": "",
                "office": "",
            },
            "owner": {
                "fullName": owner_name,
                "age": int(violation.get("age", 0) or 0),
                "address": owner_address,
                "contactNumber": owner_contact_number,
            },
            "vehicle": {
                "registrationNumber": registration_number,
                "provinceCode": _plate_prefix(registration_number),
                "vehicleType": str(violation.get("vehicleType", "vehicle")),
                "model": "",
                "color": vehicle_color,
            },
            "license": {
                "licenseNumber": "",
                "category": "",
                "expiryDate": "",
            },
            "offense": {
                "title": offense_title,
                "sectionCode": violation_code,
                "description": str(violation.get("description", "")),
                "fineAmount": int(offense_policy["fine_amount"]),
                "pointsDeducted": int(offense_policy["points_deducted"]),
            },
            "location": {
                "place": camera_location,
                "district": "",
                "mapLink": map_link,
                "coordinates": {
                    "lat": None,
                    "lng": None,
                },
            },
            "officer": {
                "name": "",
                "rank": "",
                "badgeNumber": "",
                "signature": "",
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
        output_root = self.project_root / "surveillance" / "output"
        candidates = [f"{camera_id}.mp4"]
        match = re.search(r"(\d+)$", camera_id)
        if match is not None:
            candidates.append(f"output{match.group(1)}.mp4")

        for candidate_name in candidates:
            candidate = output_root / candidate_name
            if candidate.exists():
                return f"/surveillance-output/{candidate_name}"
        return None
