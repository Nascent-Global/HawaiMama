from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Iterator

import cv2
import numpy as np

from traffic_monitoring.annotations import annotate_frame
from traffic_monitoring.config import (
    build_default_config,
    TrafficMonitoringConfig,
    ensure_output_directories,
)
from traffic_monitoring.detectors import EasyOCRReader, InferenceDetection, YOLODetector
from traffic_monitoring.domain import FrameContext
from traffic_monitoring.persistence import ViolationRecorder
from traffic_monitoring.secondary import (
    FaceCaptureAnalyzer,
    HelmetComplianceAnalyzer,
)
from traffic_monitoring.tracking import (
    PlateRecognizer,
    RiderAssociationEngine,
    TrackManager,
)
from traffic_monitoring.video import VideoSource
from traffic_monitoring.violations import ViolationEngine


@dataclass(frozen=True, slots=True)
class RunSummary:
    frames_processed: int
    elapsed_seconds: float
    output_video: Path | None = None


class TrafficMonitoringPipeline:
    def __init__(self, config: TrafficMonitoringConfig) -> None:
        self.config = config
        plate_detector_path = config.models.plate_detector
        plate_enabled = plate_detector_path.exists()
        helmet_enabled = config.models.helmet_detector.exists()
        face_enabled = bool(config.models.face_detector and config.models.face_detector.exists())
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
        self.plate_recognizer = PlateRecognizer(config, self.plate_detector, self.ocr_reader)
        self.helmet_analyzer = HelmetComplianceAnalyzer(config, self.helmet_detector)
        self.face_capture = FaceCaptureAnalyzer(config, self.face_detector)
        self.violation_engine = ViolationEngine(config)
        self.recorder = ViolationRecorder(config.runtime.records_path)
        self.last_context: FrameContext | None = None
        self.last_tracks = []
        self.last_findings_by_track: dict[int, list] = {}
        self.last_new_findings: dict[int, list] = {}
        self.last_frame: np.ndarray | None = None

    def run(self) -> RunSummary:
        ensure_output_directories(self.config)
        started_at = perf_counter()
        frames_processed = sum(1 for _ in self.frame_generator())

        return RunSummary(
            frames_processed=frames_processed,
            elapsed_seconds=perf_counter() - started_at,
            output_video=None,
        )

    def frame_generator(
        self,
        source: Path | str | cv2.VideoCapture | None = None,
    ) -> Iterator[np.ndarray]:
        ensure_output_directories(self.config)
        video_source = VideoSource(source or self.config.runtime.input_video)
        metadata = video_source.open()
        frames_processed = 0

        try:
            while True:
                frame = video_source.read()
                if frame is None:
                    break

                annotated = self._process_frame(
                    frame,
                    metadata=metadata,
                    frame_index=frames_processed,
                )
                if self.config.runtime_options.show:
                    cv2.imshow("traffic-monitor", annotated)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
                yield annotated
                frames_processed += 1
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
        self.rider_association.assign_riders(tracks)
        self.helmet_analyzer.enrich_tracks(frame, tracks)
        self.face_capture.enrich_tracks(frame, tracks)
        self.plate_recognizer.enrich_tracks(frame, tracks)
        findings_by_track = self.violation_engine.evaluate(context, tracks)
        self.last_context = context
        self.last_tracks = list(tracks)
        self.last_findings_by_track = findings_by_track
        self.last_new_findings = self.violation_engine.new_findings
        self.last_frame = frame.copy()

        annotated = annotate_frame(
            frame,
            tracks,
            context,
            findings_by_track,
            line1_y_ratio=self.config.speed.line1_y,
            line2_y_ratio=self.config.speed.line2_y,
        )
        self.recorder.record(context, tracks, self.violation_engine.new_findings)
        return annotated

    def _detect(self, frame) -> list[InferenceDetection]:
        classes = self.config.primary_tracked_class_ids
        return self.detector.track(
            frame,
            classes=classes,
            tracker=self.config.tracking.tracker,
            persist=self.config.tracking.persist,
            verbose=False,
        )


def frame_generator(
    source: Path | str | cv2.VideoCapture,
    config: TrafficMonitoringConfig | None = None,
) -> Iterator[np.ndarray]:
    pipeline = TrafficMonitoringPipeline(build_default_config() if config is None else config)
    yield from pipeline.frame_generator(source)
