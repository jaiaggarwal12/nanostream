"""
NanoStream Job Queue
Celery + Redis distributed encoding queue with fallback to in-memory queue.

Architecture:
    CLI / API
        ↓
    submit_job()
        ↓
    Celery Task → Redis Broker
        ↓               ↓
    Worker 1       Worker 2  ...N workers in parallel
        ↓
    HLSGenerator / Encoder
        ↓
    Results stored in Redis (or JSON fallback)

Usage (with Redis running):
    # Start worker
    celery -A job_queue worker --loglevel=info --concurrency=4

    # Submit job from Python
    from job_queue import JobQueue
    q = JobQueue()
    job_id = q.submit('video.mp4', codec='h265')

    # Check status
    print(q.status(job_id))

Fallback (no Redis):
    Falls back to JSON-based queue automatically.
    Run jobs in-process with q.run_next().
"""

import json
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Try importing Celery/Redis; fall back gracefully ─────────────────────────
import os as _os

_REDIS_URL = _os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

try:
    from celery import Celery
    from celery.result import AsyncResult
    import redis as redis_lib

    _redis_client = redis_lib.Redis.from_url(_REDIS_URL, socket_connect_timeout=2)
    _redis_client.ping()
    REDIS_AVAILABLE = True
    logger.info("Redis connected — using Celery queue")
except Exception:
    REDIS_AVAILABLE = False
    logger.info("Redis not available — using JSON fallback queue")


# ── Celery app (only used when Redis is live) ─────────────────────────────────
if REDIS_AVAILABLE:
    _broker_url  = _REDIS_URL
    _backend_url = _REDIS_URL.replace('/0', '/1') if _REDIS_URL.endswith('/0') else _REDIS_URL + '/1'

    celery_app = Celery(
        'nanostream',
        broker=_broker_url,
        backend=_backend_url,
    )
    celery_app.conf.update(
        task_serializer='json',
        result_serializer='json',
        accept_content=['json'],
        result_expires=86400,   # 24h
        worker_prefetch_multiplier=1,
        task_acks_late=True,    # Don't ack until complete (safe re-queue on crash)
    )

    @celery_app.task(bind=True, name='nanostream.encode_video', max_retries=3)
    def encode_video_task(self, job_id: str, video_path: str, resolutions: list,
                          codec: str, content_type: str, output_dir: str):
        """
        Celery task: encode one video to HLS.
        Retries up to 3 times on failure.
        """
        try:
            from hls_generator import HLSGenerator

            # Update state
            self.update_state(state='PROGRESS', meta={'progress': 5, 'step': 'starting'})

            gen = HLSGenerator(output_dir=output_dir)
            self.update_state(state='PROGRESS', meta={'progress': 10, 'step': 'encoding'})

            result = gen.generate_hls_package(
                video_path, resolutions, content_type=content_type
            )

            return {
                'job_id': job_id,
                'status': 'completed',
                'master_playlist': result['master_playlist'] if result else None,
                'variants': len(resolutions),
            }

        except Exception as exc:
            logger.error(f"Task {job_id} failed: {exc}")
            raise self.retry(exc=exc, countdown=30)


# ── Fallback in-memory/JSON queue ────────────────────────────────────────────
class _JSONQueue:
    """Persistent JSON-backed queue for environments without Redis."""

    def __init__(self, path: str = './queue_state.json'):
        self.path = Path(path)
        self._jobs: Dict[str, dict] = {}
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                with open(self.path) as f:
                    self._jobs = json.load(f)
            except Exception:
                self._jobs = {}

    def _save(self):
        with open(self.path, 'w') as f:
            json.dump(self._jobs, f, indent=2)

    def put(self, job: dict):
        self._jobs[job['job_id']] = job
        self._save()

    def get(self, job_id: str) -> Optional[dict]:
        return self._jobs.get(job_id)

    def update(self, job_id: str, **kwargs):
        if job_id in self._jobs:
            self._jobs[job_id].update(kwargs)
            self._save()

    def all(self, status: str = None) -> List[dict]:
        jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j.get('status') == status]
        return sorted(jobs, key=lambda j: j['created_at'], reverse=True)

    def stats(self) -> dict:
        jobs = list(self._jobs.values())
        return {
            'total': len(jobs),
            'queued':     sum(1 for j in jobs if j['status'] == 'queued'),
            'processing': sum(1 for j in jobs if j['status'] == 'processing'),
            'completed':  sum(1 for j in jobs if j['status'] == 'completed'),
            'failed':     sum(1 for j in jobs if j['status'] == 'failed'),
            'backend':    'json',
        }

    def next_queued(self) -> Optional[dict]:
        for job in sorted(self._jobs.values(), key=lambda j: j['created_at']):
            if job['status'] == 'queued':
                return job
        return None


# ── Public JobQueue interface ─────────────────────────────────────────────────
class JobQueue:
    """
    Unified job queue.

    With Redis: submits Celery tasks, tracks via Redis backend.
    Without Redis: uses JSON file queue, processes in-process.
    """

    def __init__(self, output_root: str = './hls_output'):
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self._json_queue = _JSONQueue()
        self.backend = 'redis+celery' if REDIS_AVAILABLE else 'json'

    def submit(
        self,
        video_path: str,
        resolutions: List[Dict],
        codec: str = 'h265',
        content_type: str = 'movie',
    ) -> str:
        """
        Submit encoding job.

        Args:
            video_path: Path to source video
            resolutions: List of {name, width, height} dicts
            codec: 'h264', 'h265', or 'av1'
            content_type: Detected content type

        Returns:
            job_id string
        """
        job_id = uuid.uuid4().hex[:10]
        output_dir = str(self.output_root / job_id)
        now = datetime.utcnow().isoformat()

        job = {
            'job_id': job_id,
            'video_path': str(video_path),
            'resolutions': resolutions,
            'codec': codec,
            'content_type': content_type,
            'output_dir': output_dir,
            'status': 'queued',
            'progress': 0,
            'created_at': now,
            'started_at': None,
            'completed_at': None,
            'celery_task_id': None,
            'stream_url': None,
            'error': None,
        }

        if REDIS_AVAILABLE:
            task = encode_video_task.apply_async(
                args=[job_id, str(video_path), resolutions, codec, content_type, output_dir],
                task_id=job_id,
            )
            job['celery_task_id'] = task.id
            job['status'] = 'queued'
            logger.info(f"Celery task submitted: {job_id}")
        else:
            logger.info(f"JSON queue: job submitted: {job_id}")

        self._json_queue.put(job)
        return job_id

    def status(self, job_id: str) -> Optional[Dict]:
        """
        Get job status.

        With Celery: real-time progress from Redis.
        Without: JSON state.
        """
        job = self._json_queue.get(job_id)

        if REDIS_AVAILABLE and job and job.get('celery_task_id'):
            result = AsyncResult(job['celery_task_id'], app=celery_app)
            state = result.state

            if state == 'PROGRESS':
                meta = result.info or {}
                job['status'] = 'processing'
                job['progress'] = meta.get('progress', 0)
                job['step'] = meta.get('step', '')
            elif state == 'SUCCESS':
                job['status'] = 'completed'
                job['progress'] = 100
                job['result'] = result.result
                if not job['completed_at']:
                    job['completed_at'] = datetime.utcnow().isoformat()
                self._json_queue.update(job_id, **{k: job[k] for k in
                    ['status', 'progress', 'completed_at']})
            elif state == 'FAILURE':
                job['status'] = 'failed'
                job['error'] = str(result.result)
                self._json_queue.update(job_id, status='failed', error=job['error'])
            elif state == 'STARTED':
                job['status'] = 'processing'
                if not job['started_at']:
                    self._json_queue.update(job_id, started_at=datetime.utcnow().isoformat())

        return job

    def run_next(self) -> Optional[str]:
        """
        Process next queued job in-process (fallback mode only).

        Returns:
            job_id of processed job, or None
        """
        if REDIS_AVAILABLE:
            logger.warning("run_next() is for fallback mode; Celery handles this automatically")
            return None

        job = self._json_queue.next_queued()
        if not job:
            return None

        job_id = job['job_id']
        self._json_queue.update(job_id,
            status='processing',
            started_at=datetime.utcnow().isoformat(),
        )

        try:
            from hls_generator import HLSGenerator
            gen = HLSGenerator(output_dir=job['output_dir'])
            result = gen.generate_hls_package(
                job['video_path'],
                job['resolutions'],
                content_type=job['content_type'],
            )

            # Auto-upload to Backblaze B2 if configured (survives restarts)
            stream_url = None
            try:
                from cloud_storage import CloudStorage
                storage = CloudStorage()
                if storage.configured:
                    logger.info(f"Uploading job {job_id} to B2 bucket={storage.bucket}")
                    upload = storage.upload_hls_package(job['output_dir'], job_id)
                    if upload:
                        stream_url = upload.get('master_url')
                        logger.info(f"Job {job_id} B2 upload complete: {stream_url}")
                    else:
                        logger.error(f"Job {job_id} B2 upload returned None")
                else:
                    logger.warning(f"Job {job_id} B2 not configured — stream will be local only. "
                                   f"B2_KEY_ID set: {bool(_os.environ.get('B2_KEY_ID'))}, "
                                   f"B2_APPLICATION_KEY set: {bool(_os.environ.get('B2_APPLICATION_KEY'))}, "
                                   f"B2_ENDPOINT set: {bool(_os.environ.get('B2_ENDPOINT'))}")
            except Exception as upload_exc:
                logger.error(f"B2 upload failed for job {job_id}: {upload_exc}")

            self._json_queue.update(job_id,
                status='completed',
                progress=100,
                completed_at=datetime.utcnow().isoformat(),
                stream_url=stream_url,
            )
            logger.info(f"Job {job_id} completed")
        except Exception as exc:
            self._json_queue.update(job_id,
                status='failed',
                error=str(exc),
                completed_at=datetime.utcnow().isoformat(),
            )
            logger.error(f"Job {job_id} failed: {exc}")

        return job_id

    def list_jobs(self, status: str = None) -> List[Dict]:
        """List all jobs, optionally filtered by status."""
        return self._json_queue.all(status=status)

    def stats(self) -> Dict:
        """Queue statistics."""
        s = self._json_queue.stats()
        s['backend'] = self.backend
        s['redis_available'] = REDIS_AVAILABLE
        return s

    def cancel(self, job_id: str) -> bool:
        """Cancel a queued job."""
        job = self._json_queue.get(job_id)
        if not job:
            return False
        if job['status'] != 'queued':
            logger.warning(f"Cannot cancel job in state: {job['status']}")
            return False

        if REDIS_AVAILABLE and job.get('celery_task_id'):
            AsyncResult(job['celery_task_id'], app=celery_app).revoke(terminate=True)

        self._json_queue.update(job_id, status='cancelled')
        return True


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    q = JobQueue()
    stats = q.stats()
    print(f"\nJob Queue Status")
    print(f"  Backend:   {stats['backend']}")
    print(f"  Redis:     {'✓ connected' if stats['redis_available'] else '✗ not available (using JSON fallback)'}")
    print(f"  Total:     {stats['total']}")
    print(f"  Queued:    {stats['queued']}")
    print(f"  Processing:{stats['processing']}")
    print(f"  Completed: {stats['completed']}")
    print(f"  Failed:    {stats['failed']}")

    # Simulate submitting a job
    test_resolutions = [
        {'name': '480p', 'width': 854,  'height': 480},
        {'name': '720p', 'width': 1280, 'height': 720},
    ]

    job_id = q.submit(
        video_path='test_video.mp4',
        resolutions=test_resolutions,
        codec='h265',
        content_type='movie',
    )
    print(f"\nSubmitted test job: {job_id}")
    print(f"Status: {q.status(job_id)['status']}")
    print(f"\nAll jobs: {len(q.list_jobs())}")
