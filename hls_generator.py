"""
NanoStream HLS Generator
Create multi-resolution HLS streaming packages
"""

import subprocess
import os
from pathlib import Path
from typing import List, Dict, Tuple
import logging
import math

logger = logging.getLogger(__name__)


class HLSGenerator:
    """Generate HLS streaming packages from videos."""
    
    def __init__(self, output_dir: str = './hls_output'):
        """Initialize HLS generator.
        
        Args:
            output_dir: Directory to save HLS files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_hls_package(
        self,
        video_path: str,
        resolutions: List[Dict],
        segment_duration: int = 10,
        content_type: str = 'movie',
    ) -> Dict:
        """Generate complete HLS package.
        
        Args:
            video_path: Input video path
            resolutions: List of resolution configs
            segment_duration: Segment duration in seconds
            content_type: Type of content
            
        Returns:
            HLS package info
        """
        logger.info(f"Generating HLS package for {video_path}")
        
        # Create resolution-specific directories
        variant_playlists = []
        
        for resolution in resolutions:
            variant_info = self._encode_variant(
                video_path,
                resolution,
                segment_duration,
                content_type,
            )
            if variant_info:
                variant_playlists.append(variant_info)
        
        if not variant_playlists:
            logger.error("Failed to encode any variants")
            return None
        
        # Generate master playlist
        master_playlist = self._generate_master_playlist(variant_playlists)
        
        master_path = self.output_dir / 'master.m3u8'
        with open(master_path, 'w') as f:
            f.write(master_playlist)
        
        logger.info(f"Master playlist generated: {master_path}")
        
        return {
            'master_playlist': str(master_path),
            'variants': variant_playlists,
            'output_dir': str(self.output_dir),
        }
    
    def _encode_variant(
        self,
        video_path: str,
        resolution: Dict,
        segment_duration: int,
        content_type: str,
    ) -> Dict:
        """Encode single resolution variant.
        
        Args:
            video_path: Input video
            resolution: Resolution config
            segment_duration: Segment duration
            content_type: Content type
            
        Returns:
            Variant info
        """
        variant_name = resolution['name']
        width = resolution['width']
        height = resolution['height']
        
        variant_dir = self.output_dir / variant_name
        variant_dir.mkdir(parents=True, exist_ok=True)
        
        # Determine CRF based on content type
        crf_map = {
            'animation': 24,
            'sports': 20,
            'lecture': 22,
            'movie': 23,
            'mixed': 23,
        }
        crf = crf_map.get(content_type, 23)
        
        logger.info(f"Encoding {variant_name} ({width}x{height}, CRF {crf})...")
        
        # Encode with segmentation
        playlist_path = variant_dir / 'playlist.m3u8'
        segment_pattern = variant_dir / f'{variant_name}_%05d.ts'
        
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-c:v', 'libx265',
            '-crf', str(crf),
            '-preset', 'medium',
            '-vf', f'scale={width}:{height}',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-f', 'hls',
            '-hls_time', str(segment_duration),
            '-hls_playlist_type', 'vod',
            '-hls_segment_filename', str(segment_pattern),
            str(playlist_path),
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if result.returncode != 0:
                logger.error(f"Encoding failed: {result.stderr}")
                return None
        except FileNotFoundError:
            logger.error("ffmpeg not found")
            return None
        
        # Calculate bitrate
        total_size = sum(
            os.path.getsize(f) for f in variant_dir.glob('*.ts')
        )
        
        # Get duration
        duration = self._get_video_duration(video_path)
        bitrate_mbps = (total_size * 8) / (1024 ** 2) / duration if duration > 0 else 0
        
        logger.info(f"  {variant_name}: {bitrate_mbps:.2f} Mbps")
        
        return {
            'name': variant_name,
            'width': width,
            'height': height,
            'bitrate_mbps': bitrate_mbps,
            'playlist': str(playlist_path),
            'directory': str(variant_dir),
        }
    
    def _generate_master_playlist(self, variants: List[Dict]) -> str:
        """Generate HLS master playlist.
        
        Args:
            variants: List of variant info dicts
            
        Returns:
            Master playlist content
        """
        # Sort by bitrate (ascending)
        variants_sorted = sorted(variants, key=lambda x: x['bitrate_mbps'])
        
        playlist = '#EXTM3U\n'
        playlist += '#EXT-X-VERSION:3\n'
        playlist += '#EXT-X-TARGETDURATION:10\n\n'
        
        for variant in variants_sorted:
            bitrate_kbps = int(variant['bitrate_mbps'] * 1000)
            playlist += f'#EXT-X-STREAM-INF:BANDWIDTH={bitrate_kbps},RESOLUTION={variant["width"]}x{variant["height"]}\n'
            playlist += f'{variant["name"]}/playlist.m3u8\n'
        
        return playlist
    
    @staticmethod
    def _get_video_duration(video_path: str) -> float:
        """Get video duration in seconds."""
        import subprocess
        try:
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1:noprint_wrappers=1',
                video_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return float(result.stdout.strip())
        except:
            return 0.0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("HLS Generator ready")
