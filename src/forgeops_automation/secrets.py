from __future__ import annotations

import base64
import json
from typing import Any, Optional

try:  # pragma: no cover
    import boto3  # type: ignore
except Exception:  # pragma: no cover
    boto3 = None


class SecretResolver:
    """Resolves secret references in variable mappings."""

    def __init__(self):
        self._cache: dict[tuple[str, Optional[str]], Any] = {}

    def resolve(self, values: dict[str, Any]) -> dict[str, Any]:
        return {k: self._resolve_value(v) for k, v in values.items()}

    def _resolve_value(self, value: Any) -> Any:
        if isinstance(value, dict):
            if "aws_secret" in value:
                return self._resolve_aws_secret(value)
            return {k: self._resolve_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._resolve_value(v) for v in value]
        return value

    def _resolve_aws_secret(self, spec: dict[str, Any]) -> Any:
        if boto3 is None:
            raise RuntimeError("boto3 is required to resolve aws_secret references")
        name = str(spec["aws_secret"])
        key = spec.get("key")
        cache_key = (name, key if key is None else str(key))
        if cache_key in self._cache:
            return self._cache[cache_key]

        client = boto3.client("secretsmanager")
        response = client.get_secret_value(SecretId=name)
        secret_str = response.get("SecretString")
        if secret_str is None:
            binary = response.get("SecretBinary")
            if binary is None:
                raise RuntimeError(f"Secret {name} has no SecretString or SecretBinary")
            secret_str = base64.b64decode(binary).decode()

        value: Any = secret_str
        if key is not None:
            payload = json.loads(secret_str)
            value = payload[str(key)]

        self._cache[cache_key] = value
        return value
