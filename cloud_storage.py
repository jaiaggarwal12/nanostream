"""
NanoStream Cloud Storage
Upload HLS packages to Cloudflare R2 and serve via public URL.

Why Cloudflare R2:
    - Zero egress fees (vs AWS S3 $0.085/GB)
    - S3-compatible API (boto3 works unchanged)
    - Built-in CDN via Workers
    - Free tier: 10GB storage, 1M requests/month

Setup:
    1. Create Cloudflare account → R2 → New bucket → 'nanostream'
    2. R2 → Manage R2 API tokens → Create token (Object Read & Write)
    3. Copy Account ID from R2 dashboard
    4. Set environment variables:

       export R2_ACCOUNT_ID=your_account_id
       export R2_ACCESS_KEY_ID=your_access_key
       export R2_SECRET_ACCESS_KEY=your_secret_key
       export R2_BUCKET=nanostream
       export R2_PUBLIC_URL=https://pub-xxxx.r2.dev  # from R2 public access settings

Alternatives:
    AWS S3:  Change endpoint_url to None, use standard boto3
    GCP GCS: Use google-cloud-storage library instead
    Azure:   Use azure-storage-blob library
"""

import os
import logging
from pathlib import Path
from typing import Dict, Optional
import mimetypes

logger = logging.getLogger(__name__)


class CloudStorage:
    """Upload and manage HLS packages on Cloudflare R2 (S3-compatible)."""

    def __init__(self):
        """Initialize from environment variables."""
        self.account_id       = os.environ.get('R2_ACCOUNT_ID')
        self.access_key       = os.environ.get('R2_ACCESS_KEY_ID')
        self.secret_key       = os.environ.get('R2_SECRET_ACCESS_KEY')
        self.bucket           = os.environ.get('R2_BUCKET', 'nanostream')
        self.public_url       = os.environ.get('R2_PUBLIC_URL', '').rstrip('/')
        self.configured       = bool(self.account_id and self.access_key and self.secret_key)

        if self.configured:
            self._client = self._make_client()
            logger.info(f"R2 storage configured: bucket={self.bucket}")
        else:
            self._client = None
            logger.warning(
                "R2 not configured. Set R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, "
                "R2_SECRET_ACCESS_KEY environment variables."
            )

    def _make_client(self):
        """Create boto3 S3 client pointed at Cloudflare R2."""
        try:
            import boto3
            return boto3.client(
                's3',
                endpoint_url=f'https://{self.account_id}.r2.cloudflarestorage.com',
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name='auto',
            )
        except ImportError:
            logger.error("boto3 not installed. Run: pip install boto3")
            return None

    def upload_hls_package(
        self,
        hls_dir: str,
        video_id: str,
    ) -> Optional[Dict]:
        """
        Upload complete HLS package to R2.

        Args:
            hls_dir: Local directory containing master.m3u8 and variant folders
            video_id: Unique ID for this video (used as R2 prefix)

        Returns:
            Dict with public URLs, or None if upload failed
        """
        if not self.configured or not self._client:
            logger.error("R2 not configured. Cannot upload.")
            return None

        hls_path = Path(hls_dir)
        if not hls_path.exists():
            logger.error(f"HLS directory not found: {hls_dir}")
            return None

        uploaded = []
        failed = []

        # Upload all files in HLS directory
        for file_path in sorted(hls_path.rglob('*')):
            if not file_path.is_file():
                continue

            # R2 key = video_id/relative_path
            relative = file_path.relative_to(hls_path)
            r2_key = f"videos/{video_id}/{relative}"

            content_type = self._get_content_type(file_path)

            try:
                self._client.upload_file(
                    str(file_path),
                    self.bucket,
                    r2_key,
                    ExtraArgs={
                        'ContentType': content_type,
                        'CacheControl': self._get_cache_control(file_path),
                    }
                )
                uploaded.append(r2_key)
                logger.debug(f"Uploaded: {r2_key}")

            except Exception as e:
                logger.error(f"Failed to upload {r2_key}: {e}")
                failed.append(r2_key)

        if failed:
            logger.warning(f"{len(failed)} files failed to upload")

        master_url = f"{self.public_url}/videos/{video_id}/master.m3u8"
        player_url = f"{self.public_url}/player.html?v={video_id}"

        logger.info(f"Uploaded {len(uploaded)} files for video {video_id}")
        logger.info(f"Master playlist: {master_url}")

        return {
            'video_id': video_id,
            'master_url': master_url,
            'player_url': player_url,
            'files_uploaded': len(uploaded),
            'files_failed': len(failed),
            'bucket': self.bucket,
        }

    def delete_video(self, video_id: str) -> bool:
        """Delete all files for a video from R2."""
        if not self.configured or not self._client:
            return False

        try:
            # List all objects with this video prefix
            prefix = f"videos/{video_id}/"
            paginator = self._client.get_paginator('list_objects_v2')

            keys = []
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for obj in page.get('Contents', []):
                    keys.append({'Key': obj['Key']})

            if not keys:
                logger.warning(f"No files found for video: {video_id}")
                return False

            # Delete in batches of 1000
            for i in range(0, len(keys), 1000):
                batch = keys[i:i+1000]
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
                    # Extract video_id from 'videos/VIDEO_ID/'
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
        """Get correct MIME type for HLS files."""
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
        """
        Set aggressive caching for segments (immutable),
        shorter TTL for manifests (may update).
        """
        suffix = file_path.suffix.lower()
        if suffix == '.ts':
            return 'public, max-age=31536000, immutable'   # 1 year for segments
        elif suffix == '.m3u8':
            return 'public, max-age=5'                      # 5s for playlists
        return 'public, max-age=86400'


class DeploymentManager:
    """Manage complete video deployment lifecycle."""

    def __init__(self):
        self.storage = CloudStorage()

    def deploy_video(
        self,
        video_path: str,
        video_id: str = None,
        max_resolution: str = '1080p',
    ) -> Optional[Dict]:
        """
        Full deployment pipeline:
        1. Analyze content
        2. Generate HLS package
        3. Upload to R2
        4. Return public URL

        Args:
            video_path: Local video path
            video_id: Optional custom ID (auto-generated if None)
            max_resolution: Max resolution to encode

        Returns:
            Deployment info with public URL
        """
        import uuid
        from analyzer import ContentAnalyzer
        from hls_generator import HLSGenerator
        from bitrate_ladder import BitrateLadder
        import cv2

        video_id = video_id or uuid.uuid4().hex[:10]

        # Step 1: Analyze
        logger.info(f"[1/3] Analyzing {video_path}...")
        analyzer = ContentAnalyzer()
        analysis = analyzer.analyze(video_path)

        # Step 2: Generate HLS
        logger.info(f"[2/3] Generating HLS package...")
        cap = cv2.VideoCapture(video_path)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        ladder = BitrateLadder(w, h).generate(max_resolution=max_resolution)
        hls_dir = f'./hls_output/{video_id}'

        gen = HLSGenerator(output_dir=hls_dir)
        pkg = gen.generate_hls_package(
            video_path, ladder,
            content_type=analysis['content_type']
        )

        if not pkg:
            logger.error("HLS generation failed")
            return None

        # Step 3: Upload
        logger.info(f"[3/3] Uploading to Cloudflare R2...")
        result = self.storage.upload_hls_package(hls_dir, video_id)

        if result:
            result['content_type'] = analysis['content_type']
            result['hls_dir'] = hls_dir
            logger.info(f"\n✓ Deployed: {result['master_url']}")

        return result

    def undeploy_video(self, video_id: str) -> bool:
        """Remove video from cloud storage."""
        return self.storage.delete_video(video_id)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    storage = CloudStorage()

    if not storage.configured:
        print("\nR2 not configured. To set up:")
        print("  1. Create Cloudflare account")
        print("  2. Go to R2 → Create bucket 'nanostream'")
        print("  3. Create API token with Object Read & Write")
        print("  4. Set environment variables:")
        print("     export R2_ACCOUNT_ID=your_account_id")
        print("     export R2_ACCESS_KEY_ID=your_key")
        print("     export R2_SECRET_ACCESS_KEY=your_secret")
        print("     export R2_BUCKET=nanostream")
        print("     export R2_PUBLIC_URL=https://pub-xxxx.r2.dev")
        print("\nThen run:")
        print("  python cloud_storage.py")
        print("  python cli.py full video.mp4 --deploy")
    else:
        videos = storage.list_videos()
        print(f"\nVideos in R2 ({storage.bucket}): {len(videos)}")
        for v in videos:
            print(f"  {v}: {storage.get_public_url(v)}")
