import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from comparison import analyze_session as session
from comparison.prepare import resolve_target
from comparison import prepare
from comparison.scheduler import PROVIDERS, job_budget, schedule


def pose_fixture():
    return dict(schemaVersion=3, video=dict(width=640,height=480,framesPerSecond=25,durationSeconds=.12),
        athletes=[dict(id=2)], frames=[dict(timestampSeconds=i*.04,athletes=[],shafts=[]) for i in range(3)])


class ComparisonSessionTests(unittest.TestCase):
    def test_completed_model_is_not_failed_by_an_unneeded_resource_probe(self):
        import time
        calls = []
        def sample():
            calls.append(True)
            if len(calls) > 2:
                raise RuntimeError('GPU probe unavailable while no model is waiting')
            return dict(gpuMiB=7000, ramMiB=16000)
        def execute(job):
            time.sleep(.3)
            return 'validated-result'
        result = schedule([job_budget('tapnextpp', 10)], execute, lambda *a: None, lambda: False, sample=sample)
        self.assertEqual(('TrackingReady', 'validated-result'), result['tapnextpp'])
        self.assertEqual(2, len(calls))

    def test_points_only_preparation_declares_that_pose_inference_was_not_used(self):
        from comparison import points_prepare
        class Frames:
            width, height, fps, end = 640, 480, 25., .08
            def __iter__(self): return iter([(0., None), (.04, None)])
            def close(self): pass
        with patch.object(points_prepare, 'VideoDecoder', return_value=Frames()):
            result = points_prepare.timeline('fixture.mp4')
        self.assertEqual('not-used-points-only', result['versions']['poseModelVersion'])
        self.assertFalse(result['athletes'])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.target=dict(targetId='axis',athleteTrackId=2,timestampSeconds=0.,point=dict(x=123.,y=234.),
                         box=dict(x=80.,y=200.,width=200.,height=100.))
        (self.root/'target.json').write_text(json.dumps(self.target))
        (self.root/'video.mp4').write_bytes(b'video identity')
        (self.root/'python.exe').write_bytes(b'interpreter marker')
        models=self.root/'models';models.mkdir();(models/'manifest.json').write_text('{}')
        self.args=SimpleNamespace(input=str(self.root/'video.mp4'),target=str(self.root/'target.json'),
            output=str(self.root/'session.json'),cache=str(self.root/'cache'),pose_python=str(self.root/'python.exe'),
            vision_python=str(self.root/'python.exe'),samurai_python=str(self.root/'python.exe'),points_python=str(self.root/'python.exe'),
            models_root=str(models),samurai_models_root=str(models),points_models_root=str(models),
            providers='',pose_model='rtmpose',pose_weights='',crop_padding=.2,device='cuda:0')
        session.STOP.clear()

    def tearDown(self):
        session.STOP.clear();self.temp.cleanup()

    def execute_session(self, calls, invalid_provider=None):
        capacity=lambda:dict(gpuMiB=7000,gpuTotalMiB=8192,ramMiB=16000,ramTotalMiB=32000)
        def process(command,provider=None):
            calls.append((command,provider))
            output=Path(command[command.index('--output')+1]);output.parent.mkdir(parents=True,exist_ok=True)
            result=pose_fixture()
            if Path(command[2]).name=='prepare.py':
                resolved=resolve_target(result,self.target)
                Path(command[command.index('--resolved-target')+1]).write_text(json.dumps(resolved))
            if provider:
                result['provider']=provider;result['schemaVersion']=4
                for frame in result['frames']:frame['objects']=[]
                if provider==invalid_provider:result['frames'].pop()
                raw=output.parent/'raw.json';raw.write_text('{"raw":true}')
                result['rawObservationsPath']=str(raw)
            output.write_text(json.dumps(result))
        def schedule_cpu(jobs,execute,report,cancelled):
            return schedule(jobs,execute,report,cancelled,sample=capacity)
        with patch.object(session,'resources',side_effect=capacity),patch.object(session,'process',side_effect=process),\
             patch('comparison.tap_backends.installation',return_value=(self.root/'weights.pt',{})),\
             patch.object(session,'schedule',side_effect=schedule_cpu),patch.object(session,'emit'):
            session.run(self.args)
        return json.loads(Path(self.args.output).read_text())

    def test_analyze_all_four_once_no_custom_and_warm_cache_no_inference(self):
        calls=[];result=self.execute_session(calls)
        self.assertEqual(set(PROVIDERS),{provider for _,provider in calls if provider})
        self.assertEqual(6,len(calls)) # shared pose + classification + four trackers
        pose=calls[0][0]
        self.assertEqual('pose_only',pose[pose.index('--barbell-provider')+1])
        self.assertNotIn('custom_barbell',json.dumps(calls))
        self.assertTrue(all(row['status']=='TrackingReady' for row in result['providers']))
        calls.clear();second=self.execute_session(calls)
        self.assertEqual([],calls)
        self.assertEqual(result['sessionId'],second['sessionId'])

    def test_two_points_force_only_tapnext_even_if_legacy_providers_requested(self):
        self.target.pop('point')
        self.target.pop('box')
        self.target.update(initializationVersion=2, points=[dict(x=120., y=220.), dict(x=400., y=220.)])
        Path(self.args.target).write_text(json.dumps(self.target))
        self.args.providers=','.join(PROVIDERS)
        calls=[]; result=self.execute_session(calls)
        self.assertEqual(['tapnextpp'], [p for _,p in calls if p])
        self.assertEqual(['tapnextpp'], [r['providerId'] for r in result['providers']])

    def test_two_points_with_no_pose_owner_get_unique_synthetic_identity(self):
        pose=pose_fixture()
        target=dict(targetId='bar',athleteTrackId=0,timestampSeconds=0.,initializationVersion=2,
                    points=[dict(x=120.,y=220.),dict(x=400.,y=220.)])
        resolved=resolve_target(pose,target)
        self.assertEqual(target['points'],resolved['points'])
        self.assertNotIn('point',resolved)
        self.assertNotEqual(2,resolved['athleteTrackId'])
        self.assertTrue(resolved['syntheticOwner'])
        self.assertEqual('Marked barbell',pose['athletes'][-1]['displayName'])
        for points in ([], target['points'][:1], target['points']*2, [target['points'][0]]*2):
            with self.subTest(points=points),self.assertRaises(ValueError):
                resolve_target(pose,dict(target,points=points))

    def test_two_point_preparation_does_not_verify_or_invoke_object_detector(self):
        pose=pose_fixture()
        target=dict(targetId='bar',athleteTrackId=2,timestampSeconds=0.,initializationVersion=2,
                    points=[dict(x=120.,y=220.),dict(x=400.,y=220.)])
        pose_path=self.root/'pose.json';pose_path.write_text(json.dumps(pose))
        Path(self.args.target).write_text(json.dumps(target))
        (Path(self.args.models_root)/'manifest.json').write_text(json.dumps(dict(models=dict(xclip={}))))
        args=SimpleNamespace(**vars(self.args),pose_input=str(pose_path),resolved_target=str(self.root/'resolved.json'))
        verified=[];classified=[]
        pipeline=SimpleNamespace(verify_manifest=lambda *a,**k:verified.append(k['names']),
            classify_exercises=lambda *a:(classified.append(a) or []))
        # A detector module which cannot provide any detector is sufficient:
        # point-only initialization must never import or instantiate one.
        with patch.dict(sys.modules,{'vision.pipeline':pipeline,'vision.models':SimpleNamespace()}):
            prepare.run(args)
        self.assertEqual([('xclip',)],verified)
        self.assertEqual(1,len(classified))
        resolved=json.loads(Path(args.resolved_target).read_text())
        self.assertEqual(target['points'],resolved['points'])
        self.assertNotIn('box',resolved)

    def test_missing_tracker_frames_fail_only_that_model(self):
        result=self.execute_session([],invalid_provider='samurai')
        rows={row['providerId']:row for row in result['providers']}
        self.assertEqual('Failed',rows['samurai']['status'])
        self.assertIn('timeline',rows['samurai']['error'])
        self.assertEqual(3,sum(row['status']=='TrackingReady' for row in rows.values()))
        self.args.providers='tapnextpp'
        second=self.execute_session([])
        self.assertEqual('Failed',next(r for r in second['providers'] if r['providerId']=='samurai')['status'])

    def test_raw_asset_tamper_invalidates_one_provider_only(self):
        result=self.execute_session([])
        row=next(r for r in result['providers'] if r['providerId']=='tapnextpp')
        raw=next(p for p in row['assets'] if p.endswith('raw.json'))
        Path(raw).write_text('changed raw points')
        calls=[];self.execute_session(calls)
        self.assertEqual(['tapnextpp'],[p for _,p in calls])

    def test_manual_axis_required_never_replaced_by_box_center(self):
        target=copy.deepcopy(self.target);target.pop('point')
        with self.assertRaisesRegex(ValueError,'physical target'):
            resolve_target(pose_fixture(),target)
        resolved=resolve_target(pose_fixture(),self.target)
        self.assertEqual(dict(x=123.,y=234.),resolved['point'])

    def test_empty_rack_can_be_marked_before_lifter_arrives(self):
        pose = pose_fixture()
        pose['video']['durationSeconds'] = 1.2
        person = dict(athleteId=2, trackingState='Tracked', keypoints=[
            dict(joint='LeftWrist', x=125., y=234., confidence=.9)])
        pose['frames'] = [dict(timestampSeconds=i*.04, athletes=[] if i<10 else [person]) for i in range(30)]
        target = dict(self.target, athleteTrackId=0)
        resolved = resolve_target(pose, target)
        self.assertEqual(2, resolved['athleteTrackId'])
        self.assertEqual(0, resolved['frameIndex'])
        self.assertEqual(target['point'], resolved['point'])
        # A passer-by seen briefly is insufficient evidence.
        pose['frames'][12]['athletes'] = []
        pose['frames'][22]['athletes'] = []
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            resolve_target(pose, target)

    def test_delayed_owner_does_not_choose_between_two_lifters(self):
        pose = pose_fixture()
        pose['video']['durationSeconds'] = 1.2
        people = [dict(athleteId=i, trackingState='Tracked', keypoints=[
            dict(joint='LeftWrist', x=125., y=234., confidence=.9)]) for i in (2,3)]
        pose['frames'] = [dict(timestampSeconds=i*.04, athletes=[] if i<10 else people) for i in range(30)]
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            resolve_target(pose, dict(self.target, athleteTrackId=0))

    def test_identity_changes_for_point_pose_weights_source_checkpoint_but_not_calibration(self):
        model_roots={'tapnextpp':self.args.models_root}
        source=self.root/'sources';(source/'comparison').mkdir(parents=True)
        code=source/'comparison'/'adapter.py';code.write_text('v1')
        weights=self.root/'pose.pt';weights.write_bytes(b'v1');self.args.pose_weights=str(weights)
        def identity(target):return session.inference_identity(self.args,target,source,model_roots,{'tapnextpp':'python'})
        original=identity(self.target)
        calibrated=dict(self.target,calibration={'pixelsPerMeter':1000},calibrationVersion=2)
        self.assertEqual(original,identity(calibrated))
        moved=dict(self.target,point=dict(x=124.,y=234.))
        self.assertNotEqual(original,identity(moved))
        weights.write_bytes(b'v2');self.assertNotEqual(original,identity(self.target));weights.write_bytes(b'v1')
        code.write_text('v2');self.assertNotEqual(original,identity(self.target));code.write_text('v1')
        (Path(self.args.models_root)/'manifest.json').write_text('{"checkpoint":"v2"}')
        self.assertNotEqual(original,identity(self.target))

    def test_calibration_only_reuses_all_trackers_and_keeps_resolved_athlete(self):
        first=self.execute_session([])
        requested=dict(self.target,calibration=dict(pixelsPerMeter=500),calibrationVersion=2)
        Path(self.args.target).write_text(json.dumps(requested))
        calls=[];second=self.execute_session(calls)
        self.assertFalse(calls)
        self.assertEqual(first['sessionId'],second['sessionId'])
        self.assertEqual(2,second['target']['athleteTrackId'])
        self.assertEqual(dict(pixelsPerMeter=500),second['target']['calibration'])


class SchedulerBoundaryTests(unittest.TestCase):
    def test_single_tap_with_enough_physical_ram_needs_no_commit_override(self):
        result=schedule([job_budget('tapnextpp',565)],lambda _: 'done',lambda *a:None,lambda:False,
            sample=lambda:dict(gpuMiB=6552,gpuTotalMiB=8192,ramMiB=5000,ramTotalMiB=16197),wait_seconds=-1)
        self.assertEqual(('TrackingReady','done'),result['tapnextpp'])

    def test_single_tap_can_use_commit_for_extra_reserve(self):
        result=schedule([job_budget('tapnextpp',1560)],lambda _: 'done',lambda *a:None,lambda:False,
            sample=lambda:dict(gpuMiB=6494,gpuTotalMiB=8192,ramMiB=2691,ramTotalMiB=16197,commitAvailableMiB=12000),wait_seconds=-1)
        self.assertEqual(('TrackingReady','done'),result['tapnextpp'])

    def test_single_tap_still_requires_physical_budget_and_commit_headroom(self):
        for ram,commit in ((2559,12000),(2691,10239)):
            result=schedule([job_budget('tapnextpp',1560)],lambda _:self.fail('Insufficient memory'),lambda *a:None,lambda:False,
                sample=lambda:dict(gpuMiB=6552,gpuTotalMiB=8192,ramMiB=ram,ramTotalMiB=16197,commitAvailableMiB=commit),wait_seconds=-1)
            self.assertEqual('Failed',result['tapnextpp'][0])
            self.assertIn('available Windows commit',result['tapnextpp'][1])

    def test_commit_does_not_relax_parallel_or_gpu_admission(self):
        for providers,gpu in ((['tapnextpp','samurai'],6552),(['tapnextpp'],3200)):
            result=schedule([job_budget(p,1560) for p in providers],lambda _:self.fail('Unsafe admission'),lambda *a:None,lambda:False,
                sample=lambda:dict(gpuMiB=gpu,gpuTotalMiB=8192,ramMiB=3862,ramTotalMiB=16197,commitAvailableMiB=12000),wait_seconds=-1)
            self.assertTrue(all(status=='Failed' for status,_ in result.values()))

    def test_offline_budget_scales_and_impossible_job_fails_without_waiting(self):
        short=job_budget('bootstapir',565);long=job_budget('bootstapir',4000)
        self.assertGreater(long['gpuMiB'],short['gpuMiB'])
        result=schedule([long],lambda _:self.fail('Impossible task started'),lambda *a:None,lambda:False,
            sample=lambda:dict(gpuMiB=7000,gpuTotalMiB=8192,ramMiB=16000,ramTotalMiB=32000))
        self.assertEqual('Failed',result['bootstapir'][0])
        self.assertIn('installed memory',result['bootstapir'][1])

    def test_completed_result_survives_concurrent_cancellation(self):
        import threading
        cancelled=threading.Event()
        def execute(job):cancelled.set();return 'atomically saved result'
        result=schedule([dict(providerId='tapnextpp',gpuMiB=100,ramMiB=100)],execute,lambda *a:None,cancelled.is_set,
            sample=lambda:dict(gpuMiB=7000,ramMiB=16000))
        self.assertEqual(('TrackingReady','atomically saved result'),result['tapnextpp'])

    def test_cancel_during_admission_does_not_start_later_queued_jobs(self):
        import threading
        cancelled=threading.Event();calls=[]
        def execute(job):
            calls.append(job['providerId']);return 'saved'
        def report(provider,status,value):
            if status=='Running':cancelled.set()
        jobs=[dict(providerId=p,gpuMiB=100,ramMiB=100) for p in PROVIDERS]
        result=schedule(jobs,execute,report,cancelled.is_set,sample=lambda:dict(gpuMiB=7000,ramMiB=16000))
        self.assertEqual(['grounding_dino_sam2'],calls)
        self.assertEqual(3,sum(status=='Cancelled' for status,_ in result.values()))


class ResidentTrackerTests(unittest.TestCase):
    def test_resident_credit_does_not_double_count_owned_weights_or_relax_ram(self):
        resident=session.ResidentTracker()
        resident.gpu_mib=1200
        job=dict(providerId='tapnextpp',gpuMiB=3000,ramMiB=3500)
        self.assertEqual(dict(providerId='tapnextpp',gpuMiB=1800,ramMiB=3500),resident.remaining_budget(job))
        self.assertEqual(3000,job['gpuMiB'])
        resident.gpu_mib=4000
        self.assertEqual(0,resident.remaining_budget(job)['gpuMiB'])

    def test_weights_are_reused_only_for_the_same_checkpoint_device_and_resolution(self):
        from types import SimpleNamespace
        calls=[]
        resident=session.ResidentTracker()
        torch=SimpleNamespace(cuda=SimpleNamespace(is_initialized=lambda:False,memory_allocated=lambda _:0))
        with patch.dict(sys.modules,{'torch':torch}),\
             patch.object(session,'load_resident_weights',side_effect=lambda *a: calls.append(a) or object()):
            first=resident.load('a.pt','cuda',256)
            self.assertIs(first,resident.load('a.pt','cuda',256))
            self.assertIsNot(first,resident.load('a.pt','cuda',512))
            resident.load('b.pt','cuda',512)
            resident.load('b.pt','cpu',512)
        self.assertEqual(4,len(calls))
        resident.clear()
        self.assertIsNone(resident.model)

    def test_failed_tracking_drops_model_and_original_exception_frames(self):
        import io
        from comparison import tap_backends
        resident=session.ResidentTracker()
        resident.model=object();resident.key='old'
        with patch.object(tap_backends,'run',side_effect=RuntimeError('CUDA out of memory')),patch.object(sys,'stderr',io.StringIO()):
            with self.assertRaisesRegex(RuntimeError,'out of memory') as error:
                resident.track('tapnextpp')
        self.assertIsNone(resident.model)
        self.assertIsNone(resident.key)
        self.assertIsNone(error.exception.__context__)

    def test_worker_keeps_one_resident_for_sequential_receipted_requests(self):
        import io
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'session.json'
            output.write_text(json.dumps({'providers':[{'status':'TrackingReady'}]}))
            args=SimpleNamespace(points_python=sys.executable, output=str(output))
            incoming=io.StringIO(''.join(json.dumps({'request':str(i),'arguments':[]})+'\n' for i in range(2)))
            outgoing=io.StringIO()
            with patch.object(session,'parser',return_value=SimpleNamespace(parse_args=lambda _:args)),\
                 patch.object(session,'run') as run,patch.object(session,'ResidentTracker') as tracker,\
                 patch.object(sys,'stdin',incoming),patch.object(sys,'stdout',outgoing):
                session.worker_loop()
            self.assertEqual(2,run.call_count)
            self.assertIs(run.call_args_list[0].args[1],run.call_args_list[1].args[1])
            tracker.return_value.clear.assert_called_once()
            self.assertEqual([{'workerRequest':'0','ok':True},{'workerRequest':'1','ok':True}],
                             [json.loads(line) for line in outgoing.getvalue().splitlines()])


if __name__=='__main__':unittest.main()
