"""Cache integrity checks require no models, CUDA, or image libraries."""
import json
from pathlib import Path
import tempfile
import unittest

from vision.cache import file_digest, load_cached_result, record_cache_assets


def write_json(path, value):
    Path(path).write_text(json.dumps(value), encoding="utf-8")


class VisionResultCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / "masks").mkdir()
        self.mask = self.root / "masks" / "frame.png"
        self.mask.write_bytes(b"segmentation bytes")
        self.key = "video-pose-model-config-correction-source-device-dependency-identity"
        self.result = dict(schemaVersion=4, visionMetadata=dict(cacheKey=self.key), frames=[dict(
            objects=[dict(trackingState="Tracked", maskPath=str(self.mask))])])
        self.save()

    def save(self):
        write_json(self.root / "result.json", self.result)
        record_cache_assets(self.root, self.result, self.key, write_json)

    def test_complete_cache_returns_same_measurements(self):
        self.assertEqual(self.result, load_cached_result(self.root, self.key))

    def test_identity_change_invalidates_cache(self):
        self.assertIsNone(load_cached_result(self.root, self.key + "changed"))

    def test_cancelled_incomplete_run_is_not_reused(self):
        (self.root / "complete.json").unlink()
        self.assertIsNone(load_cached_result(self.root, self.key))

    def test_missing_mask_invalidates_cache(self):
        self.mask.unlink()
        self.assertIsNone(load_cached_result(self.root, self.key))

    def test_same_size_mask_corruption_invalidates_cache(self):
        self.mask.write_bytes(b"x" * self.mask.stat().st_size)
        self.assertIsNone(load_cached_result(self.root, self.key))

    def test_changed_result_invalidates_cache(self):
        self.result["frames"][0]["objects"][0]["confidence"] = .123
        write_json(self.root / "result.json", self.result)
        self.assertIsNone(load_cached_result(self.root, self.key))

    def test_invalid_receipt_is_a_cache_miss(self):
        (self.root / "complete.json").write_text("{incomplete", encoding="utf-8")
        self.assertIsNone(load_cached_result(self.root, self.key))

    def test_unrecorded_mask_is_not_accepted(self):
        receipt = json.loads((self.root / "complete.json").read_text())
        receipt["assets"].pop(str(self.mask.relative_to(self.root)))
        write_json(self.root / "complete.json", receipt)
        self.assertIsNone(load_cached_result(self.root, self.key))

    def test_external_mask_cannot_be_recorded(self):
        self.result["frames"][0]["objects"][0]["maskPath"] = str(self.root / "result.json")
        with self.assertRaises(ValueError):
            self.save()

    def test_tracked_object_requires_mask(self):
        self.result["frames"][0]["objects"][0]["maskPath"] = None
        with self.assertRaises(ValueError):
            self.save()

    def test_negative_result_without_masks_is_reusable(self):
        self.result["frames"][0]["objects"] = [dict(trackingState="Lost", maskPath=None)]
        self.save()
        self.assertEqual(self.result, load_cached_result(self.root, self.key))

    def test_result_identity_is_checked_separately(self):
        self.result["visionMetadata"]["cacheKey"] = "wrong"
        self.save()
        self.assertIsNone(load_cached_result(self.root, self.key))

    def test_receipt_cannot_traverse_outside_root(self):
        receipt = json.loads((self.root / "complete.json").read_text())
        receipt["assets"]["../outside.json"] = dict(size=0, sha256=file_digest(self.mask))
        write_json(self.root / "complete.json", receipt)
        self.assertIsNone(load_cached_result(self.root, self.key))


if __name__ == "__main__":
    unittest.main()
