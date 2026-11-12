import unittest
from comparison.samurai_backend import memory_keep_indices, validate_target, trim_memory, LazyFrames
from types import SimpleNamespace
from pathlib import Path
import tempfile


class SamuraiContracts(unittest.TestCase):
    def test_keeps_last_eligible_memories_across_long_occlusion(self):
        outputs = {i: {'best_iou_score': .9 if i < 25 else .1,
                       'object_score_logits': 1., 'kf_score': .8} for i in range(100)}
        keep = memory_keep_indices(outputs, 99, 16, .5, 0., 0.)
        self.assertTrue(set(range(10, 25)).issubset(keep))
        self.assertTrue(set(range(84, 100)).issubset(keep))
        self.assertLessEqual(len(keep), 31)

    def test_query_timestamp_must_match_frame(self):
        target = dict(frameIndex=1, timestampSeconds=0., athleteTrackId=1,
                      targetId='bar', point=dict(x=20, y=20),
                      box=dict(x=10,y=10,width=30,height=30))
        with self.assertRaisesRegex(ValueError, 'timestamp'):
            validate_target(target, [{'timestampSeconds':0.},{'timestampSeconds':.1}], 100,100)

    def test_point_must_be_in_box(self):
        target = dict(frameIndex=0,timestampSeconds=0.,athleteTrackId=1,targetId='bar',
                      point=dict(x=90,y=20),box=dict(x=10,y=10,width=30,height=30))
        with self.assertRaisesRegex(ValueError,'point'):
            validate_target(target,[{'timestampSeconds':0.}],100,100)

    def test_trim_preserves_upstream_history_scan_and_selected_features(self):
        import torch
        outputs={i: dict(best_iou_score=torch.tensor(.9 if i%3 else .1),
            object_score_logits=torch.tensor(1.),kf_score=None,
            maskmem_features=torch.ones(2),maskmem_pos_enc=[torch.ones(2)],
            pred_masks=torch.ones(2),obj_ptr=torch.ones(2)) for i in range(2,100)}
        state={'output_dict':{'non_cond_frame_outputs':outputs},
               'output_dict_per_obj':{0:{'non_cond_frame_outputs':dict(outputs)}}}
        predictor=SimpleNamespace(max_obj_ptrs_in_encoder=16,memory_bank_iou_threshold=.5,
            memory_bank_obj_score_threshold=0.,memory_bank_kf_score_threshold=0.)
        trim_memory(state,predictor,99)
        selected=[]
        # This is the official forward scan, including direct indexing of old scores.
        for i in range(99,1,-1):
            row=outputs[i]
            if row['best_iou_score'].item()>.5: selected.insert(0,i)
            if len(selected)>=15: break
        for index in selected: self.assertIn('maskmem_features',outputs[index])
        for index in range(85,100): self.assertIn('obj_ptr',outputs[index])
        self.assertNotIn('maskmem_features',outputs[3])
        self.assertEqual(len(outputs),98)

    def test_lazy_decoder_preserves_nonzero_query_and_checks_extra_frames(self):
        import cv2
        import numpy as np
        from motiontrace_ai.video_decode import VideoDecoder
        with tempfile.TemporaryDirectory() as folder:
            video=Path(folder)/'frames.mp4'
            writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),10,(32,24))
            for i in range(4): writer.write(np.full((24,32,3),i*50,np.uint8))
            writer.release()
            decoder=VideoDecoder(video)
            frames=[dict(timestampSeconds=t) for t,_ in decoder]
            decoder.close()
            loader=LazyFrames(video,frames,2,16)
            try:
                self.assertEqual(len(loader),2)
                self.assertEqual(tuple(loader[0].shape),(3,16,16))
                self.assertEqual(loader.index,2)
                loader[1]
                loader.finish()
            finally: loader.decoder.close()
            loader=LazyFrames(video,frames[:-1],0,16)
            try:
                loader[2]
                with self.assertRaisesRegex(ValueError,'frame count'): loader.finish()
            finally: loader.decoder.close()


if __name__ == '__main__': unittest.main()
