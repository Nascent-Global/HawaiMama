
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

Point = tuple[int, int]
Polygon = tuple[Point, ...]

DEFAULT_TRACKED_CLASSES: tuple[str, ...] = (
    "person",
    "motorcycle",
    "car",
    "bus",
    "truck",
)

DEFAULT_DISPLAY_LABELS: dict[str, str] = {
    "person": "Person",
    "motorcycle": "Bike",
    "car": "Car",
    "bus": "Bus",
    "truck": "Truck",
}


def project_root() -> Path:
    """Return the repository root discovered from the package location."""

    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class ModelPaths:
    """Filesystem locations for model weights."""

    main_detector: Path
    helmet_detector: Path
    plate_detector: Path
    face_detector: Path | None = None


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    """Input and output locations used by the pipeline."""

    input_video: Path
    output_dir: Path
    snapshots_dir: Path
    records_path: Path


@dataclass(frozen=True, slots=True)
class OCRConfig:
    """Configuration for OCR behavior."""

    enabled: bool = True
    languages: tuple[str, ...] = ("en",)
    minimum_confidence: float = 0.35
    enforce_plate_rules: bool = False


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """Non-path runtime options."""

    show: bool = False
    fps_override: float | None = 12.0
    frame_limit: int | None = None
    helmet_debug: bool = False


@dataclass(frozen=True, slots=True)
class PerformanceConfig:
    """Configuration for runtime throughput controls."""

    frame_skip: int = 1
    resolution: tuple[int, int] | None = None
    fps_limit: float | None = 12.0


@dataclass(frozen=True, slots=True)
class TrafficControlConfig:
    """Configuration for adaptive-traffic extensions."""

    roi_config_path: Path


@dataclass(frozen=True, slots=True)
class DetectionConfig:
    """Thresholds and class selection for the detection stage."""

    tracked_classes: tuple[str, ...] = DEFAULT_TRACKED_CLASSES
    display_labels: dict[str, str] = field(
        default_factory=lambda: DEFAULT_DISPLAY_LABELS.copy()
    )
    confidence_threshold: float = 0.25
    plate_confidence_threshold: float = 0.25
    helmet_confidence_threshold: float = 0.30
    face_confidence_threshold: float = 0.50
    minimum_association_iou: float = 0.10
    minimum_rider_distance_ratio: float = 1.50
    helmet_top_region_ratio: float = 0.45
    helmet_overlap_threshold: float = 0.05
    helmet_stability_frames: int = 5


@dataclass(frozen=True, slots=True)
class TrackingConfig:
    """Configuration for persistent vehicle tracking."""

    tracker: str = "bytetrack.yaml"
    persist: bool = True
    max_age_frames: int = 30
    history_size: int = 15
    min_track_confidence: float = 0.25


@dataclass(frozen=True, slots=True)
class SpeedConfig:
    """Configuration for reference-line speed estimation."""

    enabled: bool = True
    line1_y: float = 0.50
    line2_y: float = 0.70
    line_distance_meters: float = 12.0
    line_tolerance_pixels: int = 15
    overspeed_threshold_kmh: float = 60.0
    max_reasonable_speed_kmh: float = 120.0


@dataclass(frozen=True, slots=True)
class WrongLaneConfig:
    """Configuration for optional wrong-lane detection."""

    enabled: bool = False
    lane_polygons: tuple[Polygon, ...] = ()
    allowed_vehicle_classes: tuple[str, ...] = ("motorcycle", "car", "bus", "truck")


@dataclass(frozen=True, slots=True)
class FaceCaptureConfig:
    """Configuration for best-effort face capture on motorbikes."""

    enabled: bool = False
    minimum_confidence: float = 0.50
    save_snapshots: bool = True


@dataclass(frozen=True, slots=True)
class OutputConfig:
    """Configuration for annotated outputs and structured logs."""

    annotated_video_name: str = "annotated.mp4"
    violations_filename: str = "violations.json"


@dataclass(frozen=True, slots=True)
class TrafficMonitoringConfig:
    """Complete project configuration."""

    root: Path
    models: ModelPaths
    runtime: RuntimePaths
    runtime_options: RuntimeConfig
    performance: PerformanceConfig
    traffic_control: TrafficControlConfig
    detection: DetectionConfig
    tracking: TrackingConfig
    speed: SpeedConfig
    wrong_lane: WrongLaneConfig
    face_capture: FaceCaptureConfig
    ocr: OCRConfig
    output: OutputConfig

    @property
    def primary_tracked_class_ids(self) -> tuple[int, ...]:
        class_ids: list[int] = []
        for label in self.detection.tracked_classes:
            class_id = YOLO_CLASS_NAME_TO_ID.get(label)
            if class_id is not None:
                class_ids.append(class_id)
        return tuple(class_ids)

    @property
    def output_video_path(self) -> Path:
        return self.runtime.output_dir / self.output.annotated_video_name

    def effective_fps(self, source_fps: float) -> float:
        if self.runtime_options.fps_override and self.runtime_options.fps_override > 0:
            return self.runtime_options.fps_override
        return source_fps if source_fps > 0 else 30.0


def build_default_config(root: Path | None = None) -> TrafficMonitoringConfig:
    """Build the default configuration used by the hackathon scaffold."""

    repo_root = project_root() if root is None else root.resolve()
    models_dir = repo_root / "models"
    output_dir = repo_root / "output"
    config_dir = repo_root / "config"

    return TrafficMonitoringConfig(
        root=repo_root,
        models=ModelPaths(
            main_detector=Path("yolov8n.pt"),
            helmet_detector=models_dir / "helmet.pt",
            plate_detector=models_dir / "plate.pt",
            face_detector=models_dir / "face.pt",
        ),
        runtime=RuntimePaths(
            input_video=repo_root / "input.mp4",
            output_dir=output_dir,
            snapshots_dir=output_dir / "snapshots",
            records_path=output_dir / "violations.json",
        ),
        runtime_options=RuntimeConfig(),
        performance=PerformanceConfig(),
        traffic_control=TrafficControlConfig(
            roi_config_path=config_dir / "approach_rois_input6.json",
        ),
        detection=DetectionConfig(),
        tracking=TrackingConfig(),
        speed=SpeedConfig(),
        wrong_lane=WrongLaneConfig(),
        face_capture=FaceCaptureConfig(),
        ocr=OCRConfig(),
        output=OutputConfig(),
    )


def ensure_output_directories(config: TrafficMonitoringConfig) -> None:
    """Create output directories required by the pipeline."""

    config.runtime.output_dir.mkdir(parents=True, exist_ok=True)
    config.runtime.snapshots_dir.mkdir(parents=True, exist_ok=True)


def config_from_namespace(args: object, root: Path | None = None) -> TrafficMonitoringConfig:
    """Build config from argparse-like namespace."""

    base = build_default_config(root=root)
    namespace = args if hasattr(args, "__dict__") else SimpleNamespace()

    input_video = Path(getattr(namespace, "input", base.runtime.input_video))
    output_path = Path(getattr(namespace, "output", base.output_video_path))
    output_dir = output_path.parent

    primary_model_arg = getattr(namespace, "primary_model", None)
    helmet_model_arg = getattr(namespace, "helmet_model", None)
    plate_model_arg = getattr(namespace, "plate_model", None)

    models = ModelPaths(
        main_detector=Path(primary_model_arg) if primary_model_arg else base.models.main_detector,
        helmet_detector=Path(helmet_model_arg) if helmet_model_arg else base.models.helmet_detector,
        plate_detector=Path(plate_model_arg) if plate_model_arg else base.models.plate_detector,
        face_detector=base.models.face_detector,
    )
    runtime = RuntimePaths(
        input_video=input_video,
        output_dir=output_dir,
        snapshots_dir=output_dir / "snapshots",
        records_path=output_dir / base.output.violations_filename,
    )
    runtime_options = RuntimeConfig(
        show=bool(getattr(namespace, "show", base.runtime_options.show)),
        fps_override=(
            float(getattr(namespace, "fps_override"))
            if getattr(namespace, "fps_override", 0.0)
            else None
        ),
        frame_limit=(
            int(getattr(namespace, "frame_limit"))
            if getattr(namespace, "frame_limit", 0)
            else None
        ),
        helmet_debug=bool(getattr(namespace, "helmet_debug", base.runtime_options.helmet_debug)),
    )
    speed = SpeedConfig(
        enabled=base.speed.enabled,
        line1_y=base.speed.line1_y,
        line2_y=base.speed.line2_y,
        line_distance_meters=base.speed.line_distance_meters,
        overspeed_threshold_kmh=float(
            getattr(namespace, "overspeed_threshold", base.speed.overspeed_threshold_kmh)
        ),
        max_reasonable_speed_kmh=base.speed.max_reasonable_speed_kmh,
    )
    resolution_arg = getattr(namespace, "resolution", "")
    resolution: tuple[int, int] | None = None
    if resolution_arg:
        width_text, height_text = str(resolution_arg).lower().split("x", maxsplit=1)
        resolution = (int(width_text), int(height_text))
    performance = PerformanceConfig(
        frame_skip=max(1, int(getattr(namespace, "frame_skip", base.performance.frame_skip))),
        resolution=resolution,
        fps_limit=(
            float(getattr(namespace, "fps_limit"))
            if getattr(namespace, "fps_limit", 0.0)
            else None
        ),
    )

    return TrafficMonitoringConfig(
        root=base.root,
        models=models,
        runtime=runtime,
        runtime_options=runtime_options,
        performance=performance,
        traffic_control=base.traffic_control,
        detection=base.detection,
        tracking=base.tracking,
        speed=speed,
        wrong_lane=base.wrong_lane,
        face_capture=base.face_capture,
        ocr=base.ocr,
        output=OutputConfig(annotated_video_name=output_path.name, violations_filename=base.output.violations_filename),
    )


YOLO_CLASS_NAME_TO_ID: dict[str, int] = {
    "person": 0,
    "bicycle": 1,
    "car": 2,
    "motorcycle": 3,
    "bus": 5,
    "truck": 7,
}


__all__ = [
    "Point",
    "Polygon",
    "DEFAULT_DISPLAY_LABELS",
    "DEFAULT_TRACKED_CLASSES",
    "DetectionConfig",
    "FaceCaptureConfig",
    "ModelPaths",
    "OCRConfig",
    "OutputConfig",
    "PerformanceConfig",
    "RuntimeConfig",
    "RuntimePaths",
    "SpeedConfig",
    "TrackingConfig",
    "TrafficMonitoringConfig",
    "TrafficControlConfig",
    "WrongLaneConfig",
    "build_default_config",
    "config_from_namespace",
    "ensure_output_directories",
    "project_root",
]
