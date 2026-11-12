import unittest
import hashlib,json,tempfile
from pathlib import Path
from motiontrace_ai.cache import inference_configuration,pose_fingerprint,cache_key,read_pose_cache,configuration_sources


class CacheTests(unittest.TestCase):
    def test_valid_digest_cannot_make_invalid_cache_shape_usable(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'pose.json'
            path.write_text('[]')
            sidecar=path.with_suffix('.sha256.json')
            sidecar.write_text(json.dumps(dict(key='key',sha256=hashlib.sha256(path.read_bytes()).hexdigest())))
            self.assertIsNone(read_pose_cache(path,'key'))
            sidecar.write_text('[]')
            self.assertIsNone(read_pose_cache(path,'key'))

    def test_config_bases_and_model_alias_metadata_invalidate_fast_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'base.py').write_text('threshold=.2')
            (root/'model-index.yml').write_text('Import: old.yml')
            first=configuration_sources([root])
            (root/'base.py').write_text('threshold=.3')
            second=configuration_sources([root])
            self.assertNotEqual(first,second)
            (root/'model-index.yml').write_text('Import: new.yml')
            self.assertNotEqual(second,configuration_sources([root]))
            self.assertIsNone(configuration_sources([root/'missing']))

    def test_config_key_does_not_depend_on_dictionary_order(self):
        from mmengine.config import Config
        self.assertEqual(inference_configuration(Config(dict(a=1,b=2))),
                         inference_configuration(Config(dict(b=2,a=1))))
    def test_pose_cache_ignores_shaft_but_invalidates_pose_inputs(self):
        fields=('model','cropPadding','selected','tracker','device','video','pose','detector','configuration','detectorConfiguration','packages')
        original={k:k for k in fields}
        original.update(shaft='bar-v1',adapter={'analyze.py':'v1','motiontrace_ai/pose_pipeline.py':'pose-v1','motiontrace_ai/shaft_tracking.py':'bar-v1'})
        changed={**original,'shaft':'bar-v2','adapter':{**original['adapter'],'motiontrace_ai/shaft_tracking.py':'bar-v2'}}
        self.assertEqual(cache_key(pose_fingerprint(original)),cache_key(pose_fingerprint(changed)))
        for key in ('video','pose','detector','selected','configuration','cropPadding','device'):
            self.assertNotEqual(cache_key(pose_fingerprint(original)),cache_key(pose_fingerprint({**original,key:'changed'})))
        changed['adapter']['motiontrace_ai/pose_pipeline.py']='pose-v2'
        self.assertNotEqual(cache_key(pose_fingerprint(original)),cache_key(pose_fingerprint(changed)))

    def test_pose_cache_rejects_corruption_or_incomplete_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'pose.json'
            payload=dict(schema=1,confirmedIds=[1],frames=[dict(timestampSeconds=0,athletes=[])])
            path.write_text(json.dumps(payload))
            self.assertIsNone(read_pose_cache(path,'key'))
            path.with_suffix('.sha256.json').write_text(json.dumps(dict(key='key',sha256=hashlib.sha256(path.read_bytes()).hexdigest())))
            self.assertEqual(payload,read_pose_cache(path,'key'))
            self.assertIsNone(read_pose_cache(path,'other-key'))
            path.write_text('{}')
            self.assertIsNone(read_pose_cache(path,'key'))

    def test_runtime_visualizer_name_does_not_invalidate_inference_cache(self):
        from mmengine.config import Config
        first = Config(dict(model=dict(type='Detector'), visualizer=dict(name='visualizer-1')))
        second = Config(dict(model=dict(type='Detector'), visualizer=dict(name='visualizer-2')))
        self.assertEqual(inference_configuration(first), inference_configuration(second))
        self.assertIn('visualizer', first)

    def test_model_change_invalidates_cache(self):
        from mmengine.config import Config
        self.assertNotEqual(inference_configuration(Config(dict(model=dict(type='A')))),
                            inference_configuration(Config(dict(model=dict(type='B')))))
