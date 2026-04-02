from __future__ import annotations

import argparse
from pathlib import Path

import cv2

from traffic_monitoring.config import build_default_config
from traffic_monitoring.detectors import EasyOCRReader, YOLODetector
from traffic_monitoring.domain import BoundingBox
from traffic_monitoring.tracking import PlateRecognizer


def test_single_image_anpr(image_path: str | Path) -> None:
    config = build_default_config()
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Could not load image: {image_path}")

    if not config.models.plate_detector.exists():
        raise FileNotFoundError(f"Missing plate model: {config.models.plate_detector}")
    if not config.models.char_detector or not config.models.char_detector.exists():
        raise FileNotFoundError(f"Missing character model: {config.models.char_detector}")

    plate_detector = YOLODetector(
        config.models.plate_detector,
        confidence=config.detection.plate_confidence_threshold,
    )
    char_detector = YOLODetector(
        config.models.char_detector,
        confidence=config.detection.char_confidence_threshold,
    )
    ocr_reader = EasyOCRReader(list(config.ocr.languages))
    recognizer = PlateRecognizer(config, plate_detector, ocr_reader, char_detector)

    plate_detections = plate_detector.predict(image, verbose=False)
    annotated = image.copy()

    if not plate_detections:
        print("[anpr-test] no plate detected")
        cv2.imshow("ANPR Test", annotated)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
        return

    best_plate = max(plate_detections, key=lambda detection: detection.confidence)
    plate_bbox = BoundingBox(*best_plate.xyxy)
    px1, py1, px2, py2 = (int(value) for value in plate_bbox.as_tuple())
    cv2.rectangle(annotated, (px1, py1), (px2, py2), (0, 255, 255), 2)
    cv2.putText(
        annotated,
        f"plate {best_plate.confidence:.2f}",
        (px1, max(16, py1 - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 255, 255),
        2,
        cv2.LINE_AA,
    )

    plate_crop, plate_origin = recognizer._crop(image, plate_bbox)
    segmented_result = None
    full_result = None

    char_detections = char_detector.predict(plate_crop, verbose=False)
    ordered_chars = sorted(char_detections, key=lambda detection: detection.xyxy[0])
    for index, detection in enumerate(ordered_chars, start=1):
        char_bbox = BoundingBox(*detection.xyxy)
        char_crop, char_origin = recognizer._crop(plate_crop, char_bbox)
        cx1, cy1, cx2, cy2 = (int(value) for value in char_bbox.as_tuple())
        cv2.rectangle(
            annotated,
            (px1 + cx1, py1 + cy1),
            (px1 + cx2, py1 + cy2),
            (0, 200, 0),
            2,
        )
        cv2.putText(
            annotated,
            str(index),
            (px1 + cx1, max(16, py1 + cy1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 200, 0),
            2,
            cv2.LINE_AA,
        )

    segmented_result, _ = recognizer._read_segmented_plate_text(plate_crop)
    full_result, _ = recognizer._read_full_plate_text(plate_crop)

    print("[anpr-test] segmented OCR:", segmented_result)
    print("[anpr-test] full plate OCR:", full_result)
    print("[anpr-test] character boxes:", len(ordered_chars))

    overlay_lines = [
        f"Segmented: {segmented_result or 'None'}",
        f"Full OCR: {full_result or 'None'}",
    ]
    panel_x1 = 16
    panel_y1 = 16
    panel_x2 = 460
    panel_y2 = 74
    cv2.rectangle(annotated, (panel_x1, panel_y1), (panel_x2, panel_y2), (20, 20, 20), thickness=-1)
    cv2.rectangle(annotated, (panel_x1, panel_y1), (panel_x2, panel_y2), (255, 255, 255), thickness=2)
    baseline = panel_y1 + 22
    for line in overlay_lines:
        cv2.putText(
            annotated,
            line,
            (panel_x1 + 10, baseline),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        baseline += 24

    cv2.imshow("ANPR Test", annotated)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Test plate detection and OCR on a single image.")
    parser.add_argument("--image", required=True, type=Path, help="Path to the input image.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    test_single_image_anpr(args.image)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
