"""Decode presentation frames, not the MOV sample-table count (which includes edits)."""
import itertools
import math
import queue
import threading
import time
import av
import cv2


def validate_analysis_frames(result):
    """Reject unusable saved timelines without treating VFR/edit lists as lost frames."""
    frames=result.get('frames')
    video=result.get('video',{})
    if not isinstance(video, dict):
        raise ValueError('Invalid analysis video metadata')
    fps=video.get('framesPerSecond',0)
    duration=video.get('durationSeconds',0)
    if (not isinstance(frames,list) or not frames or not isinstance(fps,(int,float))
            or not math.isfinite(fps) or not 0<fps<=1000
            or not isinstance(duration,(int,float)) or not math.isfinite(duration) or duration<0):
        raise ValueError('Invalid or empty analysis video timeline')
    previous=-1.
    for frame in frames:
        timestamp=frame.get('timestampSeconds') if isinstance(frame,dict) else None
        if (not isinstance(timestamp,(int,float)) or isinstance(timestamp,bool)
                or not math.isfinite(timestamp) or timestamp<0 or timestamp<=previous):
            raise ValueError('Analysis frame timestamps must be finite, nonnegative and increasing')
        previous=timestamp
    final_duration=video.get('finalFrameDurationSeconds',1/fps)
    if (not isinstance(final_duration,(int,float)) or isinstance(final_duration,bool)
            or not math.isfinite(final_duration) or final_duration<=0):
        raise ValueError('Invalid final video frame duration')
    # A held VFR frame can last much longer than 1/fps. New analyses preserve
    # its actual duration; old caches use the conservative nominal estimate.
    tolerance=max(.25,2/fps)
    if duration and abs(previous+final_duration-duration)>tolerance:
        raise ValueError('Analysis frames do not cover the saved video duration')


class VideoDecoder:
    VERSION='pyav-pts-2'
    def __init__(self,path,materialize=None):
        self.materialize=materialize
        self.container=av.open(str(path),options={'err_detect':'explode'})
        try:
            if not self.container.streams.video:raise ValueError('No video stream')
            self.stream=self.container.streams.video[0]
            self.stream.thread_type='AUTO';self.stream.codec_context.thread_count=4
            self.fps=float(self.stream.average_rate or self.stream.guessed_rate or 0)
            if not 0<self.fps<=1000:raise ValueError('Invalid video frame rate')
            self.count=self.stream.frames
            self.duration=float(self.stream.duration*self.stream.time_base) if self.stream.duration else 0
            self.start_time=float(self.stream.start_time*self.stream.time_base) if self.stream.start_time else 0
            self.iterator=self.container.decode(self.stream)
            first=next(self.iterator,None)
            if first is None:raise ValueError('No video frames decoded')
            self.width,self.height=(first.height,first.width) if abs(first.rotation)==90 else (first.width,first.height)
            self.iterator=itertools.chain([first],self.iterator)
            self.end=0
        except BaseException:
            self.container.close();raise

    def __iter__(self):
        previous=-1.
        index=0
        for frame in self.iterator:
            if frame.is_corrupt:raise ValueError('Corrupt video frame; analysis was not saved')
            timestamp=frame.time
            duration=float(frame.duration*frame.time_base) if frame.duration else 1/self.fps
            if timestamp is None or not math.isfinite(timestamp):raise ValueError('Missing frame presentation timestamp')
            # Exclude decode preroll before movie time zero; retain the frame covering zero.
            if timestamp+duration<=0:continue
            timestamp=max(0.,timestamp)
            if timestamp<=previous:raise ValueError('Non-increasing frame presentation timestamps')
            previous=timestamp;self.end=timestamp+duration
            rotation=frame.rotation
            if rotation not in (-90,0,90,-180,180):raise ValueError(f'Unsupported video rotation: {rotation}')
            dimensions=(frame.height,frame.width) if abs(rotation)==90 else (frame.width,frame.height)
            if dimensions!=(self.width,self.height):raise ValueError('Video dimensions changed mid-stream')
            # Decode and validate every PTS, but avoid allocating/rotating a full
            # RGB image when this stage does not use that frame for inference.
            if self.materialize is not None and not self.materialize(index,timestamp):
                index+=1
                yield timestamp,None
                continue
            image=frame.to_ndarray(format='bgr24')
            if rotation==-90:image=cv2.rotate(image,cv2.ROTATE_90_CLOCKWISE)
            elif rotation==90:image=cv2.rotate(image,cv2.ROTATE_90_COUNTERCLOCKWISE)
            elif abs(rotation)==180:image=cv2.rotate(image,cv2.ROTATE_180)
            if image.shape[:2]!=(self.height,self.width):raise ValueError('Video dimensions changed mid-stream')
            index+=1
            yield timestamp,image
        # Sample count is not an EOF check: MOV edit lists may legitimately hide samples.
        if not index:
            raise ValueError('No video frames with usable presentation timestamps decoded; analysis was not saved')
        expected_end=max(0.,getattr(self,'start_time',0)+self.duration)
        if self.duration and self.end+max(.25,2/self.fps)<expected_end:
            raise ValueError(f'Video ended at {self.end:.3f}s, expected {expected_end:.3f}s; analysis was not saved')

    def close(self):self.container.close()


class PrefetchedVideoDecoder:
    """Bounded decode-ahead with the same frames and validation as VideoDecoder.

    Use close() in a finally block, including when the consumer stops early.
    Only the producer accesses PyAV after iteration starts; close waits for its
    current decode call to finish before the producer closes the container.
    Capacity includes the frame being decoded, but excludes the consumer's frame.
    """
    VERSION = VideoDecoder.VERSION

    def __init__(self, path, capacity=2, decoder=None):
        if not isinstance(capacity, int) or capacity < 1:
            raise ValueError('Decode prefetch capacity must be a positive integer')
        self._decoder = decoder if decoder is not None else VideoDecoder(path)
        for name in ('fps', 'count', 'duration', 'width', 'height'):
            setattr(self, name, getattr(self._decoder, name))
        self.end = 0
        self.decode_seconds = 0.
        self._queue = queue.Queue(maxsize=capacity)
        self._slots = threading.Semaphore(capacity)
        self._stop = threading.Event()
        self._thread = None
        self._closed = False

    def _put(self, item):
        while not self._stop.is_set():
            try:
                self._queue.put(item, timeout=.05)
                return
            except queue.Full:
                pass

    def _produce(self):
        try:
            iterator = iter(self._decoder)
            while not self._stop.is_set():
                if not self._slots.acquire(timeout=.05):
                    continue
                if self._stop.is_set():
                    break
                started = time.perf_counter()
                try:
                    row = next(iterator)
                except StopIteration:
                    self._put(('end', None, self._decoder.end))
                    return
                finally:
                    self.decode_seconds += time.perf_counter() - started
                self._put(('frame', row, self._decoder.end))
        except BaseException as error:
            self._put(('error', error, self._decoder.end))
        finally:
            self._decoder.close()

    def __iter__(self):
        if self._closed:
            raise RuntimeError('Decoder is closed')
        if self._thread is not None:
            raise RuntimeError('Prefetched decoder can only be iterated once')
        self._thread = threading.Thread(target=self._produce, name='video-decode-prefetch', daemon=True)
        self._thread.start()
        try:
            while not self._stop.is_set():
                try:
                    kind, value, end = self._queue.get(timeout=.05)
                except queue.Empty:
                    continue
                self._slots.release()
                self.end = end
                if kind == 'error':
                    raise value
                if kind == 'end':
                    return
                yield value
        finally:
            self.close()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._stop.set()
        if self._thread is None:
            self._decoder.close()
        else:
            self._thread.join()
        # Release buffered images immediately after cancellation.
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
