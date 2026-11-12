"""Complete vision-result reuse, with byte-verified segmentation assets."""
import hashlib
import json
from pathlib import Path


def file_digest(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _mask_paths(result, root):
    paths = set()
    for frame in result["frames"]:
        for item in frame["objects"]:
            value = item.get("maskPath")
            if item["trackingState"] == "Tracked" and not value:
                raise ValueError("Tracked object is missing its segmentation mask")
            if value:
                path = Path(value).resolve()
                if not path.is_relative_to(root / "masks") or not path.is_file():
                    raise ValueError("Missing mask or mask outside this analysis cache")
                paths.add(path)
    return paths


def record_cache_assets(root, result, key, write_json):
    """Write the completion receipt last; partial/cancelled runs cannot be hits."""
    root = Path(root).resolve()
    paths = _mask_paths(result, root) | {root / "result.json"}
    assets = {str(path.relative_to(root)): dict(size=path.stat().st_size, sha256=file_digest(path))
              for path in sorted(paths)}
    write_json(root / "complete.json", dict(version=1, cacheKey=key, assets=assets))


def load_cached_result(root, key):
    """A cache is disposable: any inconsistency reruns analysis instead of serving it."""
    root = Path(root).resolve()
    try:
        receipt = json.loads((root / "complete.json").read_text(encoding="utf-8"))
        if receipt["version"] != 1 or receipt["cacheKey"] != key:
            return None
        assets = receipt["assets"]
        if "result.json" not in assets:
            return None
        for relative, expected in assets.items():
            path = (root / relative).resolve()
            if (not path.is_relative_to(root) or not path.is_file()
                    or path.stat().st_size != expected["size"]
                    or file_digest(path) != expected["sha256"]):
                return None
        result = json.loads((root / "result.json").read_text(encoding="utf-8"))
        if result["schemaVersion"] != 4 or result["visionMetadata"]["cacheKey"] != key:
            return None
        required = {str(path.relative_to(root)) for path in _mask_paths(result, root)} | {"result.json"}
        if required != set(assets):
            return None
        return result
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None
