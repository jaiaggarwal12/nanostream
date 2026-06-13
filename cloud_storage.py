"""
NanoStream Cloud Storage
Upload HLS packages to Backblaze B2 and serve via public URL.

Why Backblaze B2:
    - No credit card required to sign up
    - Free tier: 10 GB storage, 1 GB/day download
    - S3-compatible API (boto3 works unchanged)
    - Very cheap beyond free tier ($0.006/GB storage, $0.01/GB download)

Setup:
    1. Go to https://www.backblaze.com/sign-up/cloud-storage
    2. Sign up — no card needed
    3. Buckets → Create a Bucket → name: 'nanostream', set to Public
    4. Account → App Keys → Add a New Application Key
       - Name: nanostream
       - Access: Read and Write
       - Bucket: nanostream
    5. Copy the values shown (only shown once):
       - keyID       → B2_KEY_ID
       - applicationKey → B2_APPLICATION_KEY
    6. Bucket page → Bucket Settings → copy the Endpoint
       e.g. s3.us-west-004.backblazeb2.com  → B2_ENDPOINT
    7. Set environment variables:

       B2_KEY_ID=your_key_id
       B2_APPLICATION_KEY=your_application_key
       B2_BUCKET=nanostream
       B2_ENDPOINT=s3.us-west-004.backblazeb2.com
       B2_PUBLIC_URL=https://f004.backblazeb2.com/file/nanostream
       # Public URL format: https://<endpoint-short>.backblazeb2.com/file/<bucket>
       # e.g. if endpoint is s3.us-west-004, short = f004
"""

import os
import logging
from pathlib import Path
from typing import Dict, Optional
import mimetypes

logger = logging.getLogger(__name__)


class CloudStorage:
    """Upload and manage HLS packages on Backblaze B2 (S3-compatible API)."""

    def __init__(self):
        """Initialize from environment variables."""
        self.key_id          = os.environ.get('B2_KEY_ID')
        self.app_key         = os.environ.get('B2_APPLICATION_KEY')
        self.bucket          = os.environ.get('B2_BUCKET', 'nanostream')
        self.endpoint        = os.environ.get('B2_ENDPOINT', '')   # e.g. s3.us-west-004.backblazeb2.com
        self.public_url      = os.environ.get('B2_PUBLIC_URL', '').rstrip('/')
        self.configured      = bool(self.key_id and self.app_key and self.endpoint)

        if self.configured:
            self._client = self._make_client()
            logger.info(f"B2 storage configured: bucket={self.bucket}")
        else:
            self._client = None
            logger.warning(
                "Backblaze B2 not configured. Set B2_KEY_ID, B2_APPLICATION_KEY, "
                "B2_ENDPOINT environment variables. Storage uploads will be skipped."
            )

    def _make_client(self):
        """Create boto3 S3 client pointed at Backblaze B2."""
        try:
            import boto3
            return boto3.client(
                's3',
                endpoint_url=f'https://{self.endpoint}',
                aws_access_key_id=self.key_id,
                aws_secret_access_key=self.app_key,
                region_name='us-east-1',  # B2 ignores region but boto3 requires a value
            )
        except ImportError:
            logger.error("boto3 not installed. Run: pip install boto3")
            return None

    def upload_hls_package(self, hls_dir: str, video_id: str) -> Optional[Dict]:
        """
        Upload complete HLS package to Backblaze B2.

        Args:
            hls_dir: Local directory containing master.m3u8 and variant folders
            video_id: Unique ID for this video (used as key prefix)

        Returns:
            Dict with public URLs, or None if upload failed
        """
        if not self.configured or not self._client:
            logger.warning("B2 not configured — skipping cloud upload.")
            return None

        hls_path = Path(hls_dir)
        if not hls_path.exists():
            logger.error(f"HLS directory not found: {hls_dir}")
            return None

        uploaded = []
        failed = []

        for file_path in sorted(hls_path.rglob('*')):
            if not file_path.is_file():
                continue

            relative = file_path.relative_to(hls_path)
            b2_key = f"videos/{video_id}/{relative}".replace('\\', '/')
            content_type = self._get_content_type(file_path)

            try:
                self._client.upload_file(
                    str(file_path),
                    self.bucket,
                    b2_key,
                    ExtraArgs={
                        'ContentType': content_type,
                        'CacheControl': self._get_cache_control(file_path),
                    }
                )
                uploaded.append(b2_key)
                logger.debug(f"Uploaded: {b2_key}")

            except Exception as e:
                logger.error(f"Failed to upload {b2_key}: {e}")
                failed.append(b2_key)

        if failed:
            logger.warning(f"{len(failed)} files failed to upload")

        master_url = f"{self.public_url}/videos/{video_id}/master.m3u8"
        logger.info(f"Uploaded {len(uploaded)} files for video {video_id}")
        logger.info(f"Master playlist: {master_url}")

        return {
            'video_id': video_id,
            'master_url': master_url,
            'files_uploaded': len(uploaded),
            'files_failed': len(failed),
            'bucket': self.bucket,
            'provider': 'backblaze-b2',
        }

    def delete_video(self, video_id: str) -> bool:
        """Delete all files for a video from B2."""
        if not self.configured or not self._client:
            return False

        try:
            prefix = f"videos/{video_id}/"
            paginator = self._client.get_paginator('list_objects_v2')

            keys = []
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for obj in page.get('Contents', []):
                    keys.append({'Key': obj['Key']})

            if not keys:
                logger.warning(f"No files found for video: {video_id}")
                return False

            for i in range(0, len(keys), 1000):
                batch = keys[i:i + 1000]
                self._client.delete_objects(
                    Bucket=self.bucket,
                    Delete={'Objects': batch}
                )

            logger.info(f"Deleted {len(keys)} files for video {video_id}")
            return True

        except Exception as e:
            logger.error(f"Delete failed: {e}")
            return False

    def list_videos(self) -> list:
        """List all video IDs in the bucket."""
        if not self.configured or not self._client:
            return []

        try:
            paginator = self._client.get_paginator('list_objects_v2')
            video_ids = set()

            for page in paginator.paginate(Bucket=self.bucket, Prefix='videos/', Delimiter='/'):
                for prefix in page.get('CommonPrefixes', []):
                    parts = prefix['Prefix'].strip('/').split('/')
                    if len(parts) >= 2:
                        video_ids.add(parts[1])

            return sorted(video_ids)

        except Exception as e:
            logger.error(f"List failed: {e}")
            return []

    def get_public_url(self, video_id: str) -> str:
        """Get public HLS URL for a video."""
        return f"{self.public_url}/videos/{video_id}/master.m3u8"

    @staticmethod
    def _get_content_type(file_path: Path) -> str:
        suffix = file_path.suffix.lower()
        types = {
            '.m3u8': 'application/x-mpegURL',
            '.ts':   'video/MP2T',
            '.mp4':  'video/mp4',
            '.vtt':  'text/vtt',
        }
        return types.get(suffix, mimetypes.guess_type(str(file_path))[0] or 'application/octet-stream')

    @staticmethod
    def _get_cache_control(file_path: Path) -> str:
        suffix = file_path.suffix.lower()
        if suffix == '.ts':
            return 'public, max-age=31536000, immutable'
        elif suffix == '.m3u8':
            return 'public, max-age=5'
        return 'public, max-age=86400'


class DeploymentManager:
    """Manage complete video deployment lifecycle."""

    def __init__(self):
        self.storage = CloudStorage()

    def deploy_video(self, video_path: str, video_id: str = None,
                     max_resolution: str = '1080p') -> Optional[Dict]:
        """
        Full pipeline: analyze → generate HLS → upload to B2 → return public URL.
        """
        import uuid
        from analyzer import ContentAnalyzer
        from hls_generator import HLSGenerator
        from bitrate_ladder import BitrateLadder
        import cv2

        video_id = video_id or uuid.uuid4().hex[:10]

        logger.info(f"[1/3] Analyzing {video_path}...")
        analyzer = ContentAnalyzer()
        analysis = analyzer.analyze(video_path)

        logger.info(f"[2/3] Generating HLS package...")
        cap = cv2.VideoCapture(video_path)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        ladder = BitrateLadder(w, h).generate(max_resolution=max_resolution)
        hls_dir = f'./hls_output/{video_id}'

        gen = HLSGenerator(output_dir=hls_dir)
        pkg = gen.generate_hls_package(
            video_path, ladder, content_type=analysis['content_type']
        )

        if not pkg:
            logger.error("HLS generation failed")
            return None

        logger.info(f"[3/3] Uploading to Backblaze B2...")
        result = self.storage.upload_hls_package(hls_dir, video_id)

        if result:
            result['content_type'] = analysis['content_type']
            result['hls_dir'] = hls_dir
            logger.info(f"\n✓ Deployed: {result['master_url']}")

        return result

    def undeploy_video(self, video_id: str) -> bool:
        return self.storage.delete_video(video_id)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    storage = CloudStorage()

    if not storage.configured:
        print("\nBackblaze B2 not configured. To set up (no card needed):")
        print("  1. Sign up free: https://www.backblaze.com/sign-up/cloud-storage")
        print("  2. Buckets → Create bucket 'nanostream' (set Public)")
        print("  3. Account → App Keys → Add New Application Key")
        print("  4. Set environment variables:")
        print("     B2_KEY_ID=your_key_id")
        print("     B2_APPLICATION_KEY=your_app_key")
        print("     B2_BUCKET=nanostream")
        print("     B2_ENDPOINT=s3.us-west-004.backblazeb2.com")
        print("     B2_PUBLIC_URL=https://f004.backblazeb2.com/file/nanostream")
    else:
        videos = storage.list_videos()
        print(f"\nVideos in B2 ({storage.bucket}): {len(videos)}")
        for v in videos:
            print(f"  {v}: {storage.get_public_url(v)}")
