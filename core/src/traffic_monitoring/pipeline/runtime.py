from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter, sleep
from typing import Iterator

import cv2
import numpy as np

from traffic_monitoring.annotations import annotate_frame, annotate_traffic_control_frame
from traffic_monitoring.config import (
    build_default_config,
    TrafficMonitoringConfig,
    ensure_output_directories,
)
from traffic_monitoring.detectors import EasyOCRReader, InferenceDetection, YOLODetector
from traffic_monitoring.domain import FrameContext
from traffic_monitoring.events import ViolationRecorder, ViolationEngine
from traffic_monitoring.secondary import (
    FaceCaptureAnalyzer,
    HelmetComplianceAnalyzer,
)
from traffic_monitoring.traffic import LaneAssignmentEngine
from traffic_monitoring.traffic import SignalStateMachine
from traffic_monitoring.tracking import (
    PlateRecognizer,
    RiderAssociationEngine,
    TrackManager,
)
from traffic_monitoring.video import VideoSource


@dataclass(frozen=True, slots=True)
class RunSummary:
    frames_processed: int
    elapsed_seconds: float
    output_video: Path | None = None


class TrafficMonitoringPipeline:
    def __init__(self, config: TrafficMonitoringConfig) -> None:
        self.config = config
        self.system_mode = config.runtime_options.system_mode
        self.enforcement_enabled = self.system_mode == "enforcement_mode"
        plate_detector_path = config.models.plate_detector
        plate_enabled = self.enforcement_enabled and plate_detector_path.exists()
        char_detector_path = config.models.char_detector
        char_enabled = (
            self.enforcement_enabled
            and char_detector_path is not None
            and char_detector_path.exists()
        )
        helmet_enabled = self.enforcement_enabled and config.models.helmet_detector.exists()
        face_enabled = (
            self.enforcement_enabled
            and bool(config.models.face_detector and config.models.face_detector.exists())
        )
        self.detector = YOLODetector(
            config.models.main_detector,
            confidence=config.detection.confidence_threshold,
        )
        self.plate_detector = (
            YOLODetector(
                plate_detector_path,
                confidence=config.detection.plate_confidence_threshold,
            )
            if plate_enabled
            else None
        )
        self.char_detector = (
            YOLODetector(
                char_detector_path,
                confidence=config.detection.char_confidence_threshold,
            )
            if char_enabled and char_detector_path is not None
            else None
        )
        self.ocr_reader = (
            EasyOCRReader(list(config.ocr.languages))
            if config.ocr.enabled and plate_enabled
            else None
        )
        self.helmet_detector = (
            YOLODetector(
                config.models.helmet_detector,
                confidence=config.detection.helmet_confidence_threshold,
            )
            if helmet_enabled
            else None
        )
        self.face_detector = (
            YOLODetector(
                config.models.face_detector,
                confidence=config.face_capture.minimum_confidence,
            )
            if face_enabled and config.models.face_detector is not None
            else None
        )
        self.track_manager = TrackManager(config)
        self.rider_association = RiderAssociationEngine(config)
        self.plate_recognizer = PlateRecognizer(
            config,
            self.plate_detector,
            self.ocr_reader,
            self.char_detector,
        )
        self.helmet_analyzer = HelmetComplianceAnalyzer(config, self.helmet_detector)
        self.face_capture = FaceCaptureAnalyzer(config, self.face_detector)
        self.violation_engine = ViolationEngine(config)
        self.recorder = ViolationRecorder(config.runtime.records_path)
        self.lane_assignment = LaneAssignmentEngine(
            config.traffic_control.roi_config_path,
            stop_speed_threshold_px=config.traffic_control.stop_speed_threshold_px,
            stop_frames_threshold=config.traffic_control.stop_frames_threshold,
            stop_line_distance_px=config.traffic_control.stop_line_distance_px,
            emergency_labels=config.traffic_control.emergency_labels,
            emergency_keywords=config.traffic_control.emergency_keywords,
        )
        lane_order = list(self.lane_assignment.rois) or [config.traffic_control.initial_active_lane]
        self.signal_state_machine = SignalStateMachine(
            lane_order,
            initial_active_lane=config.traffic_control.initial_active_lane,
            min_green_time=config.traffic_control.min_green_time,
            max_green_time=config.traffic_control.max_green_time,
            yellow_time=config.traffic_control.yellow_time,
            priority_queue_weight=config.traffic_control.priority_queue_weight,
            priority_wait_weight=config.traffic_control.priority_wait_weight,
            fairness_weight=config.traffic_control.fairness_weight,
            max_priority_score=config.traffic_control.max_priority_score,
        )
        self.last_context: FrameContext | None = None
        self.last_tracks = []
        self.last_findings_by_track: dict[int, list] = {}
        self.last_new_findings: dict[int, list] = {}
        self.last_frame: np.ndarray | None = None
        self.last_traffic_state: dict[str, object] = {"lane_counts": {}, "lane_metrics": {}, "signal": {}}

    def run(self) -> RunSummary:
        ensure_output_directories(self.config)
        started_at = perf_counter()
        frames_processed = 0
        writer: cv2.VideoWriter | None = None

        try:
            for frame in self.frame_generator():
                if writer is None:
                    writer = self._create_output_writer(frame)
                if writer is not None:
                    writer.write(frame)
                frames_processed += 1
        finally:
            if writer is not None:
                writer.release()

        return RunSummary(
            frames_processed=frames_processed,
            elapsed_seconds=perf_counter() - started_at,
            output_video=self.config.output_video_path if frames_processed > 0 else None,
        )

    def _create_output_writer(self, frame: np.ndarray) -> cv2.VideoWriter | None:
        output_path = self.config.output_video_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fps = self.config.performance.fps_limit or self.config.runtime_options.fps_override or 12.0
        height, width = frame.shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(output_path), fourcc, float(fps), (width, height))
        if not writer.isOpened():
            return None
        return writer

    def frame_generator(
        self,
        source: Path | str | cv2.VideoCapture | None = None,
    ) -> Iterator[np.ndarray]:
        ensure_output_directories(self.config)
        video_source = VideoSource(source or self.config.runtime.input_video)
        metadata = video_source.open()
        frames_processed = 0
        source_frame_index = 0
        last_yielded_at = 0.0

        try:
            while True:
                frame = video_source.read()
                if frame is None:
                    break
                if not self._should_process_frame(source_frame_index):
                    source_frame_index += 1
                    continue

                annotated = self._process_frame(
                    frame,
                    metadata=metadata,
                    frame_index=source_frame_index,
                )
                self._enforce_fps_limit(last_yielded_at)
                if self.config.runtime_options.show:
                    cv2.imshow("traffic-monitor", annotated)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
                yield annotated
                last_yielded_at = perf_counter()
                frames_processed += 1
                source_frame_index += 1
                if (
                    self.config.runtime_options.frame_limit is not None
                    and frames_processed >= self.config.runtime_options.frame_limit
                ):
                    break
        finally:
            self.recorder.flush()
            video_source.close()
            if self.config.runtime_options.show:
                cv2.destroyAllWindows()

    def _process_frame(
        self,
        frame: np.ndarray,
        *,
        metadata,
        frame_index: int,
    ) -> np.ndarray:
        fps = self.config.effective_fps(metadata.fps)
        context = FrameContext(
            frame_index=frame_index,
            fps=fps,
            width=metadata.width,
            height=metadata.height,
            timestamp_seconds=frame_index / fps,
        )
        detections = self._detect(frame)
        tracks = self.track_manager.update(context, detections)
        lane_metrics = self.lane_assignment.evaluate(tracks, context)
        signal_snapshot = self.signal_state_machine.update(
            context.timestamp_seconds,
            lane_metrics.lane_metrics,
            emergency_lane=lane_metrics.emergency_lane,
        )
        if self.enforcement_enabled:
            self.rider_association.assign_riders(tracks)
            self.helmet_analyzer.enrich_tracks(frame, tracks)
            self.face_capture.enrich_tracks(frame, tracks)
            self.plate_recognizer.enrich_tracks(frame, tracks)
            findings_by_track = self.violation_engine.evaluate(context, tracks)
            new_findings = self.violation_engine.new_findings
        else:
            findings_by_track = {}
            new_findings = {}
        self.last_context = context
        self.last_tracks = list(tracks)
        self.last_findings_by_track = findings_by_track
        self.last_new_findings = new_findings
        self.last_frame = frame.copy()
        self.last_traffic_state = lane_metrics.to_dict()
        self.last_traffic_state["signal"] = signal_snapshot.to_dict()

        if self.config.runtime_options.overlay_mode == "traffic_control":
            annotated = annotate_traffic_control_frame(
                frame,
                context,
                self.lane_assignment.rois,
                self.last_traffic_state,
            )
        else:
            annotated = annotate_frame(
                frame,
                tracks,
                context,
                findings_by_track,
                line1_y_ratio=self.config.speed.line1_y,
                line2_y_ratio=self.config.speed.line2_y,
                hide_person_speed_labels=self.config.runtime_options.hide_person_speed_labels,
                suppress_associated_person_boxes=self.config.runtime_options.suppress_associated_person_boxes,
            )
        if self.enforcement_enabled:
            self.recorder.record(context, tracks, new_findings)
        return annotated

    def _detect(self, frame) -> list[InferenceDetection]:
        classes = self.config.primary_tracked_class_ids
        detection_frame, scale_x, scale_y = self._resize_for_detection(frame)
        detections = self.detector.track(
            detection_frame,
            classes=classes,
            tracker=self.config.tracking.tracker,
            persist=self.config.tracking.persist,
            verbose=False,
        )
        if scale_x == 1.0 and scale_y == 1.0:
            return detections
        return self._rescale_detections(
            detections,
            scale_x=scale_x,
            scale_y=scale_y,
        )

    def _should_process_frame(self, source_frame_index: int) -> bool:
        return source_frame_index % self.config.performance.frame_skip == 0

    def _resize_for_detection(
        self,
        frame: np.ndarray,
    ) -> tuple[np.ndarray, float, float]:
        target = self.config.performance.resolution
        if target is None:
            return frame, 1.0, 1.0
        target_width, target_height = target
        if target_width <= 0 or target_height <= 0:
            return frame, 1.0, 1.0
        source_height, source_width = frame.shape[:2]
        if source_width == target_width and source_height == target_height:
            return frame, 1.0, 1.0
        resized = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_LINEAR)
        scale_x = source_width / target_width
        scale_y = source_height / target_height
        return resized, scale_x, scale_y

    def _rescale_detections(
        self,
        detections: list[InferenceDetection],
        *,
        scale_x: float,
        scale_y: float,
    ) -> list[InferenceDetection]:
        rescaled: list[InferenceDetection] = []
        for detection in detections:
            x1, y1, x2, y2 = detection.xyxy
            rescaled.append(
                InferenceDetection(
                    xyxy=(x1 * scale_x, y1 * scale_y, x2 * scale_x, y2 * scale_y),
                    confidence=detection.confidence,
                    class_id=detection.class_id,
                    class_name=detection.class_name,
                    track_id=detection.track_id,
                )
            )
        return rescaled

    def _enforce_fps_limit(self, last_yielded_at: float) -> None:
        fps_limit = self.config.performance.fps_limit
        if fps_limit is None or fps_limit <= 0 or last_yielded_at <= 0.0:
            return
        target_interval = 1.0 / fps_limit
        elapsed = perf_counter() - last_yielded_at
        remaining = target_interval - elapsed
        if remaining > 0:
            sleep(remaining)


def frame_generator(
    source: Path | str | cv2.VideoCapture,
    config: TrafficMonitoringConfig | None = None,
) -> Iterator[np.ndarray]:
    pipeline = TrafficMonitoringPipeline(build_default_config() if config is None else config)
    yield from pipeline.frame_generator(source)
