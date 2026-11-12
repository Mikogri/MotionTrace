import unittest
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch
import av
from fractions import Fraction
from types import SimpleNamespace
import numpy as np
from motiontrace_ai.video_decode import VideoDecoder, PrefetchedVideoDecoder, validate_analysis_frames

class Frame:
    def __init__(self,time,rotation=0,corrupt=False):
        self.time=time;self.duration=1;self.time_base=Fraction(1,30);self.rotation=rotation;self.is_corrupt=corrupt
        self.width=4;self.height=2
    def to_ndarray(self,format):return np.zeros((2,4,3),np.uint8)

def decoder(frames,duration=0,rotation=0):
    d=VideoDecoder.__new__(VideoDecoder);d.iterator=iter(frames);d.fps=30;d.count=627
    d.width,d.height=(2,4) if rotation else (4,2);d.duration=duration;d.end=0;d.materialize=None
    return d

class VideoDecodeTests(unittest.TestCase):
    def test_no_presentable_frames_is_not_success(self):
        with self.assertRaisesRegex(ValueError,'No video frames'):
            list(decoder([Frame(-1)]))
    def test_nonzero_stream_start_still_checks_complete_end(self):
        source=decoder([Frame(10+i/30) for i in range(30)],2)
        source.start_time=10
        with self.assertRaisesRegex(ValueError,'Video ended'):
            list(source)
    def test_valid_nonzero_start_keeps_original_timestamps(self):
        source=decoder([Frame(10+i/30) for i in range(60)],2)
        source.start_time=10
        self.assertEqual(list(source)[0][0],10)
    def test_variable_frame_rate_is_not_mistaken_for_missing_samples(self):
        self.assertEqual(len(list(decoder([Frame(0),Frame(.1),Frame(.5)],.53))),3)
    def test_small_negative_first_pts_is_clamped_without_shifting_later_frames(self):
        rows=list(decoder([Frame(-.0016667),Frame(1/30),Frame(2/30)]))
        self.assertEqual([r[0] for r in rows],[0,1/30,2/30])
    def test_edit_list_sample_count_does_not_reject_complete_timeline(self):
        d=decoder([Frame(i/30) for i in range(620)],620/30)
        self.assertEqual(len(list(d)),620)
    def test_truncated_timeline_is_not_silently_accepted(self):
        with self.assertRaisesRegex(ValueError,'Video ended'):list(decoder([Frame(0),Frame(1/30)],20))
    def test_corrupt_and_duplicate_pts_rejected(self):
        with self.assertRaisesRegex(ValueError,'Corrupt'):list(decoder([Frame(0,corrupt=True)]))
        with self.assertRaisesRegex(ValueError,'Non-increasing'):list(decoder([Frame(0),Frame(0)]))
    def test_portrait_rotation_preserves_dimensions(self):
        self.assertEqual(list(decoder([Frame(0,-90)],rotation=-90))[0][1].shape,(4,2,3))
    def test_selective_images_keep_pts_rotation_and_validate_skipped_frames(self):
        source=decoder([Frame(i/30,-90) for i in range(5)],rotation=-90)
        source.materialize=lambda index,time:index==3
        rows=list(source)
        self.assertEqual([r[0] for r in rows],[i/30 for i in range(5)])
        self.assertEqual([i for i,(_,image) in enumerate(rows) if image is not None],[3])
        self.assertEqual(rows[3][1].shape,(4,2,3))
        for frames,message in [([Frame(0),Frame(0)],'Non-increasing'),([Frame(0,corrupt=True)],'Corrupt'),([Frame(0,45)],'Unsupported')]:
            source=decoder(frames);source.materialize=lambda index,time:False
            with self.assertRaisesRegex(ValueError,message):list(source)

class AnalysisFrameValidationTests(unittest.TestCase):
    def result(self,times,duration=1):
        return dict(video=dict(durationSeconds=duration,framesPerSecond=30),
                    frames=[dict(timestampSeconds=t) for t in times])

    def test_complete_variable_rate_result_is_valid(self):
        validate_analysis_frames(self.result([0,.2,.6,.9666667]))

    def test_final_held_vfr_frame_uses_its_actual_duration(self):
        result=self.result([0,.033,1],duration=2)
        result['video']['finalFrameDurationSeconds']=1
        validate_analysis_frames(result)

    def test_invalid_final_frame_duration_is_rejected(self):
        for duration in (0,-1,float('nan'),float('inf'),True,'1'):
            result=self.result([0,.9666667])
            result['video']['finalFrameDurationSeconds']=duration
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                validate_analysis_frames(result)

    def test_empty_duplicate_nonfinite_and_truncated_results_are_invalid(self):
        for times in ([],[0,0],[0,float('nan')],[0,.033]):
            with self.subTest(times=times), self.assertRaises(ValueError):
                validate_analysis_frames(self.result(times))

    def test_frame_past_video_end_is_invalid(self):
        with self.assertRaises(ValueError):
            validate_analysis_frames(self.result([0,3]))

    def test_unknown_duration_does_not_require_metadata_frame_count(self):
        result=self.result([0,.033,.2],duration=0)
        result['video']['frameCount']=100
        validate_analysis_frames(result)

class PrefetchedDecodeTests(unittest.TestCase):
    def test_actual_video_has_identical_pixels_pts_and_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'fixture.mkv'
            with av.open(str(path), 'w') as output:
                stream = output.add_stream('ffv1', rate=30)
                stream.width = 32
                stream.height = 24
                stream.pix_fmt = 'bgr0'
                for i in range(12):
                    pixels = np.random.default_rng(i).integers(0, 256, (24, 32, 3), dtype=np.uint8)
                    frame = av.VideoFrame.from_ndarray(pixels, format='bgr24')
                    for packet in stream.encode(frame):
                        output.mux(packet)
                for packet in stream.encode():
                    output.mux(packet)
            direct = VideoDecoder(path)
            buffered = PrefetchedVideoDecoder(path)
            selected = PrefetchedVideoDecoder(path,decoder=VideoDecoder(path,materialize=lambda i,t:i%3==0))
            try:
                expected = list(direct)
                actual = list(buffered)
                sparse=list(selected)
                self.assertEqual(len(expected), 12)
                self.assertEqual(len(actual), len(expected))
                for (et, ep), (at, ap) in zip(expected, actual):
                    self.assertEqual(et, at)
                    np.testing.assert_array_equal(ep, ap)
                for index,((et,ep),(st,sp)) in enumerate(zip(expected,sparse)):
                    self.assertEqual(et,st)
                    if index%3==0:np.testing.assert_array_equal(ep,sp)
                    else:self.assertIsNone(sp)
                for name in ('fps', 'count', 'duration', 'width', 'height', 'end'):
                    self.assertEqual(getattr(direct, name), getattr(buffered, name))
                self.assertFalse(buffered._thread.is_alive())
            finally:
                direct.close()
                buffered.close()
                selected.close()

    def test_eof_validation_and_frame_errors_reach_consumer(self):
        for frames, duration, message in [
            ([Frame(0), Frame(1/30)], 20, 'Video ended'),
            ([Frame(0), Frame(0)], 0, 'Non-increasing'),
            ([Frame(0), Frame(1/30, corrupt=True)], 0, 'Corrupt'),
        ]:
            source = decoder(frames, duration)
            source.close = unittest.mock.Mock()
            with patch('motiontrace_ai.video_decode.VideoDecoder', return_value=source):
                buffered = PrefetchedVideoDecoder('unused')
            with self.assertRaisesRegex(ValueError, message):
                list(buffered)
            source.close.assert_called_once()
            self.assertFalse(buffered._thread.is_alive())

    def test_early_close_bounds_decode_ahead_and_closes_on_producer(self):
        source = decoder([Frame(i/30) for i in range(1000)])
        reached = threading.Event()
        close_threads = []
        original = source.iterator
        def frames():
            for index, frame in enumerate(original):
                if index == 2:
                    reached.set()
                yield frame
        source.iterator = frames()
        source.close = lambda: close_threads.append(threading.current_thread().name)
        with patch('motiontrace_ai.video_decode.VideoDecoder', return_value=source):
            buffered = PrefetchedVideoDecoder('unused', capacity=2)
        iterator = iter(buffered)
        next(iterator)
        self.assertTrue(reached.wait(2))
        buffered.close()
        iterator.close()
        self.assertEqual(close_threads, ['video-decode-prefetch'])
        self.assertLessEqual(source.end, 3/30)
        self.assertFalse(buffered._thread.is_alive())
        self.assertTrue(buffered._queue.empty())

if __name__=='__main__':unittest.main()
