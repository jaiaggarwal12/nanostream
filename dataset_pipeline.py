#!/usr/bin/env python3
"""
NanoStream Real Video Dataset Pipeline

Downloads public domain test videos, runs real codec benchmarks,
and builds a training dataset for the ML encoder.

Sources:
    - Xiph.org (standard codec test sequences)
    - Netflix VMAF test clips
    - Big Buck Bunny (Blender Foundation, CC)
    - Tears of Steel (Blender Foundation, CC)

Usage:
    python dataset_pipeline.py --download --benchmark --train
    python dataset_pipeline.py --benchmark --videos ./my_videos/
    python dataset_pipeline.py --train --data ./benchmark_results/dataset.csv
"""

import os
import subprocess
import json
import csv
import argparse
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional
import numpy as np

logger = logging.getLogger(__name__)

# ── Public domain test videos ─────────────────────────────────────────────────
TEST_VIDEOS = [
    {
        'name': 'big_buck_bunny_1080p',
        'url': 'https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/1080/Big_Buck_Bunny_1080_10s_5MB.mp4',
        'content_type': 'animation',
        'description': 'Big Buck Bunny (animation, 10s)',
    },
    {
        'name': 'big_buck_bunny_720p',
        'url': 'https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/720/Big_Buck_Bunny_720_10s_1MB.mp4',
        'content_type': 'animation',
        'description': 'Big Buck Bunny 720p (animation, 10s)',
    },
    {
        'name': 'jellyfish_1080p',
        'url': 'https://test-videos.co.uk/vids/jellyfish/mp4/h264/1080/Jellyfish_1080_10s_30MB.mp4',
        'content_type': 'movie',
        'description': 'Jellyfish (natural/movie, 10s)',
    },
    {
        'name': 'jellyfish_720p',
        'url': 'https://test-videos.co.uk/vids/jellyfish/mp4/h264/720/Jellyfish_720_10s_10MB.mp4',
        'content_type': 'movie',
        'description': 'Jellyfish 720p (natural/movie, 10s)',
    },
    {
        'name': 'sintel_trailer',
        'url': 'https://download.blender.org/durian/trailer/sintel_trailer-1080p.mp4',
        'content_type': 'movie',
        'description': 'Sintel trailer (cinematic, 1080p)',
    },
    {
        'name': 'tears_of_steel',
        'url': 'https://download.blender.org/tearsofsteel/tearsofsteel-1080p.mov',
        'content_type': 'movie',
        'description': 'Tears of Steel (cinematic, 1080p)',
    },
]

# ── CRF test matrix ───────────────────────────────────────────────────────────
CRF_SETTINGS = {
    'h264': [18, 22, 26, 30],
    'h265': [20, 24, 28, 32],
    'av1':  [24, 28, 32, 36],
}


class DatasetPipeline:
    """Download real videos, benchmark codecs, build training dataset."""

    def __init__(self, data_dir: str = './dataset'):
        self.data_dir     = Path(data_dir)
        self.video_dir    = self.data_dir / 'videos'
        self.encoded_dir  = self.data_dir / 'encoded'
        self.results_dir  = self.data_dir / 'results'

        for d in [self.video_dir, self.encoded_dir, self.results_dir]:
            d.mkdir(parents=True, exist_ok=True)

    # ── Download ──────────────────────────────────────────────────────────────

    def download_test_videos(self, max_videos: int = None) -> List[Path]:
        """Download public domain test videos."""
        downloaded = []
        videos = TEST_VIDEOS[:max_videos] if max_videos else TEST_VIDEOS

        for v in videos:
            dest = self.video_dir / f"{v['name']}.mp4"
            if dest.exists():
                logger.info(f"Already exists: {dest.name}")
                downloaded.append(dest)
                continue

            logger.info(f"Downloading: {v['description']}")
            try:
                result = subprocess.run(
                    ['curl', '-L', '-o', str(dest), v['url'],
                     '--max-time', '120', '--retry', '3'],
                    capture_output=True, timeout=180
                )
                if result.returncode == 0 and dest.stat().st_size > 10_000:
                    logger.info(f"  ✓ {dest.name} ({dest.stat().st_size // 1024} KB)")
                    downloaded.append(dest)
                else:
                    logger.warning(f"  ✗ Failed: {v['url']}")
                    if dest.exists():
                        dest.unlink()
            except Exception as e:
                logger.error(f"  ✗ Error: {e}")

        logger.info(f"Downloaded {len(downloaded)} videos")
        return downloaded

    # ── Feature extraction ────────────────────────────────────────────────────

    def extract_features(self, video_path: Path) -> Optional[Dict]:
        """Extract content features from video."""
        try:
            import cv2

            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                return None

            total   = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps     = cap.get(cv2.CAP_PROP_FPS)
            width   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height  = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            if total < 5:
                cap.release()
                return None

            indices = np.linspace(0, total - 1, min(10, total), dtype=int)
            frames  = []
            for idx in indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                if ret:
                    frames.append(frame)
            cap.release()

            if len(frames) < 2:
                return None

            # Motion via optical flow
            motions = []
            prev = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY)
            for f in frames[1:]:
                curr = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
                flow = cv2.calcOpticalFlowFarneback(
                    prev, curr, None, 0.5, 3, 15, 3, 5, 1.2, 0
                )
                motions.append(np.sqrt(flow[..., 0]**2 + flow[..., 1]**2).mean())
                prev = curr
            motion = float(np.mean(motions))

            # Edge density
            edges = [
                cv2.Canny(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), 100, 200).mean() / 255
                for f in frames
            ]
            edge_density = float(np.mean(edges))

            # Color variance
            hsv_vars = [
                cv2.cvtColor(f, cv2.COLOR_BGR2HSV)[:, :, 1].std()
                for f in frames
            ]
            color_variance = float(np.mean(hsv_vars))

            # Scene cut rate
            diffs = []
            for i in range(1, len(frames)):
                g1 = cv2.cvtColor(frames[i-1], cv2.COLOR_BGR2GRAY).astype(float)
                g2 = cv2.cvtColor(frames[i],   cv2.COLOR_BGR2GRAY).astype(float)
                diffs.append(np.abs(g1 - g2).mean())
            scene_cut_rate = float(np.mean(diffs))

            # Entropy (using grayscale histogram)
            entropies = []
            for f in frames:
                gray = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
                hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()
                hist = hist / hist.sum()
                hist = hist[hist > 0]
                entropies.append(float(-np.sum(hist * np.log2(hist))))
            entropy = float(np.mean(entropies))

            return {
                'video': video_path.name,
                'width': width,
                'height': height,
                'fps': round(fps, 2),
                'total_frames': total,
                'motion': round(motion, 3),
                'edge_density': round(edge_density, 5),
                'color_variance': round(color_variance, 3),
                'scene_cut_rate': round(scene_cut_rate, 3),
                'entropy': round(entropy, 3),
            }

        except Exception as e:
            logger.error(f"Feature extraction failed for {video_path}: {e}")
            return None

    # ── Encoding benchmark ────────────────────────────────────────────────────

    def benchmark_video(self, video_path: Path, content_type: str) -> List[Dict]:
        """Run full codec × CRF benchmark on one video."""
        features = self.extract_features(video_path)
        if not features:
            logger.warning(f"Could not extract features from {video_path.name}")
            return []

        logger.info(f"Benchmarking: {video_path.name}")
        logger.info(f"  Features: motion={features['motion']:.2f}, "
                   f"entropy={features['entropy']:.2f}, "
                   f"edges={features['edge_density']:.4f}")

        results = []
        original_size = video_path.stat().st_size

        for codec, crfs in CRF_SETTINGS.items():
            for crf in crfs:
                out_path = self.encoded_dir / f"{video_path.stem}_{codec}_crf{crf}.mp4"

                # Encode
                t0 = time.time()
                success = self._encode(video_path, out_path, codec, crf)
                encode_time = time.time() - t0

                if not success or not out_path.exists():
                    continue

                compressed_size = out_path.stat().st_size

                # Quality metrics
                psnr, ssim = self._compute_quality(video_path, out_path)

                ratio = original_size / compressed_size if compressed_size > 0 else 0

                row = {
                    **features,
                    'content_type': content_type,
                    'codec': codec,
                    'crf': crf,
                    'original_size_bytes': original_size,
                    'compressed_size_bytes': compressed_size,
                    'compression_ratio': round(ratio, 3),
                    'bitrate_reduction_pct': round((1 - 1/ratio) * 100, 1) if ratio > 0 else 0,
                    'psnr_db': round(psnr, 3),
                    'ssim': round(ssim, 4),
                    'encode_time_s': round(encode_time, 2),
                }
                results.append(row)

                logger.info(f"  {codec.upper()} CRF{crf}: "
                           f"ratio={ratio:.2f}x, "
                           f"PSNR={psnr:.2f}dB, "
                           f"SSIM={ssim:.4f}")

                # Clean up encoded file to save space
                out_path.unlink()

        return results

    def _encode(
        self,
        input_path: Path,
        output_path: Path,
        codec: str,
        crf: int,
        max_frames: int = 150,  # 5s at 30fps - fast benchmark
    ) -> bool:
        """Encode video with specified codec and CRF."""
        codec_map = {'h264': 'libx264', 'h265': 'libx265', 'av1': 'libaom-av1'}
        vcodec = codec_map[codec]

        cmd = [
            'ffmpeg', '-y',
            '-i', str(input_path),
            '-vframes', str(max_frames),
            '-c:v', vcodec,
            '-crf', str(crf),
            '-preset', 'medium' if codec != 'av1' else '4',
            '-an',  # no audio (faster)
            str(output_path),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, timeout=300)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Encode failed: {e}")
            return False

    def _compute_quality(
        self,
        original: Path,
        compressed: Path,
        num_frames: int = 10,
    ):
        """Compute PSNR and SSIM between original and compressed."""
        try:
            import cv2
            from scipy.ndimage import gaussian_filter

            def read_frames(path, n):
                cap = cv2.VideoCapture(str(path))
                total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                idxs = np.linspace(0, total - 1, min(n, total), dtype=int)
                frames = []
                for idx in idxs:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                    ret, f = cap.read()
                    if ret:
                        frames.append(f.astype(np.float64))
                cap.release()
                return frames

            orig_frames = read_frames(original, num_frames)
            comp_frames = read_frames(compressed, num_frames)

            psnrs, ssims = [], []
            for o, c in zip(orig_frames, comp_frames):
                if o.shape != c.shape:
                    c = cv2.resize(c.astype(np.uint8), (o.shape[1], o.shape[0])).astype(np.float64)

                # PSNR
                mse = np.mean((o - c) ** 2)
                psnr = 100.0 if mse < 1e-10 else float(20 * np.log10(255 / np.sqrt(mse)))
                psnrs.append(psnr)

                # SSIM (per channel, averaged)
                ssim_channels = []
                for ch in range(3):
                    img1 = o[:, :, ch]
                    img2 = c[:, :, ch]
                    C1, C2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
                    m1 = gaussian_filter(img1, 1.5)
                    m2 = gaussian_filter(img2, 1.5)
                    s12 = gaussian_filter(img1 * img2, 1.5) - m1 * m2
                    s1  = gaussian_filter(img1 ** 2, 1.5) - m1 ** 2
                    s2  = gaussian_filter(img2 ** 2, 1.5) - m2 ** 2
                    ssim_channels.append(float(np.mean(
                        (2*m1*m2+C1)*(2*s12+C2) / ((m1**2+m2**2+C1)*(s1+s2+C2))
                    )))
                ssims.append(np.mean(ssim_channels))

            return float(np.mean(psnrs)), float(np.mean(ssims))

        except Exception as e:
            logger.error(f"Quality computation failed: {e}")
            return 0.0, 0.0

    # ── Dataset builder ───────────────────────────────────────────────────────

    def run_full_benchmark(
        self,
        videos: List[Path],
        content_types: Dict[str, str] = None,
    ) -> Path:
        """Run benchmark on all videos and save dataset.

        Args:
            videos: List of video paths
            content_types: Map of video stem → content type

        Returns:
            Path to saved CSV dataset
        """
        all_results = []
        content_types = content_types or {}

        for i, video in enumerate(videos):
            logger.info(f"\n[{i+1}/{len(videos)}] Processing: {video.name}")
            ct = content_types.get(video.stem, 'mixed')
            results = self.benchmark_video(video, ct)
            all_results.extend(results)
            logger.info(f"  → {len(results)} benchmark rows")

        if not all_results:
            logger.error("No benchmark results generated")
            return None

        # Save CSV
        csv_path = self.results_dir / 'dataset.csv'
        fieldnames = list(all_results[0].keys())
        with open(csv_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_results)

        # Save JSON summary
        summary = {
            'total_rows': len(all_results),
            'videos': len(videos),
            'codecs': list(CRF_SETTINGS.keys()),
            'content_types': list(set(r['content_type'] for r in all_results)),
            'avg_psnr': round(np.mean([r['psnr_db'] for r in all_results]), 2),
            'avg_ssim': round(np.mean([r['ssim'] for r in all_results]), 4),
            'avg_compression_ratio': round(np.mean([r['compression_ratio'] for r in all_results]), 2),
        }
        with open(self.results_dir / 'summary.json', 'w') as f:
            json.dump(summary, f, indent=2)

        logger.info(f"\n✓ Dataset saved: {csv_path}")
        logger.info(f"  Rows: {summary['total_rows']}")
        logger.info(f"  Avg PSNR: {summary['avg_psnr']} dB")
        logger.info(f"  Avg SSIM: {summary['avg_ssim']}")
        logger.info(f"  Avg compression: {summary['avg_compression_ratio']}x")

        return csv_path

    def determine_best_codec(self, csv_path: Path) -> Path:
        """
        Post-process benchmark CSV to add 'best_codec' and 'optimal_crf' columns.
        Best = highest SSIM at acceptable PSNR (≥35 dB).
        """
        import pandas as pd

        df = pd.read_csv(csv_path)

        # For each video, find codec+CRF with best SSIM where PSNR ≥ 35dB
        training_rows = []
        for video, group in df.groupby('video'):
            acceptable = group[group['psnr_db'] >= 35.0]
            if acceptable.empty:
                acceptable = group  # fallback: take all

            best = acceptable.loc[acceptable['ssim'].idxmax()]
            row = group.iloc[0].to_dict()
            row['best_codec']  = best['codec']
            row['optimal_crf'] = int(best['crf'])
            training_rows.append(row)

        train_df = pd.DataFrame(training_rows)
        train_path = self.results_dir / 'training_data.csv'
        train_df.to_csv(train_path, index=False)

        logger.info(f"\n✓ Training data saved: {train_path}")
        logger.info(f"  Rows: {len(train_df)}")
        from collections import Counter
        dist = Counter(train_df['best_codec'])
        logger.info(f"  Codec distribution: {dict(dist)}")

        return train_path


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
    )

    parser = argparse.ArgumentParser(description='NanoStream dataset pipeline')
    parser.add_argument('--download',  action='store_true', help='Download test videos')
    parser.add_argument('--benchmark', action='store_true', help='Run codec benchmarks')
    parser.add_argument('--train',     action='store_true', help='Retrain ML model after benchmarking')
    parser.add_argument('--videos',    default=None, help='Directory of your own videos')
    parser.add_argument('--data-dir',  default='./dataset', help='Data directory')
    parser.add_argument('--max',       type=int, default=None, help='Max videos to download')
    args = parser.parse_args()

    pipeline = DatasetPipeline(data_dir=args.data_dir)

    videos = []

    if args.download:
        print("\n── Downloading test videos ──────────────────────────────")
        videos = pipeline.download_test_videos(max_videos=args.max)

    if args.videos:
        video_dir = Path(args.videos)
        videos += list(video_dir.glob('*.mp4')) + list(video_dir.glob('*.mov'))
        print(f"\n── Found {len(videos)} videos in {args.videos} ──")

    if not videos:
        videos = list(pipeline.video_dir.glob('*.mp4'))
        if videos:
            print(f"\n── Using {len(videos)} existing videos ──")

    if args.benchmark:
        if not videos:
            print("No videos found. Run with --download first.")
            return

        # Infer content types from known names
        ct_map = {}
        for v in videos:
            name = v.stem.lower()
            if 'bunny' in name or 'animation' in name:
                ct_map[v.stem] = 'animation'
            elif 'jellyfish' in name or 'nature' in name:
                ct_map[v.stem] = 'movie'
            elif 'sintel' in name or 'steel' in name or 'film' in name:
                ct_map[v.stem] = 'movie'
            else:
                ct_map[v.stem] = 'mixed'

        print(f"\n── Running benchmarks on {len(videos)} videos ──────────")
        csv_path = pipeline.run_full_benchmark(videos, ct_map)

        if csv_path:
            print(f"\n── Determining best codecs per video ────────────────")
            train_path = pipeline.determine_best_codec(csv_path)

            if args.train and train_path:
                print(f"\n── Retraining ML model ──────────────────────────────")
                os.system(f"python train.py --data {train_path}")

    elif args.train:
        train_path = Path(args.data_dir) / 'results' / 'training_data.csv'
        if not train_path.exists():
            print(f"Training data not found: {train_path}")
            print("Run with --benchmark first to generate it.")
            return
        os.system(f"python train.py --data {train_path}")


if __name__ == '__main__':
    main()
