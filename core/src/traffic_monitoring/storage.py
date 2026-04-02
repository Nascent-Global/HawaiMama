from __future__ import annotations

import mimetypes
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import boto3
from dotenv import load_dotenv


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class ObjectStorageSettings:
    use_s3: bool
    local_root: Path
    local_url_prefix: str
    s3_bucket_name: str
    s3_region: str
    s3_access_key_id: str
    s3_secret_access_key: str
    s3_endpoint_url: str | None
    s3_public_base_url: str | None
    s3_prefix: str


class ObjectStorage:
    provider: str

    def put_bytes(self, key: str, data: bytes, *, content_type: str) -> str:
        raise NotImplementedError

    def put_file(self, key: str, source_path: Path, *, content_type: str | None = None) -> str:
        raise NotImplementedError


class LocalObjectStorage(ObjectStorage):
    provider = "local"

    def __init__(self, root: Path, *, url_prefix: str = "/wwwroots") -> None:
        self.root = root
        self.url_prefix = url_prefix.rstrip("/")
        self.root.mkdir(parents=True, exist_ok=True)

    def put_bytes(self, key: str, data: bytes, *, content_type: str) -> str:
        destination = self.root / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return self._public_url(key)

    def put_file(self, key: str, source_path: Path, *, content_type: str | None = None) -> str:
        destination = self.root / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
        return self._public_url(key)

    def _public_url(self, key: str) -> str:
        return f"{self.url_prefix}/{key.replace(os.sep, '/')}"


class S3ObjectStorage(ObjectStorage):
    provider = "s3"

    def __init__(self, settings: ObjectStorageSettings) -> None:
        self.settings = settings
        self.client = boto3.client(
            "s3",
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            region_name=settings.s3_region or None,
            endpoint_url=settings.s3_endpoint_url or None,
        )

    def put_bytes(self, key: str, data: bytes, *, content_type: str) -> str:
        self.client.put_object(
            Bucket=self.settings.s3_bucket_name,
            Key=self._prefixed_key(key),
            Body=data,
            ContentType=content_type,
        )
        return self._public_url(key)

    def put_file(self, key: str, source_path: Path, *, content_type: str | None = None) -> str:
        extra_args = {"ContentType": content_type} if content_type else None
        self.client.upload_file(
            str(source_path),
            self.settings.s3_bucket_name,
            self._prefixed_key(key),
            ExtraArgs=extra_args,
        )
        return self._public_url(key)

    def _prefixed_key(self, key: str) -> str:
        prefix = self.settings.s3_prefix.strip("/")
        if prefix:
            return f"{prefix}/{key}"
        return key

    def _public_url(self, key: str) -> str:
        final_key = self._prefixed_key(key)
        if self.settings.s3_public_base_url:
            return f"{self.settings.s3_public_base_url.rstrip('/')}/{quote(final_key, safe='/')}"
        if self.settings.s3_endpoint_url:
            return (
                f"{self.settings.s3_endpoint_url.rstrip('/')}/"
                f"{self.settings.s3_bucket_name}/{quote(final_key, safe='/')}"
            )
        if self.settings.s3_region:
            return (
                f"https://{self.settings.s3_bucket_name}.s3."
                f"{self.settings.s3_region}.amazonaws.com/{quote(final_key, safe='/')}"
            )
        return f"https://{self.settings.s3_bucket_name}.s3.amazonaws.com/{quote(final_key, safe='/')}"


def load_object_storage_settings(project_root: Path) -> ObjectStorageSettings:
    load_dotenv(project_root / ".env", override=False)
    local_root = Path(os.environ.get("LOCAL_OBJECT_STORAGE_ROOT", "wwwroots"))
    if not local_root.is_absolute():
        local_root = project_root / local_root
    return ObjectStorageSettings(
        use_s3=_env_bool("USE_S3", default=False),
        local_root=local_root.resolve(),
        local_url_prefix=os.environ.get("LOCAL_OBJECT_STORAGE_URL_PREFIX", "/wwwroots"),
        s3_bucket_name=os.environ.get("S3_BUCKET_NAME", ""),
        s3_region=os.environ.get("S3_REGION", ""),
        s3_access_key_id=os.environ.get("S3_ACCESS_KEY_ID", ""),
        s3_secret_access_key=os.environ.get("S3_SECRET_ACCESS_KEY", ""),
        s3_endpoint_url=os.environ.get("S3_ENDPOINT_URL") or None,
        s3_public_base_url=os.environ.get("S3_PUBLIC_BASE_URL") or None,
        s3_prefix=os.environ.get("S3_PREFIX", "traffic-monitoring"),
    )


def build_object_storage(project_root: Path) -> ObjectStorage:
    settings = load_object_storage_settings(project_root)
    if settings.use_s3:
        if not settings.s3_bucket_name:
            raise ValueError("S3_BUCKET_NAME is required when USE_S3=true")
        return S3ObjectStorage(settings)
    return LocalObjectStorage(settings.local_root, url_prefix=settings.local_url_prefix)


def guess_content_type(path: Path, *, default: str) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or default
