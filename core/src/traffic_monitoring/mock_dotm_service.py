from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True, slots=True)
class VehicleRecord:
    plate_number: str
    owner_name: str
    address: str
    vehicle_type: str
    color: str
    registration_date: str
    contact_number: str = "9800000000"
    is_mock_data: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def normalize_plate(plate: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", plate.upper())


class MockDoTMService:
    def __init__(self, registry_path: Path) -> None:
        self.registry_path = registry_path
        raw_registry = json.loads(registry_path.read_text(encoding="utf-8"))
        self._records = {
            normalize_plate(plate): VehicleRecord(**payload)
            for plate, payload in raw_registry.items()
        }

    def get_vehicle_details(self, plate: str) -> VehicleRecord | None:
        normalized = normalize_plate(plate)
        if not normalized:
            return None
        return self._records.get(normalized)

    def choose_demo_record(self, seed: str | None = None) -> VehicleRecord:
        records = list(self._records.values())
        if not records:
            raise RuntimeError("Mock DoTM registry is empty")
        if not seed:
            return records[0]
        index = int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16) % len(records)
        return records[index]

    def api_response(self, plate: str) -> dict[str, object]:
        normalized = normalize_plate(plate)
        record = self.get_vehicle_details(plate)
        if record is None:
            return {
                "plate": normalized,
                "message": "not found",
                "is_mock_data": True,
            }
        return {
            "plate": normalized,
            **record.to_dict(),
        }


@lru_cache(maxsize=4)
def load_mock_dotm_service(project_root: Path) -> MockDoTMService:
    return MockDoTMService(project_root / "data" / "mock_vehicle_registry.json")

