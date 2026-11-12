"""Host wall-clock stage timings; no extra GPU synchronization in inference."""
from contextlib import contextmanager
from time import perf_counter


class StageTimings:
    def __init__(self):
        self.started=perf_counter()
        self.seconds={}

    @contextmanager
    def measure(self,name):
        started=perf_counter()
        try:
            yield
        finally:
            self.seconds[name]=self.seconds.get(name,0)+perf_counter()-started

    def snapshot(self,frames=0,**extra):
        return dict(elapsedSeconds=round(perf_counter()-self.started,6),decodedFrames=frames,
                    stagesSeconds={name:round(seconds,6) for name,seconds in self.seconds.items()},**extra)
