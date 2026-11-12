"""Admit independent model processes using live free memory and reserved budgets."""
import ctypes
import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

PROVIDERS = ('grounding_dino_sam2', 'samurai', 'tapnextpp', 'bootstapir')


def resources():
    gpu = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.free,memory.total', '--format=csv,noheader,nounits'],
                                  text=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    class Memory(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [(name, ctypes.c_ulonglong) for name in
            ('totalPhysical', 'availablePhysical', 'totalPage', 'availablePage', 'totalVirtual', 'availableVirtual', 'extended')]
    status = Memory(); status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise OSError('Cannot determine available RAM')
    free,total = (int(value.strip()) for value in gpu.strip().splitlines()[0].split(','))
    return dict(gpuMiB=free, gpuTotalMiB=total, ramMiB=status.availablePhysical//(1024*1024),
                ramTotalMiB=status.totalPhysical//(1024*1024), commitAvailableMiB=status.availablePage//(1024*1024))


def job_budget(provider, frame_count):
    """MiB admission estimates, including headroom beyond measured torch allocation.

    BootsTAPIR keeps full-sequence 256px features: measured 2114MiB for 565
    frames. It must not use a fixed budget for arbitrarily long recordings.
    """
    gpu = max(3000, 1000 + 3 * frame_count) if provider == 'bootstapir' else 3000 if provider == 'tapnextpp' else 4500
    return dict(providerId=provider, gpuMiB=gpu, ramMiB=3500)


def schedule(jobs, execute, report, cancelled, sample=resources, wait_seconds=60):
    """One retry after OOM, serialized. Never alter checkpoint, FPS or resolution."""
    pending = list(jobs); active = {}; results = {}; attempts = {}; serial = False
    single_tap = len(pending) == 1 and pending[0]['providerId'] == 'tapnextpp'
    baseline = sample(); stalled = time.monotonic()
    for job in pending:
        report(job['providerId'], 'Queued', None)
    with ThreadPoolExecutor(max_workers=4) as pool:
        while pending or active:
            if cancelled():
                for job in pending:
                    results[job['providerId']] = ('Cancelled', None)
                    report(job['providerId'], 'Cancelled', None)
                pending.clear()
            # Live sampling is an admission check, not a condition for collecting completed work.
            capacity = sample() if pending else baseline
            reserved_gpu = sum(j['gpuMiB'] for j in active.values())
            reserved_ram = sum(j['ramMiB'] for j in active.values())
            if not active:
                baseline = capacity
            gpu = min(capacity['gpuMiB'], baseline['gpuMiB']-reserved_gpu)-768
            ram = min(capacity['ramMiB'], baseline['ramMiB']-reserved_ram)-1024
            # Measured 4K/256px TAP: peak working set 4134 MiB, tracking ~1708,
            # private commit 7814 MiB. Allow Windows to page the loading peak,
            # but retain 2.5 GiB physical headroom and 9 GiB commit + 1 GiB reserve.
            tap_commit_admission = single_tap and capacity.get('commitAvailableMiB', 0) >= 10240
            if tap_commit_admission and not active and pending and capacity['ramMiB'] >= 2560:
                ram = max(ram, pending[0]['ramMiB'])
            for job in list(pending):
                if cancelled():break
                if (job['gpuMiB'] + 768 > capacity.get('gpuTotalMiB', float('inf'))
                        or job['ramMiB'] + 1024 > capacity.get('ramTotalMiB', float('inf'))):
                    pending.remove(job)
                    error = (f"This recording exceeds installed memory for {job['providerId']}: "
                             f"requires GPU {job['gpuMiB']} MiB and RAM {job['ramMiB']} MiB plus reserve; "
                             f"capacity {capacity}. Resolution, FPS and model were not changed.")
                    results[job['providerId']] = ('Failed', error)
                    report(job['providerId'], 'Failed', error)
                    continue
                if (serial and active) or job['gpuMiB'] > gpu or job['ramMiB'] > ram:
                    continue
                pending.remove(job)
                future = pool.submit(execute, job)
                active[future] = job
                gpu -= job['gpuMiB']; ram -= job['ramMiB']
                report(job['providerId'], 'Running', None)
                stalled = time.monotonic()
            if pending and not active and time.monotonic()-stalled > wait_seconds:
                for job in pending:
                    shortage = 'system RAM' if job['ramMiB'] > ram else 'GPU memory'
                    error = (f"Not enough free {shortage}. Free RAM: {capacity['ramMiB']} MiB; "
                             f"free GPU memory: {capacity['gpuMiB']} MiB. Model budget: RAM {job['ramMiB']} MiB, "
                             f"GPU {job['gpuMiB']} MiB, with additional memory headroom required. "
                             "Close memory-heavy applications and retry.")
                    if single_tap and shortage == 'system RAM':
                        error = (f"Not enough free memory for TAPNext++. Free RAM: {capacity['ramMiB']} MiB; "
                                 f"available Windows commit: {capacity.get('commitAvailableMiB', 'unknown')} MiB. "
                                 "Requires either 4524 MiB free RAM, or 2560 MiB free RAM and "
                                 "10240 MiB available commit (RAM + page file). Close memory-heavy applications and retry.")
                    results[job['providerId']] = ('Failed', error)
                    report(job['providerId'], 'Failed', error)
                pending.clear()
            done, _ = wait(active, timeout=.2, return_when=FIRST_COMPLETED) if active else ([], [])
            for future in done:
                job = active.pop(future); provider = job['providerId']
                try:
                    value = future.result()
                    # A completed, validated result survives a concurrent cancel.
                    status = 'TrackingReady'
                except Exception as exc:
                    value = str(exc)
                    if 'out of memory' in value.lower() and not attempts.get(provider) and not cancelled():
                        attempts[provider] = 1; serial = True; pending.insert(0, job)
                        report(provider, 'Queued', 'Retrying after GPU OOM with exclusive admission')
                        continue
                    status = 'Cancelled' if cancelled() else 'Failed'
                results[provider] = (status, value)
                report(provider, status, value)
                stalled = time.monotonic()
            if not active and pending:
                time.sleep(.2)
    return results
