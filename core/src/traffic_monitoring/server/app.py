from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import deque
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import cv2
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from traffic_monitoring.auth import hash_password
from traffic_monitoring.config import TrafficMonitoringConfig, apply_input_overrides, build_default_config
from traffic_monitoring.events import ViolationCode
from traffic_monitoring.mock_dotm_service import load_mock_dotm_service
from traffic_monitoring.pipeline import TrafficMonitoringPipeline
from traffic_monitoring.server.repository import AdminRepository, default_database_url
from traffic_monitoring.storage import build_object_storage, load_object_storage_settings
from traffic_monitoring.traffic import SignalStateMachine


def _camera_sort_key(path: Path) -> tuple[int, str]:
    match = re.search(r"(\d+)$", path.stem)
    suffix = int(match.group(1)) if match is not None else 10_000
    return (suffix, path.stem.lower())


_SUPPORTED_SURVEILLANCE_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}


def _is_supported_surveillance_video(path: Path) -> bool:
    return path.suffix.lower() in _SUPPORTED_SURVEILLANCE_EXTENSIONS


def _discover_surveillance_videos(root: Path) -> list[Path]:
    surveillance_dir = root / "surveillance"
    surveillance_dir.mkdir(parents=True, exist_ok=True)
    return sorted(
        [
            path
            for path in surveillance_dir.iterdir()
            if path.is_file() and _is_supported_surveillance_video(path)
        ],
        key=_camera_sort_key,
    )


def _build_camera_registry(root: Path) -> dict[str, dict[str, object]]:
    cameras: dict[str, dict[str, object]] = {}
    for index, video_path in enumerate(_discover_surveillance_videos(root), start=1):
        camera_id = video_path.stem.lower()
        label = video_path.stem.upper() if video_path.stem else f"Camera {index}"
        cameras[camera_id] = {
            "id": camera_id,
            "source": str(video_path),
            "location": label,
            "location_link": None,
            "status": "online",
            "system_mode": "enforcement_mode",
        }
    return cameras

def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp_to_iso(timestamp_seconds: float) -> str:
    return datetime.fromtimestamp(timestamp_seconds, tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


app = FastAPI(title="Traffic Monitoring Stream Server")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.environ.get("ADMIN_ALLOWED_ORIGINS", "http://localhost:3000").split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_base_config = build_default_config()
load_dotenv(_base_config.root / ".env", override=False)
_object_storage_settings = load_object_storage_settings(_base_config.root)
_base_config.runtime.output_dir.mkdir(parents=True, exist_ok=True)
(_base_config.root / "surveillance").mkdir(parents=True, exist_ok=True)
_object_storage_settings.local_root.mkdir(parents=True, exist_ok=True)
app.mount("/snapshots", StaticFiles(directory=str(_base_config.runtime.output_dir)), name="snapshots")
app.mount("/inputs", StaticFiles(directory=str(_base_config.root / "input")), name="inputs")
app.mount(
    "/surveillance-media",
    StaticFiles(
        directory=str(_base_config.root / "surveillance"),
        follow_symlink=True,
    ),
    name="surveillance-media",
)
app.mount(
    "/surveillance-output",
    StaticFiles(
        directory=str(_base_config.root / "surveillance" / "output"),
        follow_symlink=True,
    ),
    name="surveillance-output",
)
app.mount(
    "/wwwroots",
    StaticFiles(
        directory=str(_object_storage_settings.local_root),
        follow_symlink=True,
    ),
    name="wwwroots",
)

cameras: dict[str, dict[str, object]] = _build_camera_registry(_base_config.root)
repository = AdminRepository(default_database_url(), project_root=_base_config.root)
object_storage = build_object_storage(_base_config.root)
vehicle_registry = load_mock_dotm_service(_base_config.root)

events: list[dict[str, object]] = []
traffic_state_by_camera: dict[str, dict[str, object]] = {}
intersection_state_by_id: dict[str, dict[str, object]] = {}
_seen_event_keys: set[tuple[str, float, int, str]] = set()
_recent_frames_by_camera: dict[str, deque[tuple[float, object]]] = {}
_api_event_codes = {
    ViolationCode.OVERSPEED.value,
    ViolationCode.NO_HELMET.value,
    ViolationCode.PLATE_UNREADABLE.value,
    ViolationCode.PLATE_MISSING.value,
    ViolationCode.WRONG_LANE.value,
}
_intersection_signal_machines: dict[str, SignalStateMachine] = {}
_VIOLATION_CLIP_PRE_SECONDS = 3.0
_VIOLATION_CLIP_MAX_SECONDS = 6.0
_SESSION_COOKIE_NAME = "hawaimama_session"


class CameraConfigUpdate(BaseModel):
    system_mode: Literal["enforcement_mode", "traffic_management_mode"] | None = None
    location: str | None = None
    frame_skip: int | None = None
    resolution: tuple[int, int] | None = None
    fps_limit: float | None = None
    ocr_enabled: bool | None = None
    ocr_debug: bool | None = None
    intersection_id: str | None = None
    lanes: list[str] | None = None
    roi_config_path: str | None = None
    confidence_threshold: float | None = None
    plate_confidence_threshold: float | None = None
    char_confidence_threshold: float | None = None
    helmet_confidence_threshold: float | None = None
    overspeed_threshold_kmh: float | None = None
    line1_y: float | None = None
    line2_y: float | None = None
    line_distance_meters: float | None = None
    line_tolerance_pixels: int | None = None
    helmet_stability_frames: int | None = None
    stop_speed_threshold_px: float | None = None
    stop_frames_threshold: int | None = None
    stop_line_distance_px: float | None = None
    min_green_time: float | None = None
    max_green_time: float | None = None
    yellow_time: float | None = None
    priority_queue_weight: float | None = None
    priority_wait_weight: float | None = None
    fairness_weight: float | None = None
    max_priority_score: float | None = None
    initial_active_lane: str | None = None


def _camera_metadata_updates(update: CameraConfigUpdate) -> dict[str, object]:
    return {
        "frame_skip": update.frame_skip,
        "resolution": list(update.resolution) if update.resolution is not None else None,
        "fps_limit": update.fps_limit,
        "ocr_enabled": update.ocr_enabled,
        "ocr_debug": update.ocr_debug,
        "intersection_id": (update.intersection_id or "").strip() or None,
        "lanes": [lane.strip() for lane in update.lanes if lane.strip()] if update.lanes is not None else None,
        "roi_config_path": (update.roi_config_path or "").strip() or None,
        "confidence_threshold": update.confidence_threshold,
        "plate_confidence_threshold": update.plate_confidence_threshold,
        "char_confidence_threshold": update.char_confidence_threshold,
        "helmet_confidence_threshold": update.helmet_confidence_threshold,
        "overspeed_threshold_kmh": update.overspeed_threshold_kmh,
        "line1_y": update.line1_y,
        "line2_y": update.line2_y,
        "line_distance_meters": update.line_distance_meters,
        "line_tolerance_pixels": update.line_tolerance_pixels,
        "helmet_stability_frames": update.helmet_stability_frames,
        "stop_speed_threshold_px": update.stop_speed_threshold_px,
        "stop_frames_threshold": update.stop_frames_threshold,
        "stop_line_distance_px": update.stop_line_distance_px,
        "min_green_time": update.min_green_time,
        "max_green_time": update.max_green_time,
        "yellow_time": update.yellow_time,
        "priority_queue_weight": update.priority_queue_weight,
        "priority_wait_weight": update.priority_wait_weight,
        "fairness_weight": update.fairness_weight,
        "max_priority_score": update.max_priority_score,
        "initial_active_lane": (update.initial_active_lane or "").strip() or None,
    }


def _resolve_roi_config_path(config: TrafficMonitoringConfig, camera: dict[str, object]) -> Path:
    roi_path = str(camera.get("roi_config_path") or "").strip()
    if not roi_path:
        return config.traffic_control.roi_config_path
    candidate = Path(roi_path)
    if candidate.is_absolute():
        return candidate
    return config.root / roi_path


class LoginRequest(BaseModel):
    username: str
    password: str


class AdminAccountCreate(BaseModel):
    username: str
    full_name: str
    password: str
    role: Literal["superadmin", "admin"] = "admin"
    is_active: bool = True
    all_locations: bool = False
    allowed_locations: list[str] = []
    permissions: dict[str, bool] | None = None


class AdminAccountUpdate(BaseModel):
    full_name: str | None = None
    password: str | None = None
    role: Literal["superadmin", "admin"] | None = None
    is_active: bool | None = None
    all_locations: bool | None = None
    allowed_locations: list[str] | None = None
    permissions: dict[str, bool] | None = None


def _normalize_location(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _default_permissions(*, superadmin: bool = False) -> dict[str, bool]:
    permissions = {
        "can_view_live": True,
        "can_manage_feeds": True,
        "can_view_violations": True,
        "can_verify_violations": True,
        "can_view_accidents": True,
        "can_verify_accidents": True,
        "can_view_challans": True,
        "can_manage_admins": False,
    }
    if superadmin:
        permissions["can_manage_admins"] = True
    return permissions


def _hackathon_admin() -> dict[str, Any]:
    return {
        "id": "hackathon-superadmin",
        "username": "superadmin",
        "full_name": "Hackathon Superadmin",
        "role": "superadmin",
        "is_active": True,
        "all_locations": True,
        "allowed_locations": [],
        "permissions": _default_permissions(superadmin=True),
    }


def _bootstrap_admin_accounts() -> list[dict[str, object]]:
    superadmin_username = os.environ.get("SUPERADMIN_USERNAME", "superadmin")
    superadmin_password = os.environ.get("SUPERADMIN_PASSWORD", "superadmin123")
    superadmin_full_name = os.environ.get("SUPERADMIN_FULL_NAME", "System Superadmin")
    default_admin_username = os.environ.get("DEFAULT_ADMIN_USERNAME", "admin")
    default_admin_password = os.environ.get("DEFAULT_ADMIN_PASSWORD", "admin123")
    default_admin_full_name = os.environ.get("DEFAULT_ADMIN_FULL_NAME", "Default Office Admin")

    return [
        {
            "username": superadmin_username,
            "full_name": superadmin_full_name,
            "password_hash": hash_password(superadmin_password),
            "role": "superadmin",
            "is_active": True,
            "all_locations": True,
            "allowed_locations": [],
            "permissions": _default_permissions(superadmin=True),
        },
        {
            "username": default_admin_username,
            "full_name": default_admin_full_name,
            "password_hash": hash_password(default_admin_password),
            "role": "admin",
            "is_active": True,
            "all_locations": True,
            "allowed_locations": [],
            "permissions": _default_permissions(superadmin=False),
        },
    ]


repository.initialize(cameras, bootstrap_admins=_bootstrap_admin_accounts())


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "unknown"


def _read_session_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization.split(" ", maxsplit=1)[1].strip()
        if token:
            return token
    cookie_token = request.cookies.get(_SESSION_COOKIE_NAME)
    if cookie_token:
        return cookie_token
    return None


def _permission_enabled(admin: dict[str, Any], permission: str) -> bool:
    if admin.get("role") == "superadmin":
        return True
    permissions = admin.get("permissions", {})
    return bool(permissions.get(permission, False))


def _can_access_location(admin: dict[str, Any], location: str | None) -> bool:
    if admin.get("role") == "superadmin" or admin.get("all_locations"):
        return True
    normalized = _normalize_location(location)
    if not normalized:
        return False
    allowed_locations = {
        _normalize_location(value)
        for value in admin.get("allowed_locations", [])
        if _normalize_location(value)
    }
    return normalized in allowed_locations


def _camera_location_for_id(camera_id: str | None) -> str | None:
    if not camera_id:
        return None
    _refresh_camera_inventory()
    camera = cameras.get(camera_id)
    if camera is None:
        return None
    return str(camera.get("location", "")).strip() or None


def _extract_record_location(record: dict[str, Any]) -> str | None:
    camera_location = str(record.get("cameraLocation") or "").strip()
    if camera_location:
        return camera_location
    nested_location = record.get("location")
    if isinstance(nested_location, dict):
        place = str(nested_location.get("place") or "").strip()
        if place:
            return place
    for key in ("address", "tempAddress", "ownerAddress"):
        value = str(record.get(key) or "").strip()
        if value:
            return value
    direct_location = str(record.get("location") or "").strip()
    if direct_location and not direct_location.startswith("http"):
        return direct_location
    return None


def _filter_records_for_admin(admin: dict[str, Any], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if _can_access_location(admin, _extract_record_location(record))
    ]


def _require_admin(request: Request, *, permission: str | None = None) -> dict[str, Any]:
    admin = getattr(request.state, "admin", None)
    if admin is None:
        token = _read_session_token(request)
        if token:
            admin = repository.get_session_admin(token)
            if admin is not None:
                request.state.admin = admin
    if admin is None:
        admin = _hackathon_admin()
        request.state.admin = admin
    if permission and not _permission_enabled(admin, permission):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return admin


def _guard_record_access(admin: dict[str, Any], record: dict[str, Any], *, detail: str = "Resource access denied") -> None:
    if not _can_access_location(admin, _extract_record_location(record)):
        raise HTTPException(status_code=403, detail=detail)


def _media_camera_id_from_path(path: str) -> str | None:
    parts = [part for part in path.split("/") if part]
    if len(parts) >= 2 and parts[0] in {"surveillance-media", "surveillance-output"}:
        return Path(parts[1]).stem.lower()
    if len(parts) >= 3 and parts[0] == "camera" and parts[2] == "stream":
        return parts[1].lower()
    if len(parts) >= 6 and parts[0] == "wwwroots" and parts[1] == "violations":
        camera_segment = parts[5]
        return camera_segment.split("-", maxsplit=1)[0].lower()
    return None


def _is_public_backend_path(path: str) -> bool:
    return path in {"/auth/login", "/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"}


def _is_protected_media_path(path: str) -> bool:
    return (
        path.startswith("/surveillance-media/")
        or path.startswith("/surveillance-output/")
        or path.startswith("/wwwroots/")
        or (path.startswith("/camera/") and path.endswith("/stream"))
    )


@app.middleware("http")
async def admin_session_middleware(request: Request, call_next):
    if request.method == "OPTIONS" or _is_public_backend_path(request.url.path):
        return await call_next(request)

    token = _read_session_token(request)
    if token:
        request.state.admin = repository.get_session_admin(token)
    elif getattr(request.state, "admin", None) is None:
        request.state.admin = _hackathon_admin()

    if _is_protected_media_path(request.url.path):
        admin = getattr(request.state, "admin", None)
        if admin is None:
            admin = _hackathon_admin()
            request.state.admin = admin
        if not _permission_enabled(admin, "can_view_live"):
            return JSONResponse({"detail": "Insufficient permissions"}, status_code=403)
        camera_id = _media_camera_id_from_path(request.url.path)
        if camera_id and not _can_access_location(admin, _camera_location_for_id(camera_id)):
            return JSONResponse({"detail": "Location access denied"}, status_code=403)

    return await call_next(request)


def _camera_location(camera_id: str) -> str:
    return str(cameras.get(camera_id, {}).get("location", "Pokhara"))


def _refresh_camera_inventory() -> None:
    global cameras
    discovered = _build_camera_registry(_base_config.root)
    repository.sync_cameras(discovered)
    stored = {camera["id"]: camera for camera in repository.list_cameras()}
    cameras = {
        camera_id: {**camera, **stored.get(camera_id, {})}
        for camera_id, camera in discovered.items()
    }


def _next_camera_id() -> str:
    discovered = _discover_surveillance_videos(_base_config.root)
    highest = 0
    for path in discovered:
        suffix = path.stem[2:]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return f"nv{highest + 1}"


def _surveillance_source_path(camera_id: str) -> Path:
    camera = cameras.get(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Unknown camera: {camera_id}")
    source_path = Path(str(camera["source"]))
    surveillance_root = (_base_config.root / "surveillance").resolve()
    source_parent = source_path.parent.resolve(strict=False)
    if source_parent != surveillance_root and surveillance_root not in source_parent.parents:
        raise HTTPException(status_code=400, detail="Only surveillance-backed feeds can be managed here")
    return source_path


_refresh_camera_inventory()


def _camera_config(camera_id: str) -> tuple[str, TrafficMonitoringConfig]:
    _refresh_camera_inventory()
    camera = cameras.get(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Unknown camera: {camera_id}")
    source = str(camera["source"])

    config = build_default_config()
    stream_output_dir = config.runtime.output_dir / camera_id
    runtime = replace(
        config.runtime,
        input_video=Path(source),
        output_dir=stream_output_dir,
        snapshots_dir=stream_output_dir / "snapshots",
        records_path=stream_output_dir / config.output.violations_filename,
    )
    runtime_options = replace(
        config.runtime_options,
        system_mode=camera.get("system_mode", config.runtime_options.system_mode),
        ocr_debug=bool(camera.get("ocr_debug", config.runtime_options.ocr_debug)),
        overlay_mode=(
            "traffic_control"
            if camera.get("system_mode", config.runtime_options.system_mode) == "traffic_management_mode"
            else "monitoring"
        ),
    )
    performance = replace(
        config.performance,
        frame_skip=int(camera.get("frame_skip", config.performance.frame_skip)),
        resolution=camera.get("resolution", config.performance.resolution),
        fps_limit=float(camera.get("fps_limit", config.performance.fps_limit))
        if camera.get("fps_limit", config.performance.fps_limit) is not None
        else None,
    )
    speed = replace(
        config.speed,
        enabled=runtime_options.system_mode != "traffic_management_mode",
        line1_y=float(camera.get("line1_y", config.speed.line1_y)),
        line2_y=float(camera.get("line2_y", config.speed.line2_y)),
        line_distance_meters=float(camera.get("line_distance_meters", config.speed.line_distance_meters)),
        line_tolerance_pixels=int(camera.get("line_tolerance_pixels", config.speed.line_tolerance_pixels)),
        overspeed_threshold_kmh=float(camera.get("overspeed_threshold_kmh", config.speed.overspeed_threshold_kmh)),
    )
    ocr = replace(
        config.ocr,
        enabled=bool(camera.get("ocr_enabled", config.ocr.enabled)),
    )
    detection = replace(
        config.detection,
        confidence_threshold=float(camera.get("confidence_threshold", config.detection.confidence_threshold)),
        plate_confidence_threshold=float(
            camera.get("plate_confidence_threshold", config.detection.plate_confidence_threshold)
        ),
        char_confidence_threshold=float(
            camera.get("char_confidence_threshold", config.detection.char_confidence_threshold)
        ),
        helmet_confidence_threshold=float(
            camera.get("helmet_confidence_threshold", config.detection.helmet_confidence_threshold)
        ),
        helmet_stability_frames=int(
            camera.get("helmet_stability_frames", config.detection.helmet_stability_frames)
        ),
    )
    traffic_control = replace(
        config.traffic_control,
        roi_config_path=_resolve_roi_config_path(config, camera),
        stop_speed_threshold_px=float(
            camera.get("stop_speed_threshold_px", config.traffic_control.stop_speed_threshold_px)
        ),
        stop_frames_threshold=int(
            camera.get("stop_frames_threshold", config.traffic_control.stop_frames_threshold)
        ),
        stop_line_distance_px=float(
            camera.get("stop_line_distance_px", config.traffic_control.stop_line_distance_px)
        ),
        min_green_time=float(camera.get("min_green_time", config.traffic_control.min_green_time)),
        max_green_time=float(camera.get("max_green_time", config.traffic_control.max_green_time)),
        yellow_time=float(camera.get("yellow_time", config.traffic_control.yellow_time)),
        initial_active_lane=str(
            camera.get("initial_active_lane", config.traffic_control.initial_active_lane)
        ),
        priority_queue_weight=float(
            camera.get("priority_queue_weight", config.traffic_control.priority_queue_weight)
        ),
        priority_wait_weight=float(
            camera.get("priority_wait_weight", config.traffic_control.priority_wait_weight)
        ),
        fairness_weight=float(camera.get("fairness_weight", config.traffic_control.fairness_weight)),
        max_priority_score=float(
            camera.get("max_priority_score", config.traffic_control.max_priority_score)
        ),
    )
    config = replace(
        config,
        runtime=runtime,
        runtime_options=runtime_options,
        performance=performance,
        traffic_control=traffic_control,
        detection=detection,
        speed=speed,
        ocr=ocr,
    )
    return source, apply_input_overrides(config)


def _intersection_signal_machine(intersection_id: str) -> SignalStateMachine:
    machine = _intersection_signal_machines.get(intersection_id)
    if machine is not None:
        return machine

    config = build_default_config()
    lane_order: list[str] = []
    seed_camera: dict[str, object] | None = None
    for camera in cameras.values():
        if camera.get("intersection_id") != intersection_id:
            continue
        if seed_camera is None:
            seed_camera = camera
        for lane in camera.get("lanes", []):
            if lane not in lane_order:
                lane_order.append(lane)

    traffic_control = config.traffic_control
    if seed_camera is not None:
        traffic_control = replace(
            traffic_control,
            initial_active_lane=str(
                seed_camera.get("initial_active_lane", traffic_control.initial_active_lane)
            ),
            min_green_time=float(seed_camera.get("min_green_time", traffic_control.min_green_time)),
            max_green_time=float(seed_camera.get("max_green_time", traffic_control.max_green_time)),
            yellow_time=float(seed_camera.get("yellow_time", traffic_control.yellow_time)),
            priority_queue_weight=float(
                seed_camera.get("priority_queue_weight", traffic_control.priority_queue_weight)
            ),
            priority_wait_weight=float(
                seed_camera.get("priority_wait_weight", traffic_control.priority_wait_weight)
            ),
            fairness_weight=float(seed_camera.get("fairness_weight", traffic_control.fairness_weight)),
            max_priority_score=float(
                seed_camera.get("max_priority_score", traffic_control.max_priority_score)
            ),
        )

    machine = SignalStateMachine(
        lane_order or [traffic_control.initial_active_lane],
        initial_active_lane=traffic_control.initial_active_lane,
        min_green_time=traffic_control.min_green_time,
        max_green_time=traffic_control.max_green_time,
        yellow_time=traffic_control.yellow_time,
        priority_queue_weight=traffic_control.priority_queue_weight,
        priority_wait_weight=traffic_control.priority_wait_weight,
        fairness_weight=traffic_control.fairness_weight,
        max_priority_score=traffic_control.max_priority_score,
    )
    _intersection_signal_machines[intersection_id] = machine
    return machine


def _update_intersection_state(camera_id: str, pipeline: TrafficMonitoringPipeline) -> None:
    camera = cameras.get(camera_id)
    if camera is None:
        return
    intersection_id = camera.get("intersection_id")
    if not intersection_id or pipeline.last_context is None:
        return

    timestamp = pipeline.last_context.timestamp_seconds
    traffic_state_by_camera[camera_id] = {
        **dict(pipeline.last_traffic_state),
        "timestamp_seconds": timestamp,
        "camera_id": camera_id,
        "intersection_id": intersection_id,
    }

    aggregate_lanes: dict[str, dict[str, float | int]] = {}
    participating_cameras: list[dict[str, object]] = []
    aggregate_timestamp = timestamp
    emergency_lane: str | None = None
    for member_camera_id, member_camera in cameras.items():
        if member_camera.get("intersection_id") != intersection_id:
            continue
        latest = traffic_state_by_camera.get(member_camera_id)
        if latest is None:
            continue
        participating_cameras.append(
            {
                "camera": member_camera_id,
                "lanes": member_camera.get("lanes", []),
                "timestamp_seconds": latest.get("timestamp_seconds"),
            }
        )
        aggregate_timestamp = max(
            aggregate_timestamp,
            float(latest.get("timestamp_seconds", aggregate_timestamp)),
        )
        if latest.get("emergency_lane") and emergency_lane is None:
            emergency_lane = str(latest.get("emergency_lane"))
        latest_lane_metrics = latest.get("lane_metrics", {})
        for lane in member_camera.get("lanes", []):
            metrics = latest_lane_metrics.get(lane)
            if metrics is None:
                continue
            aggregate_lanes[lane] = {
                "count": int(metrics.get("count", 0)),
                "queue": int(metrics.get("queue", 0)),
                "avg_wait": float(metrics.get("avg_wait", 0.0)),
            }

    if not aggregate_lanes:
        return

    signal_machine = _intersection_signal_machine(intersection_id)
    signal_snapshot = signal_machine.update(
        aggregate_timestamp,
        aggregate_lanes,
        emergency_lane=emergency_lane,
    )
    intersection_state_by_id[intersection_id] = {
        "intersection": intersection_id,
        "signal": signal_snapshot.to_dict(),
        "lanes": aggregate_lanes,
        "cameras": participating_cameras,
        "timestamp_seconds": round(aggregate_timestamp, 3),
    }


def _save_snapshot(
    *,
    camera_id: str,
    track,
    context_time: float,
    violation: str,
    frame,
) -> str | None:
    if frame is None:
        return None
    bbox = track.bbox.clamp(frame.shape[1], frame.shape[0])
    x1, y1, x2, y2 = (int(value) for value in bbox.as_tuple())
    if x2 <= x1 or y2 <= y1:
        return None
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None

    ok, encoded = cv2.imencode(".jpg", crop)
    if not ok:
        return None

    timestamp = datetime.fromtimestamp(context_time, tz=UTC)
    timestamp_tag = timestamp.strftime("%H%M%S_%f")
    location_slug = _slugify(_camera_location(camera_id))
    owner_snapshot = _owner_snapshot(
        camera_id=camera_id,
        track=track,
        seed=f"{camera_id}:{track.track_id}:{timestamp_tag}:{violation}",
    )
    storage_key = (
        f"violations/{timestamp:%Y/%m/%d}/{camera_id}-{location_slug}/"
        f"{violation}/track-{track.track_id}/{timestamp_tag}_snapshot.jpg"
    )
    image_url = object_storage.put_bytes(
        storage_key,
        encoded.tobytes(),
        content_type="image/jpeg",
    )
    metadata_key = storage_key.rsplit(".", maxsplit=1)[0] + ".json"
    metadata_payload = {
        "plate": track.plate_text,
        "owner_name": owner_snapshot["owner_name"],
        "owner_address": owner_snapshot["owner_address"],
        "violation": violation,
        "camera_id": camera_id,
        "camera_location": _camera_location(camera_id),
        "timestamp": _timestamp_to_iso(context_time),
        "image_url": image_url,
        "is_mock_data": owner_snapshot["is_mock_data"],
    }
    object_storage.put_bytes(
        metadata_key,
        json.dumps(metadata_payload, indent=2).encode("utf-8"),
        content_type="application/json",
    )
    return image_url


def _remember_frame(camera_id: str, pipeline: TrafficMonitoringPipeline) -> None:
    context = pipeline.last_context
    frame = pipeline.last_frame
    if context is None or frame is None:
        return

    frame_buffer = _recent_frames_by_camera.setdefault(camera_id, deque())
    frame_buffer.append((context.timestamp_seconds, frame.copy()))
    cutoff = context.timestamp_seconds - _VIOLATION_CLIP_MAX_SECONDS
    while frame_buffer and frame_buffer[0][0] < cutoff:
        frame_buffer.popleft()


def _save_violation_clip(
    *,
    camera_id: str,
    track,
    context_time: float,
    violation: str,
) -> str | None:
    frame_buffer = _recent_frames_by_camera.get(camera_id)
    if not frame_buffer:
        return None

    clip_start_time = context_time - _VIOLATION_CLIP_PRE_SECONDS
    selected_frames = [
        (timestamp, frame)
        for timestamp, frame in frame_buffer
        if clip_start_time <= timestamp <= context_time
    ]
    if len(selected_frames) < 2:
        return None

    duration = max(selected_frames[-1][0] - selected_frames[0][0], 0.1)
    fps = min(24.0, max(6.0, (len(selected_frames) - 1) / duration))
    timestamp = datetime.fromtimestamp(context_time, tz=UTC)
    timestamp_tag = timestamp.strftime("%H%M%S_%f")
    location_slug = _slugify(_camera_location(camera_id))
    storage_key = (
        f"violations/{timestamp:%Y/%m/%d}/{camera_id}-{location_slug}/"
        f"{violation}/track-{track.track_id}/{timestamp_tag}_clip.mp4"
    )

    with tempfile.TemporaryDirectory(prefix=f"{camera_id}_{violation}_") as temp_dir:
        temp_path = Path(temp_dir)
        for index, (_, frame) in enumerate(selected_frames):
            frame_path = temp_path / f"frame_{index:05d}.jpg"
            if not cv2.imwrite(str(frame_path), frame):
                return None

        clip_path = temp_path / "clip.mp4"
        command = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-framerate",
            f"{fps:.2f}",
            "-i",
            str(temp_path / "frame_%05d.jpg"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(clip_path),
        ]
        try:
            subprocess.run(
                command,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            return None
        if not clip_path.exists():
            return None

        return object_storage.put_file(
            storage_key,
            clip_path,
            content_type="video/mp4",
        )


def _camera_location_link(camera_id: str) -> str | None:
    camera = cameras.get(camera_id, {})
    location_link = camera.get("location_link")
    if not location_link:
        return None
    return str(location_link)


def _owner_snapshot(*, camera_id: str, track, seed: str) -> dict[str, object]:
    fallback = vehicle_registry.choose_demo_record(seed=seed)
    return {
        "owner_name": str(track.metadata.get("owner_name") or fallback.owner_name),
        "owner_address": str(track.metadata.get("owner_address") or fallback.address),
        "vehicle_color": str(track.metadata.get("vehicle_color") or fallback.color),
        "registration_date": str(track.metadata.get("registration_date") or fallback.registration_date),
        "owner_contact_number": str(track.metadata.get("owner_contact_number") or fallback.contact_number),
        "is_mock_data": bool(track.metadata.get("is_mock_data", True)),
    }


def _build_violation_record(
    *,
    camera_id: str,
    track,
    timestamp_seconds: float,
    violation_code: str,
    image_path: str | None,
    clip_url: str | None,
) -> dict[str, object]:
    location = _camera_location(camera_id)
    source_path = Path(str(cameras.get(camera_id, {}).get("source", "")))
    if source_path.parent.name == "surveillance":
        source_video_url = f"/surveillance-media/{source_path.name}"
    else:
        source_video_url = f"/inputs/{source_path.name}"
    violation_titles = {
        "overspeed": "Overspeed Violation",
        "no_helmet": "No Helmet Detected",
        "wrong_lane": "Wrong Lane Violation",
        "plate_missing": "License Plate Missing",
        "plate_unreadable": "License Plate Unreadable",
    }
    now = _utc_now_iso()
    timestamp = _timestamp_to_iso(timestamp_seconds)
    license_plate = (track.plate_text or f"{track.label_name[:2].upper()}-{track.track_id:04d}").upper()
    owner_snapshot = _owner_snapshot(
        camera_id=camera_id,
        track=track,
        seed=f"{camera_id}:{track.track_id}:{timestamp}",
    )
    owner_name = str(owner_snapshot["owner_name"])
    owner_address = str(owner_snapshot["owner_address"])
    vehicle_color = str(owner_snapshot["vehicle_color"])
    registration_date = str(owner_snapshot["registration_date"])
    owner_contact_number = str(owner_snapshot["owner_contact_number"])
    is_mock_data = bool(owner_snapshot["is_mock_data"])
    vehicle_type = str(track.metadata.get("owner_vehicle_type") or track.label_name)
    return {
        "id": str(uuid4()),
        "cameraId": camera_id,
        "trackId": track.track_id,
        "violationCode": violation_code,
        "vehicleType": vehicle_type,
        "title": violation_titles.get(violation_code, "Traffic Violation"),
        "driverName": owner_name,
        "age": 0,
        "dob": "2000-01-01T00:00:00Z",
        "bloodGroup": "Unknown",
        "licensePlate": license_plate,
        "tempAddress": owner_address,
        "permAddress": owner_address,
        "timestamp": timestamp,
        "locationLink": _camera_location_link(camera_id) or "",
        "screenshot1Url": image_path or "",
        "screenshot2Url": "",
        "screenshot3Url": "",
        "videoUrl": clip_url or source_video_url,
        "description": (
            f"{violation_titles.get(violation_code, 'Traffic violation')} detected at "
            f"{location}. Plate read: {track.plate_text or 'pending verification'}. "
            f"Owner: {owner_name}."
        ),
        "verified": False,
        "cameraLocation": location,
        "cameraLocationLink": _camera_location_link(camera_id),
        "evidenceProvider": object_storage.provider,
        "evidenceClipUrl": clip_url or "",
        "sourceVideoUrl": source_video_url,
        "ownerName": owner_name,
        "ownerAddress": owner_address,
        "ownerContactNumber": owner_contact_number,
        "vehicleColor": vehicle_color,
        "registrationDate": registration_date,
        "isMockData": is_mock_data,
        "createdAt": now,
        "updatedAt": now,
    }


def _record_new_events(camera_id: str, pipeline: TrafficMonitoringPipeline) -> None:
    context = pipeline.last_context
    if context is None:
        return

    tracks_by_id = {track.track_id: track for track in pipeline.last_tracks}
    for track_id, findings in pipeline.last_new_findings.items():
        track = tracks_by_id.get(track_id)
        if track is None:
            continue
        for finding in findings:
            violation = finding.code.value
            if violation not in _api_event_codes:
                continue
            timestamp = round(context.timestamp_seconds, 3)
            event_key = (camera_id, timestamp, track_id, violation)
            if event_key in _seen_event_keys:
                continue
            _seen_event_keys.add(event_key)
            image_path = _save_snapshot(
                camera_id=camera_id,
                track=track,
                context_time=timestamp,
                violation=violation,
                frame=pipeline.last_frame,
            )
            clip_url = _save_violation_clip(
                camera_id=camera_id,
                track=track,
                context_time=timestamp,
                violation=violation,
            )
            owner_snapshot = _owner_snapshot(
                camera_id=camera_id,
                track=track,
                seed=f"{camera_id}:{track_id}:{timestamp}:{violation}",
            )
            event_payload = {
                "camera": camera_id,
                "time": timestamp,
                "track_id": track_id,
                "vehicle": track.label_name,
                "vehicle_type": str(track.metadata.get("owner_vehicle_type") or track.label_name),
                "plate": track.plate_text,
                "owner_name": owner_snapshot["owner_name"],
                "address": owner_snapshot["owner_address"],
                "violation": violation,
                "image": image_path,
                "video": clip_url,
                "location": _camera_location(camera_id),
                "location_link": _camera_location_link(camera_id),
                "storage_provider": object_storage.provider,
                "is_mock_data": owner_snapshot["is_mock_data"],
            }
            events.append(event_payload)
            repository.ingest_violation_event(
                _build_violation_record(
                    camera_id=camera_id,
                    track=track,
                    timestamp_seconds=timestamp,
                    violation_code=violation,
                    image_path=image_path,
                    clip_url=clip_url,
                ),
                source_event_key=f"{camera_id}:{timestamp}:{track_id}:{violation}",
            )


def mjpeg_frame_generator(camera_id: str) -> Iterator[bytes]:
    source, config = _camera_config(camera_id)
    pipeline = TrafficMonitoringPipeline(config)
    for frame in pipeline.frame_generator(source):
        _remember_frame(camera_id, pipeline)
        _record_new_events(camera_id, pipeline)
        _update_intersection_state(camera_id, pipeline)
        ok, encoded = cv2.imencode(".jpg", frame)
        if not ok:
            continue
        payload = encoded.tobytes()
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + payload + b"\r\n"


@app.get("/video_feed")
def video_feed(request: Request) -> StreamingResponse:
    admin = _require_admin(request, permission="can_view_live")
    _refresh_camera_inventory()
    if not cameras:
        raise HTTPException(status_code=404, detail="No surveillance videos found")
    accessible_camera = next(
        (
            camera_id
            for camera_id in cameras
            if _can_access_location(admin, _camera_location_for_id(camera_id))
        ),
        None,
    )
    if accessible_camera is None:
        raise HTTPException(status_code=403, detail="No live feeds available for this account")
    return StreamingResponse(
        mjpeg_frame_generator(accessible_camera),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.post("/auth/login")
def login_admin(payload: LoginRequest) -> JSONResponse:
    admin = repository.authenticate_admin(payload.username, payload.password)
    if admin is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = repository.create_admin_session(admin["id"])
    response = JSONResponse({"admin": admin, "token": token})
    response.set_cookie(
        _SESSION_COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=24 * 60 * 60,
    )
    return response


@app.post("/auth/logout")
def logout_admin(request: Request) -> JSONResponse:
    token = _read_session_token(request)
    if token:
        repository.revoke_session(token)
    response = JSONResponse({"ok": True})
    response.delete_cookie(_SESSION_COOKIE_NAME, samesite="lax")
    return response


@app.get("/auth/me")
def current_admin(request: Request) -> JSONResponse:
    return JSONResponse(_require_admin(request))


@app.get("/auth/admins")
def list_admin_accounts(request: Request) -> JSONResponse:
    _require_admin(request, permission="can_manage_admins")
    return JSONResponse(repository.list_admin_accounts())


@app.post("/auth/admins")
def create_admin_account(request: Request, payload: AdminAccountCreate) -> JSONResponse:
    _require_admin(request, permission="can_manage_admins")
    try:
        admin = repository.create_admin_account(
            username=payload.username.strip(),
            full_name=payload.full_name.strip(),
            password_hash=hash_password(payload.password),
            role=payload.role,
            is_active=payload.is_active,
            all_locations=payload.all_locations,
            allowed_locations=payload.allowed_locations,
            permissions=payload.permissions or _default_permissions(superadmin=payload.role == "superadmin"),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to create admin account: {exc}") from exc
    return JSONResponse(admin)


@app.patch("/auth/admins/{admin_id}")
def update_admin_account(request: Request, admin_id: str, payload: AdminAccountUpdate) -> JSONResponse:
    _require_admin(request, permission="can_manage_admins")
    next_permissions = payload.permissions
    if payload.role == "superadmin" and next_permissions is None:
        next_permissions = _default_permissions(superadmin=True)
    admin = repository.update_admin_account(
        admin_id,
        full_name=payload.full_name.strip() if payload.full_name else None,
        password_hash=hash_password(payload.password) if payload.password else None,
        role=payload.role,
        is_active=payload.is_active,
        all_locations=payload.all_locations,
        allowed_locations=payload.allowed_locations,
        permissions=next_permissions,
    )
    if admin is None:
        raise HTTPException(status_code=404, detail=f"Unknown admin account: {admin_id}")
    return JSONResponse(admin)


@app.get("/camera/{camera_id}/stream")
def camera_stream(camera_id: str, request: Request) -> StreamingResponse:
    admin = _require_admin(request, permission="can_view_live")
    _refresh_camera_inventory()
    if not _can_access_location(admin, _camera_location_for_id(camera_id)):
        raise HTTPException(status_code=403, detail="Location access denied")
    return StreamingResponse(
        mjpeg_frame_generator(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/surveillance/feeds")
def surveillance_feeds(request: Request) -> JSONResponse:
    admin = _require_admin(request, permission="can_view_live")
    _refresh_camera_inventory()
    feeds = _filter_records_for_admin(admin, repository.list_surveillance_feeds())
    return JSONResponse(feeds)


@app.get("/vehicle/{plate}")
def vehicle_lookup(plate: str, request: Request) -> JSONResponse:
    _require_admin(request)
    return JSONResponse(vehicle_registry.api_response(plate))


@app.get("/events")
def list_events(request: Request) -> JSONResponse:
    admin = _require_admin(request, permission="can_view_violations")
    return JSONResponse(_filter_records_for_admin(admin, events))


@app.get("/cameras")
def list_cameras(request: Request) -> JSONResponse:
    admin = _require_admin(request, permission="can_view_live")
    _refresh_camera_inventory()
    return JSONResponse(_filter_records_for_admin(admin, repository.list_cameras()))


@app.get("/admin/cameras")
def list_camera_configs(request: Request) -> JSONResponse:
    admin = _require_admin(request, permission="can_manage_feeds")
    _refresh_camera_inventory()
    return JSONResponse(_filter_records_for_admin(admin, repository.list_cameras()))


@app.patch("/admin/cameras/{camera_id}")
def update_camera_config(camera_id: str, update: CameraConfigUpdate, request: Request) -> JSONResponse:
    admin = _require_admin(request, permission="can_manage_feeds")
    _refresh_camera_inventory()
    if not _can_access_location(admin, _camera_location_for_id(camera_id)):
        raise HTTPException(status_code=403, detail="Location access denied")

    camera = repository.update_camera_config(
        camera_id,
        system_mode=update.system_mode,
        location=update.location,
        metadata_updates=_camera_metadata_updates(update),
    )
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Unknown camera: {camera_id}")
    if camera_id in cameras:
        cameras[camera_id].update(camera)
    return JSONResponse(camera)


@app.post("/admin/cameras")
async def create_camera_config(
    request: Request,
    file: UploadFile = File(...),
    location: str = Form(...),
    system_mode: Literal["enforcement_mode", "traffic_management_mode"] = Form("enforcement_mode"),
) -> JSONResponse:
    _require_admin(request, permission="can_manage_feeds")
    location_value = location.strip()
    if not location_value:
        raise HTTPException(status_code=400, detail="Location is required")

    suffix = Path(file.filename or "").suffix.lower() or ".mp4"
    if suffix not in _SUPPORTED_SURVEILLANCE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported video format")

    camera_id = _next_camera_id()
    destination = _base_config.root / "surveillance" / f"{camera_id}{suffix}"
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        with destination.open("wb") as output_file:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                output_file.write(chunk)
    except Exception as exc:
        if destination.exists():
            destination.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Failed to store uploaded feed: {exc}") from exc
    finally:
        await file.close()

    _refresh_camera_inventory()
    camera = repository.update_camera_config(
        camera_id,
        system_mode=system_mode,
        location=location_value,
    )
    if camera is None:
        raise HTTPException(status_code=500, detail="Feed was uploaded but registry update failed")
    if camera_id in cameras:
        cameras[camera_id].update(camera)
    return JSONResponse(camera)


@app.delete("/admin/cameras/{camera_id}")
def delete_camera_config(camera_id: str, request: Request) -> JSONResponse:
    admin = _require_admin(request, permission="can_manage_feeds")
    if not _can_access_location(admin, _camera_location_for_id(camera_id)):
        raise HTTPException(status_code=403, detail="Location access denied")
    source_path = _surveillance_source_path(camera_id)
    source_path.unlink(missing_ok=True)

    processed_preview = _base_config.root / "surveillance" / "output" / f"{camera_id}.mp4"
    processed_preview.unlink(missing_ok=True)

    stream_output_dir = _base_config.runtime.output_dir / camera_id
    if stream_output_dir.exists():
        shutil.rmtree(stream_output_dir, ignore_errors=True)

    _recent_frames_by_camera.pop(camera_id, None)
    traffic_state_by_camera.pop(camera_id, None)
    cameras.pop(camera_id, None)
    _refresh_camera_inventory()
    return JSONResponse({"deleted": True, "camera_id": camera_id})


@app.get("/violations")
def list_violations(request: Request) -> JSONResponse:
    admin = _require_admin(request, permission="can_view_violations")
    return JSONResponse(_filter_records_for_admin(admin, repository.list_violations()))


@app.get("/violations/{violation_id}")
def get_violation(violation_id: str, request: Request) -> JSONResponse:
    admin = _require_admin(request, permission="can_view_violations")
    violation = repository.get_violation(violation_id)
    if violation is None:
        raise HTTPException(status_code=404, detail=f"Unknown violation: {violation_id}")
    _guard_record_access(admin, violation, detail="Location access denied")
    return JSONResponse(violation)


@app.post("/violations/{violation_id}/verify")
def verify_violation(violation_id: str, request: Request) -> JSONResponse:
    admin = _require_admin(request, permission="can_verify_violations")
    violation = repository.get_violation(violation_id)
    if violation is None:
        raise HTTPException(status_code=404, detail=f"Unknown violation: {violation_id}")
    _guard_record_access(admin, violation, detail="Location access denied")
    result = repository.verify_violation(violation_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Unknown violation: {violation_id}")
    return JSONResponse(result)


@app.get("/accidents")
def list_accidents(request: Request) -> JSONResponse:
    admin = _require_admin(request, permission="can_view_accidents")
    return JSONResponse(_filter_records_for_admin(admin, repository.list_accidents()))


@app.get("/accidents/{accident_id}")
def get_accident(accident_id: str, request: Request) -> JSONResponse:
    admin = _require_admin(request, permission="can_view_accidents")
    accident = repository.get_accident(accident_id)
    if accident is None:
        raise HTTPException(status_code=404, detail=f"Unknown accident: {accident_id}")
    _guard_record_access(admin, accident, detail="Location access denied")
    return JSONResponse(accident)


@app.post("/accidents/{accident_id}/verify")
def verify_accident(accident_id: str, request: Request) -> JSONResponse:
    admin = _require_admin(request, permission="can_verify_accidents")
    accident = repository.get_accident(accident_id)
    if accident is None:
        raise HTTPException(status_code=404, detail=f"Unknown accident: {accident_id}")
    _guard_record_access(admin, accident, detail="Location access denied")
    result = repository.verify_accident(accident_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Unknown accident: {accident_id}")
    return JSONResponse(result)


@app.get("/challans")
def list_challans(request: Request) -> JSONResponse:
    admin = _require_admin(request, permission="can_view_challans")
    return JSONResponse(_filter_records_for_admin(admin, repository.list_challans()))


@app.get("/challans/{challan_id}")
def get_challan(challan_id: str, request: Request) -> JSONResponse:
    admin = _require_admin(request, permission="can_view_challans")
    challan = repository.get_challan(challan_id)
    if challan is None:
        raise HTTPException(status_code=404, detail=f"Unknown challan: {challan_id}")
    _guard_record_access(admin, challan, detail="Location access denied")
    return JSONResponse(challan)


@app.get("/traffic/state")
def traffic_state(request: Request) -> JSONResponse:
    _require_admin(request, permission="can_view_live")
    if intersection_state_by_id:
        intersection_id = next(reversed(intersection_state_by_id))
        latest = intersection_state_by_id[intersection_id]
        return JSONResponse(latest)
    return JSONResponse({"intersection": None, "signal": {}, "lanes": {}, "cameras": []})


@app.get("/traffic/lanes")
def traffic_lanes(request: Request) -> JSONResponse:
    _require_admin(request, permission="can_view_live")
    if intersection_state_by_id:
        intersection_id = next(reversed(intersection_state_by_id))
        latest = intersection_state_by_id[intersection_id]
        return JSONResponse(
            {
                "intersection": intersection_id,
                "lanes": latest.get("lanes", {}),
                "cameras": latest.get("cameras", []),
            }
        )
    return JSONResponse({"intersection": None, "lanes": {}, "cameras": []})
