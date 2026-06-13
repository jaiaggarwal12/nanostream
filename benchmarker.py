"""
NanoStream Benchmarker
Compare H.264, H.265, and AV1 with real metrics
"""

import os
import subprocess
from pathlib import Path
from typing import Dict, List
import logging
import json
import numpy as np

logger = logging.getLogger(__name__)


class Benchmarker:
    """Benchmark and compare video codecs."""
    
    def __init__(self, output_dir: str = './benchmark_results'):
        """Initialize benchmarker.
        
        Args:
            output_dir: Directory to save benchmark results
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def compute_metrics(
        self,
        original_path: str,
        compressed_path: str,
        codec_name: str,
    ) -> Dict:
        """Compute quality metrics between original and compressed.
        
        Args:
            original_path: Path to original video
            compressed_path: Path to compressed video
            codec_name: Name of codec used
            
        Returns:
            Dict with PSNR, SSIM, file sizes
        """
        logger.info(f"Computing metrics for {codec_name}...")
        
        # Get file sizes
        original_size = os.path.getsize(original_path)
        compressed_size = os.path.getsize(compressed_path)
        
        # Extract 10 frames from each and compare
        original_frames = self._extract_frames(original_path, num_frames=10)
        compressed_frames = self._extract_frames(compressed_path, num_frames=10)
        
        if not original_frames or not compressed_frames:
            logger.warning(f"Could not extract frames for {codec_name}")
            return None
        
        # Compute PSNR and SSIM
        psnr_values = []
        ssim_values = []
        
        for orig, comp in zip(original_frames, compressed_frames):
            # Resize compressed to match original if needed
            if orig.shape != comp.shape:
                comp = self._resize_frame(comp, orig.shape)
            
            psnr = self._compute_psnr(orig, comp)
            ssim = self._compute_ssim(orig, comp)
            
            if psnr > 0:
                psnr_values.append(psnr)
            if ssim > 0:
                ssim_values.append(ssim)
        
        compression_ratio = original_size / compressed_size if compressed_size > 0 else 0
        
        return {
            'codec': codec_name,
            'original_size_mb': original_size / (1024 ** 2),
            'compressed_size_mb': compressed_size / (1024 ** 2),
            'compression_ratio': compression_ratio,
            'bitrate_reduction_percent': ((original_size - compressed_size) / original_size * 100) if original_size > 0 else 0,
            'psnr_mean_db': float(np.mean(psnr_values)) if psnr_values else 0,
            'psnr_std_db': float(np.std(psnr_values)) if psnr_values else 0,
            'ssim_mean': float(np.mean(ssim_values)) if ssim_values else 0,
            'ssim_std': float(np.std(ssim_values)) if ssim_values else 0,
        }
    
    @staticmethod
    def _extract_frames(video_path: str, num_frames: int = 10) -> List:
        """Extract sample frames from video."""
        import cv2
        
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return []
        
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_indices = np.linspace(0, total_frames - 1, num_frames, dtype=int)
        
        frames = []
        for idx in frame_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if ret:
                frames.append(frame)
        
        cap.release()
        return frames
    
    @staticmethod
    def _resize_frame(frame, target_shape):
        """Resize frame to match target shape."""
        import cv2
        return cv2.resize(frame, (target_shape[1], target_shape[0]))
    
    @staticmethod
    def _compute_psnr(img1, img2, max_val=255) -> float:
        """Compute PSNR between two images."""
        mse = np.mean((img1.astype(np.float64) - img2.astype(np.float64)) ** 2)
        if mse == 0:
            return 100.0
        return float(20 * np.log10(max_val / np.sqrt(mse)))
    
    @staticmethod
    def _compute_ssim(img1, img2) -> float:
        """Compute SSIM between two images."""
        from scipy.ndimage import gaussian_filter
        
        if img1.dtype != np.float64:
            img1 = img1.astype(np.float64)
        if img2.dtype != np.float64:
            img2 = img2.astype(np.float64)
        
        C1 = (0.01 * 255) ** 2
        C2 = (0.03 * 255) ** 2
        
        mean1 = gaussian_filter(img1, sigma=1.5)
        mean2 = gaussian_filter(img2, sigma=1.5)
        
        sq1 = gaussian_filter(img1 ** 2, sigma=1.5)
        sq2 = gaussian_filter(img2 ** 2, sigma=1.5)
        cross = gaussian_filter(img1 * img2, sigma=1.5)
        
        var1 = sq1 - mean1 ** 2
        var2 = sq2 - mean2 ** 2
        cov = cross - mean1 * mean2
        
        numerator = (2 * mean1 * mean2 + C1) * (2 * cov + C2)
        denominator = (mean1 ** 2 + mean2 ** 2 + C1) * (var1 + var2 + C2)
        
        ssim = numerator / denominator
        return float(np.mean(ssim))
    
    def save_results(self, results: List[Dict], filename: str = 'benchmark_results.json'):
        """Save benchmark results to JSON."""
        filepath = self.output_dir / filename
        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2)
        logger.info(f"Results saved to {filepath}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Benchmarker module ready")
