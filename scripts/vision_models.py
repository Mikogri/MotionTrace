"""Install pinned local model snapshots; verification never contacts the Hub."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import urllib.request


MODELS = {
    "xclip": {
        "id": "microsoft/xclip-base-patch16",
        "revision": "d6184e3fd8780d04c85d0f1eabe5f94bf44d98f6",
        "license": "MIT",
        "notices": {
            "LICENSE": "https://raw.githubusercontent.com/microsoft/VideoX/1744b2159c3d11694f94dab4fcde8660c685e79a/LICENSE",
            "NOTICE.md": "https://raw.githubusercontent.com/microsoft/VideoX/1744b2159c3d11694f94dab4fcde8660c685e79a/notice.md",
        },
    },
    "grounding_dino": {
        "id": "IDEA-Research/grounding-dino-tiny",
        "revision": "a2bb814dd30d776dcf7e30523b00659f4f141c71",
        "license": "Apache-2.0",
        "notices": {
            "LICENSE": "https://raw.githubusercontent.com/IDEA-Research/GroundingDINO/856dde20aee659246248e20734ef9ba5214f5e44/LICENSE",
        },
    },
    "sam2": {
        "id": "facebook/sam2.1-hiera-small",
        "revision": "ee5bba1d82bb8749febdf90f45e84b687142ba03",
        "license": "Apache-2.0",
        "notices": {
            "LICENSE": "https://raw.githubusercontent.com/facebookresearch/sam2/2b90b9f5ceec907a1c18123530e92e794ad901a4/LICENSE",
        },
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def download(root: Path) -> None:
    # Imported only on the explicitly online installation path.
    from huggingface_hub import HfApi, snapshot_download

    root.mkdir(parents=True, exist_ok=True)
    manifest = {"backendVersion": "1", "models": {}}
    for key, spec in MODELS.items():
        info = HfApi().model_info(spec["id"], revision=spec["revision"])
        if info.sha != spec["revision"]:
            raise ValueError(f"Unexpected revision for {spec['id']}: {info.sha}")
        names = [entry.rfilename for entry in info.siblings]
        has_safetensors = any(name.endswith(".safetensors") for name in names)
        allowed = [name for name in names if not name.startswith(".") and not (
            name.endswith((".pt", ".onnx", ".h5", ".msgpack"))
            or (has_safetensors and name.endswith(".bin"))
        )]
        destination = root / key
        snapshot_download(
            repo_id=spec["id"], revision=spec["revision"], local_dir=destination,
            allow_patterns=allowed, max_workers=2,
        )
        sources = {
            name: f"https://huggingface.co/{spec['id']}/resolve/{spec['revision']}/{name}"
            for name in allowed
        }
        for name, url in spec["notices"].items():
            target = destination / "upstream_notices" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(url, timeout=60) as response:
                content = response.read()
            if len(content) < 100:
                raise ValueError(f"Incomplete license response: {url}")
            target.write_bytes(content)
            sources[target.relative_to(destination).as_posix()] = url
        files = []
        for name, url in sorted(sources.items()):
            target = destination / name
            files.append({"path": name, "size": target.stat().st_size,
                          "sha256": sha256(target), "source": url})
        manifest["models"][key] = {
            "id": spec["id"], "revision": spec["revision"],
            "path": str(destination.resolve()), "license": spec["license"],
            "source": f"https://huggingface.co/{spec['id']}/tree/{spec['revision']}",
            "files": files,
        }
        print(f"Installed {key}: {sum(item['size'] for item in files):,} bytes", flush=True)
    write_json(root / "manifest.json", manifest)


def verify(root: Path) -> None:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("backendVersion") != "1" or set(manifest.get("models", {})) != set(MODELS):
        raise ValueError("Incompatible or incomplete model manifest; run setup-vision.ps1")
    for key, spec in MODELS.items():
        item = manifest["models"][key]
        if item.get("id") != spec["id"] or item.get("revision") != spec["revision"]:
            raise ValueError(f"Unapproved model revision: {key}")
        destination = (root / key).resolve()
        if Path(item["path"]).resolve() != destination or not item.get("files"):
            raise ValueError(f"Invalid model path/file inventory: {key}")
        listed = {entry["path"] for entry in item["files"]}
        if "config.json" not in listed or not any(name.endswith((".safetensors", ".bin")) for name in listed):
            raise ValueError(f"Model config or weights missing from manifest: {key}")
        for entry in item["files"]:
            target = (destination / entry["path"]).resolve()
            if not target.is_relative_to(destination):
                raise ValueError(f"Path outside model directory: {entry['path']}")
            if not target.is_file() or target.stat().st_size != entry["size"] or sha256(target) != entry["sha256"]:
                raise ValueError(f"Missing or modified model file: {target}. Run setup-vision.ps1.")
        print(f"Verified {key}: {len(item['files'])} files", flush=True)


def audit_environment(root: Path) -> None:
    """Keep actual installed metadata and bundled notices; licenses are not inferred."""
    destination = root / "dependency_notices"
    destination.mkdir(parents=True, exist_ok=True)
    packages = []
    for distribution in sorted(importlib.metadata.distributions(), key=lambda d: d.metadata["Name"].lower()):
        name, version = distribution.metadata["Name"], distribution.version
        notices = []
        for file in distribution.files or ():
            relative = Path(str(file))
            if not any(part.endswith((".dist-info", ".egg-info")) for part in relative.parts):
                continue
            if not any(marker in relative.name.lower() for marker in ("license", "notice", "copying")):
                continue
            source = Path(distribution.locate_file(file))
            if not source.is_file():
                continue
            target = destination / name / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            notices.append({"path": target.relative_to(root).as_posix(), "sha256": sha256(target)})
        packages.append({"name": name, "version": version,
                         "licenseExpression": distribution.metadata.get("License-Expression"),
                         "licenseMetadata": distribution.metadata.get("License"),
                         "licenseClassifiers": [c for c in distribution.metadata.get_all("Classifier", []) if c.startswith("License ::")],
                         "notices": notices})
    write_json(root / "dependencies.json", packages)
    print(f"Saved metadata and bundled notices for {len(packages)} installed packages", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "MotionTrace/models/vision")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--download", action="store_true")
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--audit-environment", action="store_true")
    args = parser.parse_args()
    if args.download:
        download(args.root.resolve())
        verify(args.root.resolve())
    elif args.verify:
        verify(args.root.resolve())
    else:
        audit_environment(args.root.resolve())


if __name__ == "__main__":
    main()
