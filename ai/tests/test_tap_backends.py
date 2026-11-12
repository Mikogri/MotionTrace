import copy
from pathlib import Path
import sys
import unittest
import tempfile
import json
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from comparison.tap_backends import observation, validate_target, decoded_frames
from comparison import tap_backends


class BidirectionalTimelineTests(unittest.TestCase):
    def test_model_tensors_replay_losslessly_with_original_layout_and_device(self):
        import torch
        for device in ['cpu'] + (['cuda'] if torch.cuda.is_available() else []):
            frames = [torch.arange(18, dtype=torch.float32, device=device).reshape(1, 3, 2, 3)
                      .permute(0, 2, 3, 1).unsqueeze(0) + i for i in range(3)]
            rows = list(tap_backends.bidirectional_frames(enumerate(frames), 1))
            self.assertEqual([(False, 1), (False, 2), (True, 1), (True, 0)], [(b, i) for b, i, _ in rows])
            for _, index, frame in rows:
                self.assertTrue(torch.equal(frames[index], frame))
                self.assertEqual(frames[index].stride(), frame.stride())
                self.assertEqual(frames[index].device, frame.device)
                self.assertEqual(frames[index].dtype, frame.dtype)

    def test_spool_budget_also_applies_to_prepared_tensors(self):
        import torch
        with self.assertRaisesRegex(ValueError, 'temporary disk budget'):
            list(tap_backends.bidirectional_frames(enumerate([torch.zeros(1024), torch.zeros(1024)]), 1, max_spool_bytes=1024))

    def test_seed_is_replayed_once_per_direction_and_original_indices_survive(self):
        import numpy as np
        frames = ((i, np.full((2, 2, 3), i, dtype=np.uint8)) for i in range(5))
        rows = list(tap_backends.bidirectional_frames(frames, 2))
        self.assertEqual([(back, i) for back, i, _ in rows], [(False, 2), (False, 3), (False, 4), (True, 2), (True, 1), (True, 0)])
        self.assertTrue(all(int(image[0, 0, 0]) == i for _, i, image in rows))

    def test_points_only_tracking_covers_floor_and_overhead_even_for_a_chest_seed(self):
        self.assertEqual((0, 0, 1920, 1080), tap_backends.tracking_region(
            dict(points=[dict(x=832, y=472), dict(x=804, y=473)]), 1920, 1080, dict(frames=[dict(athletes=[])])))

    def test_frame_zero_does_not_trigger_a_second_inference_pass(self):
        import numpy as np
        self.assertEqual([(back, i) for back, i, _ in tap_backends.bidirectional_frames(((0, np.zeros((1, 1, 3))),), 0)], [(False, 0)])

class PointTrackerContractTests(unittest.TestCase):
    def test_resident_weights_are_not_used_before_checkpoint_integrity_validation(self):
        from unittest.mock import Mock
        loader=Mock()
        pose=copy.deepcopy(self.pose)
        pose['video'].update(framesPerSecond=25,durationSeconds=.13)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'pose.json').write_text(json.dumps(pose))
            (root/'target.json').write_text(json.dumps(self.target))
            (root/'manifest.json').write_text(json.dumps({'repositoryRevision':'tampered'}))
            with self.assertRaisesRegex(ValueError,'revision mismatch'):
                tap_backends.run('tapnextpp','unused.mp4',root/'pose.json',root/'target.json',root/'out.json',root,
                                 device='cpu',model_loader=loader)
            loader.assert_not_called()

    def test_pair_guard_rejects_isolated_one_point_jump_preserving_raw(self):
        target=dict(targetId='bar',athleteTrackId=1)
        def pair(a,b):
            return [observation(target,'tapnextpp',x,y,True,dict(visibilityProbability=.99),1000,1000,i)
                    for i,(x,y) in enumerate((a,b))]
        rows=[pair((100,200),(300,200)),pair((100,180),(440,180)),pair((100,160),(300,160))]
        original=copy.deepcopy(rows)
        tap_backends.reject_pair_spikes(rows,[dict(timestampSeconds=i/30) for i in range(3)])
        self.assertTrue(all(o['measurement'] is None for o in rows[1]))
        self.assertEqual(original[1][1]['rawObservation'],rows[1][1]['rawObservation'])
        self.assertEqual(original[0],rows[0]);self.assertEqual(original[2],rows[2])
        self.assertEqual('pair-discontinuity',rows[1][0]['rejectionReason'])

    def test_pair_guard_keeps_fast_shared_motion_and_does_not_bridge_gaps(self):
        target=dict(targetId='bar',athleteTrackId=1)
        for times,positions in (([0,.03,.06],[(100,300),(300,500),(100,300)]),
                                ([0,.3,.6],[(100,300),(100,440),(100,300)])):
            rows=[[observation(target,'tapnextpp',x,200,True,dict(visibilityProbability=.99),1000,1000,i)
                   for i,x in enumerate(p)] for p in positions]
            original=copy.deepcopy(rows)
            tap_backends.reject_pair_spikes(rows,[dict(timestampSeconds=t) for t in times])
            self.assertEqual(original,rows)

    def test_pose_crop_covers_wrist_motion_and_keeps_fallback_when_pose_missing(self):
        target=dict(points=[dict(x=800,y=1400),dict(x=1000,y=1400)],athleteTrackId=1,frameIndex=0)
        frames=[dict(athletes=[dict(athleteId=1,trackingState='Tracked',keypoints=[
            dict(joint='LeftWrist',x=800,y=1400+i*15,confidence=.9),
            dict(joint='RightWrist',x=1000,y=1400+i*15,confidence=.9)])]) for i in range(30)]
        base=tap_backends.tracking_region(target,2160,3840,self.pose)
        self.assertEqual(base,tap_backends.tracking_region(target,2160,3840,dict(frames=[])))
        left,top,w,h=tap_backends.tracking_region(target,2160,3840,dict(frames=frames))
        self.assertLess(w,base[2])
        self.assertTrue(left <= 800 < 1000 < left+w)
        self.assertTrue(top <= 1400 < 1835 < top+h)

    def setUp(self):
        self.pose = {"video": {"width": 2160, "height": 3840}, "frames": [
            {"timestampSeconds": 0.0}, {"timestampSeconds": .04}, {"timestampSeconds": .09}]}
        self.target = dict(targetId="left-axis", athleteTrackId=7, frameIndex=1,
                           timestampSeconds=.04, point=dict(x=300., y=1200.))

    def test_nonzero_query_frame_resolves_exact_variable_timestamp(self):
        self.assertEqual(1, validate_target(self.pose, self.target))
        self.target["timestampSeconds"] = 1 / 30
        with self.assertRaisesRegex(ValueError, "timestamp"):
            validate_target(self.pose, self.target)

    def test_two_queries_keep_distinct_coordinates_visibility_and_recurrent_state(self):
        import numpy as np
        import torch
        target=dict(self.target,points=[dict(x=300.,y=1200.),dict(x=900.,y=1600.)])
        target.pop('point')
        left,top,cw,ch=tap_backends.tracking_region(target,2160,3840,self.pose)
        calls=[]
        def infer(**kwargs):
            calls.append(kwargs)
            tracks=torch.tensor([[[[1200.-top,300.-left],[1600.-top,900.-left]]]])
            return tracks,None,torch.tensor([[[[3.],[-2.]]]]),'retained-state'
        model=SimpleNamespace(device=torch.device('cpu'),_model=infer)
        coordinate_sizes=[]
        frame_sizes=[]
        utils=SimpleNamespace(display_to_model=lambda q,*a:coordinate_sizes.append(a[-1]) or q,
            make_query_tensor=lambda q,*a:torch.tensor(q[:,::-1].copy()),
            preprocess_frame=lambda image,*a:frame_sizes.append(a[-1]) or torch.zeros((1,1,2,2,3)),
            model_to_display=lambda xy,*a:coordinate_sizes.append(a[-1]) or xy)
        wrapper=SimpleNamespace(from_checkpoint=lambda *a,**kw:model)
        modules={'tapnet.tapnextpp.votsp2026.model':SimpleNamespace(TAPNextPP=wrapper),
                 'tapnet.tapnextpp.votsp2026':SimpleNamespace(utils=utils)}
        with patch.dict(sys.modules,modules),patch.object(tap_backends,'decoded_frames',
                return_value=[(i,np.zeros((2,2,3))) for i in range(3)]):
            rows=tap_backends.tapnext('video',self.pose,target,'checkpoint','cpu',lambda *a:None,resolution=512)
        self.assertEqual([256]*5,coordinate_sizes)
        self.assertEqual([512]*3,frame_sizes)  # The seed's prepared input is reused in the backward pass.
        self.assertEqual([2,2,2],[len(r) for r in rows])
        self.assertEqual([[1200.-top,300.-left],[1600.-top,900.-left]],calls[0]['query_points'].tolist())
        self.assertIsNone(calls[1]['query_points'])
        self.assertEqual('retained-state',calls[1]['state'])
        self.assertIsNone(calls[2]['state'])
        self.assertIsNotNone(calls[2]['query_points'])
        self.assertEqual('retained-state', calls[3]['state'])
        first,second=rows[1]
        self.assertEqual(['left-axis-1','left-axis-2'],[o['objectId'] for o in rows[1]])
        self.assertEqual([0,1],[o['pointIndex'] for o in rows[1]])
        self.assertTrue(all(o['measurementGroupId']=='left-axis' for o in rows[1]))
        self.assertEqual(300.,first['measurement']['x'])
        self.assertIsNone(second['measurement'])
        self.assertEqual(900.,second['rawObservation']['x'])
        self.assertEqual(-2.,second['rawObservation']['visibilityLogit'])

    def test_query_context_covers_both_points_and_room_for_motion_within_source(self):
        for points in ([dict(x=1440.,y=1938.),dict(x=1824.,y=1961.)],
                       [dict(x=0.,y=0.),dict(x=2159.,y=3839.)]):
            left,top,width,height=tap_backends.tracking_region(dict(points=points),2160,3840)
            self.assertGreaterEqual(left,0)
            self.assertGreaterEqual(top,0)
            self.assertLessEqual(left+width,2160)
            self.assertLessEqual(top+height,3840)
            for point in points:
                self.assertTrue(left <= point['x'] < left+width)
                self.assertTrue(top <= point['y'] < top+height)
        self.assertEqual((0,0,2160,3840),tap_backends.tracking_region(self.target,2160,3840))

    def test_invalid_reference_and_unresolved_athlete_rejected(self):
        for update in (dict(point=dict(x=float("nan"), y=40.)), dict(point=dict(x=2160., y=40.)),
                       dict(athleteTrackId=0), dict(frameIndex=-1), dict(frameIndex=True)):
            target = copy.deepcopy(self.target)
            target.update(update)
            with self.subTest(update=update), self.assertRaises(ValueError):
                validate_target(self.pose, target)

    def test_two_point_preflight_rejects_same_xy_even_with_different_metadata(self):
        for points in ([dict(x=1.,y=2.,note='left'),dict(x=1.,y=2.,note='right')],
                       [dict(x=float('nan'),y=2.),dict(x=3.,y=4.)],
                       [dict(x=True,y=2.),dict(x=3.,y=4.)],
                       [None,dict(x=3.,y=4.)]):
            with self.subTest(points=points),self.assertRaises(ValueError):
                tap_backends.target_points(dict(points=points))

    def test_visible_physical_point_has_no_invented_box_or_mask(self):
        result = observation(self.target, "tapnextpp", 321., 1234., True,
                             dict(visibilityProbability=.95, visibilityLogit=3.), 2160, 3840)
        self.assertIsNone(result["box"])
        self.assertIsNone(result["maskPath"])
        self.assertEqual("tapnextpp", result["measurement"]["source"])
        self.assertFalse(result["measurement"]["isProxy"])
        self.assertEqual("Reduced", result["measurement"]["quality"])
        self.assertEqual(321., result["measurement"]["x"])

    def test_occluded_prediction_retained_raw_but_never_measurement(self):
        result = observation(self.target, "bootstapir", 321., 1234., False,
                             dict(visibilityProbability=.1, occlusionLogit=4.), 2160, 3840)
        self.assertEqual("Lost", result["trackingState"])
        self.assertIsNone(result["measurement"])
        self.assertEqual(321., result["rawObservation"]["x"])
        self.assertEqual(4., result["rawObservation"]["occlusionLogit"])

    def test_outside_image_prediction_does_not_become_zero_measurement(self):
        result = observation(self.target, "tapnextpp", -3., 12., True,
                             dict(visibilityProbability=.9), 2160, 3840)
        self.assertIsNone(result["measurement"])
        self.assertEqual(-3., result["rawObservation"]["x"])

    def test_decoder_rejects_missing_shared_frames_and_wrong_pts(self):
        import cv2
        import numpy as np
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "three frames.avi")
            writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), 25, (64, 64))
            for _ in range(3):
                writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
            writer.release()
            pose = dict(video=dict(width=64, height=64), frames=[dict(timestampSeconds=i*.04) for i in range(3)])
            self.assertEqual(3, len(list(decoded_frames(path, pose))))
            pose["frames"].append(dict(timestampSeconds=.12))
            with self.assertRaisesRegex(ValueError, "Incomplete"):
                list(decoded_frames(path, pose))
            pose["frames"] = pose["frames"][:3]
            pose["frames"][1]["timestampSeconds"] = .05
            with self.assertRaisesRegex(ValueError, "timestamps"):
                list(decoded_frames(path, pose))

    def test_saved_result_identifies_actual_provider_and_only_target_participant(self):
        # Exercise the real serialization boundary consumed by C#; only weights
        # and inference are mocked. Inheriting custom_barbell/participant defaults
        # would reject the new provider or bring the spotter back into the UI.
        pose = copy.deepcopy(self.pose)
        pose.update(schemaVersion=3, provider="custom_barbell", limitations=[],
            versions=dict(engineVersion="engine-v1", poseModelVersion="pose-v1",
                          barbellProvider="custom_barbell", barbellModelVersion="old-shaft-model"),
            athletes=[dict(id=7, isExerciseParticipant=True), dict(id=8, isExerciseParticipant=True)])
        pose["video"].update(fileName="sample.mp4", framesPerSecond=25., durationSeconds=.13)
        for frame in pose["frames"]:
            frame.update(athletes=[], shaft={"old": True}, shafts=[{"old": True}])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pose_path, target_path = root / "pose.json", root / "target.json"
            pose_path.write_text(json.dumps(pose))
            target_path.write_text(json.dumps(self.target))
            for provider, function, resolution in (("tapnextpp", "tapnext", 256), ("tapnextpp", "tapnext", 512), ("bootstapir", "bootstapir", 256)):
                with self.subTest(provider=provider,resolution=resolution):
                    visible = observation(self.target, provider, 320., 1220., True,
                                          dict(visibilityProbability=.95), 2160, 3840)
                    hidden = observation(self.target, provider, 330., 1250., False,
                                         dict(visibilityProbability=.15), 2160, 3840)
                    output = root / f"{provider}.json"
                    stale_entry=dict(checkpoint='tapnextpp_ckpt.pt',files=[dict(path='tapnextpp_ckpt.pt',sha256='wrong',size=1)])
                    expected=tap_backends.TAPNEXT_CHECKPOINTS[resolution] if provider=='tapnextpp' else tap_backends.CHECKPOINTS[provider]
                    with patch.object(tap_backends, "installation", return_value=(root/expected[0], stale_entry)), \
                         patch.object(tap_backends, function, return_value=[[], [visible], [hidden]]) as tracker:
                        tap_backends.run(provider, "sample.mp4", pose_path, target_path, output,
                                         root, device="cpu",tapnext_resolution=resolution)
                    tracker.assert_called_once()
                    result = json.loads(output.read_text(encoding="utf-8"))
                    self.assertEqual(4, result["schemaVersion"])
                    self.assertEqual(provider, result["provider"])
                    self.assertEqual(provider, result["versions"]["barbellProvider"])
                    self.assertEqual(expected[1], result["versions"]["barbellModelVersion"])
                    self.assertEqual(expected[0],result['trackingModel']['checkpoint'])
                    self.assertEqual([dict(path=expected[0],sha256=expected[1],size=expected[2])],result['trackingModel']['files'])
                    self.assertEqual([resolution,resolution],result['trackingModel']['resolution'])
                    self.assertEqual(tap_backends.VERSION, result["versions"]["measurementVersion"])
                    self.assertEqual("pose-v1", result["versions"]["poseModelVersion"])
                    self.assertEqual("engine-v1", result["versions"]["engineVersion"])
                    self.assertEqual([7], [a["id"] for a in result["athletes"] if a["isExerciseParticipant"]])
                    self.assertEqual({7, 8}, {a["id"] for a in result["athletes"]})
                    self.assertEqual(provider, result["visionMetadata"]["provider"])
                    self.assertEqual(result["trackingModel"], result["visionMetadata"]["trackingModel"])
                    self.assertEqual(result["performance"], result["visionMetadata"]["performance"])
                    self.assertFalse(result["visionMetadata"]["isProxy"])
                    self.assertEqual(self.target, result["visionMetadata"]["target"])
                    self.assertEqual([0., .04, .09], [f["timestampSeconds"] for f in result["frames"]])
                    self.assertTrue(all(f["shaft"] is None and f["shafts"] == [] for f in result["frames"]))
                    self.assertEqual([], result["frames"][0]["objects"])
                    obj = result["frames"][1]["objects"][0]
                    self.assertIsInstance(obj["confidence"], (float, int))
                    self.assertTrue(0 <= obj["confidence"] <= 1)
                    self.assertEqual(provider, obj["measurement"]["source"])
                    self.assertFalse(obj["measurement"]["isProxy"])
                    self.assertIsNone(obj["box"])
                    self.assertIsNone(obj["maskPath"])
                    self.assertIsNone(result["frames"][2]["objects"][0]["measurement"])
                    self.assertFalse(list(root.glob("*.tmp")))
            self.assertEqual(pose, json.loads(pose_path.read_text()))


if __name__ == "__main__":
    unittest.main()
