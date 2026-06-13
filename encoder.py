"""
NanoStream Encoder
Content-aware encoding with optimized settings per video type
"""

import subprocess
import os
from pathlib import Path
from typing import Dict, Tuple
import logging
import time

logger = logging.getLogger(__name__)


# Encoding profiles per content type
ENCODING_PROFILES = {
    'animation': {
        'description': 'Animation-optimized (lower bitrate, sharp edges)',
        'h265_crf': 24,  # Higher quality (lower number)
        'h264_crf': 22,
        'av1_crf': 30,
        'preset': 'slow',
    },
    'sports': {
        'description': 'Sports-optimized (preserve motion clarity)',
        'h265_crf': 20,  # High quality for fast motion
        'h264_crf': 18,
        'av1_crf': 26,
        'preset': 'medium',
    },
    'lecture': {
        'description': 'Lecture-optimized (preserve text/details)',
        'h265_crf': 22,  # High quality for text
        'h264_crf': 20,
        'av1_crf': 28,
        'preset': 'slow',
    },
    'movie': {
        'description': 'Movie-optimized (balanced quality/bitrate)',
        'h265_crf': 23,
        'h264_crf': 21,
        'av1_crf': 29,
        'preset': 'medium',
    },
    'mixed': {
        'description': 'Mixed content (default balanced)',
        'h265_crf': 23,
        'h264_crf': 21,
        'av1_crf': 29,
        'preset': 'medium',
    }
}


class Encoder:
    """Encode video with content-aware optimization."""
    
    def __init__(self, content_type: str = 'mixed'):
        """Initialize encoder.
        
        Args:
            content_type: Type of content ('animation', 'sports', 'lecture', 'movie', 'mixed')
        """
        self.content_type = content_type
        self.profile = ENCODING_PROFILES.get(content_type, ENCODING_PROFILES['mixed'])
    
    def encode_h265(
        self,
        input_path: str,
        output_path: str,
        resolution: Tuple[int, int] = None,
    ) -> Dict:
        """Encode video with H.265.
        
        Args:
            input_path: Input video path
            output_path: Output video path
            resolution: Target resolution (width, height)
            
        Returns:
            Encoding stats
        """
        logger.info(f"Encoding with H.265 (CRF {self.profile['h265_crf']})...")
        
        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-c:v', 'libx265',
            '-crf', str(self.profile['h265_crf']),
            '-preset', self.profile['preset'],
            '-c:a', 'aac',
            '-b:a', '128k',
        ]
        
        if resolution:
            cmd.extend(['-vf', f'scale={resolution[0]}:{resolution[1]}'])
        
        cmd.extend(['-y', output_path])
        
        start_time = time.time()
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg error: {result.stderr}")
        except FileNotFoundError:
            raise RuntimeError("ffmpeg not found. Install with: winget install ffmpeg")
        
        encode_time = time.time() - start_time
        file_size = os.path.getsize(output_path)
        
        return {
            'codec': 'H.265/HEVC',
            'file_size_mb': file_size / (1024 ** 2),
            'encode_time_seconds': encode_time,
            'crf': self.profile['h265_crf'],
        }
    
    def encode_av1(
        self,
        input_path: str,
        output_path: str,
        resolution: Tuple[int, int] = None,
    ) -> Dict:
        """Encode video with AV1 (if available).
        
        Args:
            input_path: Input video path
            output_path: Output video path
            resolution: Target resolution (width, height)
            
        Returns:
            Encoding stats or None if AV1 not available
        """
        logger.info(f"Encoding with AV1 (CRF {self.profile['av1_crf']})...")
        
        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-c:v', 'libaom-av1',
            '-crf', str(self.profile['av1_crf']),
            '-preset', '4',  # AV1 preset (0-8, 4 is balanced)
            '-c:a', 'aac',
            '-b:a', '128k',
        ]
        
        if resolution:
            cmd.extend(['-vf', f'scale={resolution[0]}:{resolution[1]}'])
        
        cmd.extend(['-y', output_path])
        
        try:
            start_time = time.time()
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if result.returncode != 0:
                logger.warning(f"AV1 encoding failed: {result.stderr}")
                return None
            
            encode_time = time.time() - start_time
            file_size = os.path.getsize(output_path)
            
            return {
                'codec': 'AV1',
                'file_size_mb': file_size / (1024 ** 2),
                'encode_time_seconds': encode_time,
                'crf': self.profile['av1_crf'],
            }
        except FileNotFoundError:
            logger.warning("AV1 encoder not available")
            return None
    
    def encode_h264(
        self,
        input_path: str,
        output_path: str,
        resolution: Tuple[int, int] = None,
    ) -> Dict:
        """Encode video with H.264 (baseline for comparison).
        
        Args:
            input_path: Input video path
            output_path: Output video path
            resolution: Target resolution (width, height)
            
        Returns:
            Encoding stats
        """
        logger.info(f"Encoding with H.264 (CRF {self.profile['h264_crf']})...")
        
        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-c:v', 'libx264',
            '-crf', str(self.profile['h264_crf']),
            '-preset', self.profile['preset'],
            '-c:a', 'aac',
            '-b:a', '128k',
        ]
        
        if resolution:
            cmd.extend(['-vf', f'scale={resolution[0]}:{resolution[1]}'])
        
        cmd.extend(['-y', output_path])
        
        start_time = time.time()
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg error: {result.stderr}")
        except FileNotFoundError:
            raise RuntimeError("ffmpeg not found")
        
        encode_time = time.time() - start_time
        file_size = os.path.getsize(output_path)
        
        return {
            'codec': 'H.264/AVC',
            'file_size_mb': file_size / (1024 ** 2),
            'encode_time_seconds': encode_time,
            'crf': self.profile['h264_crf'],
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Encoder module ready")
