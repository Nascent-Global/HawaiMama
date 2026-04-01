from __future__ import annotations

import argparse
from pathlib import Path

from traffic_monitoring.config import config_from_namespace
from traffic_monitoring.pipeline import TrafficMonitoringPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="traffic-monitor",
        description="Run the traffic monitoring pipeline on a video file.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("input.mp4"),
        help="Path to the input video.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/annotated.mp4"),
        help="Path for the annotated output video.",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Display the annotated frames while processing.",
    )
    parser.add_argument(
        "--primary-model",
        type=str,
        default="yolov8n.pt",
        help="Primary YOLO model path or model name.",
    )
    parser.add_argument(
        "--plate-model",
        type=str,
        default="",
        help="Optional YOLO plate detector path.",
    )
    parser.add_argument(
        "--helmet-model",
        type=str,
        default="",
        help="Optional helmet detector path.",
    )
    parser.add_argument(
        "--overspeed-threshold",
        type=float,
        default=60.0,
        help="Overspeed threshold in km/h.",
    )
    parser.add_argument(
        "--speed-scale",
        type=float,
        default=1.0,
        help="Deprecated and currently ignored; speed uses reference line timing.",
    )
    parser.add_argument(
        "--fps-override",
        type=float,
        default=12.0,
        help="Effective FPS to use for speed estimation on this camera setup.",
    )
    parser.add_argument(
        "--frame-limit",
        type=int,
        default=0,
        help="Optional maximum number of frames to process for smoke testing.",
    )
    parser.add_argument(
        "--helmet-debug",
        action="store_true",
        help="Draw helmet and no-helmet debug detections with confidence scores.",
    )
    parser.add_argument(
        "--frame-skip",
        type=int,
        default=1,
        help="Process every Nth frame for better throughput.",
    )
    parser.add_argument(
        "--resolution",
        type=str,
        default="",
        help="Optional inference resolution as WIDTHxHEIGHT, for example 1280x720.",
    )
    parser.add_argument(
        "--fps-limit",
        type=float,
        default=12.0,
        help="Maximum annotated output FPS for streaming or local display.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = config_from_namespace(args)
    summary = TrafficMonitoringPipeline(config).run()
    print(f"Processed {summary.frames_processed} frames in {summary.elapsed_seconds:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
