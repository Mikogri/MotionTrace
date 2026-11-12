import threading
import time
import unittest
from comparison.scheduler import PROVIDERS, schedule


class ComparisonSchedulerTests(unittest.TestCase):
    def test_all_four_run_once_and_budget_limits_concurrency(self):
        active = maximum = 0
        lock = threading.Lock(); events = []; called = []
        def execute(job):
            nonlocal active, maximum
            with lock:
                active += 1; maximum = max(maximum, active); called.append(job['providerId'])
            time.sleep(.01)
            with lock: active -= 1
            return job['providerId']
        jobs = [dict(providerId=p, gpuMiB=4000, ramMiB=1000) for p in PROVIDERS]
        result = schedule(jobs, execute, lambda *a: events.append(a), lambda:False,
                          sample=lambda:dict(gpuMiB=7000, ramMiB=16000))
        self.assertEqual(set(called), set(PROVIDERS)); self.assertEqual(maximum, 1)
        self.assertEqual([e[1] for e in events[:4]], ['Queued']*4)
        self.assertTrue(all(s=='TrackingReady' for s,v in result.values()))

    def test_failure_does_not_remove_other_results(self):
        def execute(job):
            if job['providerId']=='samurai': raise ValueError('model failure')
            return 'measured'
        result = schedule([dict(providerId=p,gpuMiB=100,ramMiB=100) for p in PROVIDERS],execute,
                          lambda *a:None,lambda:False,sample=lambda:dict(gpuMiB=7000,ramMiB=16000))
        self.assertEqual(result['samurai'][0],'Failed')
        self.assertEqual(sum(s=='TrackingReady' for s,v in result.values()),3)

    def test_oom_retry_is_bounded_and_cancel_never_starts_queued_work(self):
        called=[]
        def execute(job):
            called.append(1); raise RuntimeError('CUDA out of memory')
        job=dict(providerId='tapnextpp',gpuMiB=100,ramMiB=100)
        result=schedule([job],execute,lambda *a:None,lambda:False,sample=lambda:dict(gpuMiB=7000,ramMiB=16000))
        self.assertEqual(len(called),2);self.assertEqual(result['tapnextpp'][0],'Failed')
        called.clear()
        result=schedule([job],execute,lambda *a:None,lambda:True,sample=lambda:dict(gpuMiB=7000,ramMiB=16000))
        self.assertFalse(called);self.assertEqual(result['tapnextpp'][0],'Cancelled')

if __name__=='__main__':unittest.main()
