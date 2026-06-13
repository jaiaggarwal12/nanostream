"""
NanoStream Bitrate Ladder
Generate Netflix-style multi-resolution encoding ladder
"""

from typing import List, Dict, Tuple
import logging

logger = logging.getLogger(__name__)


class BitrateLadder:
    """Generate and manage multi-resolution encoding ladder."""
    
    # Standard resolutions and recommended bitrates
    STANDARD_LADDER = [
        {'name': '4K', 'width': 3840, 'height': 2160, 'bitrate_h265': 12},
        {'name': '1440p', 'width': 2560, 'height': 1440, 'bitrate_h265': 8},
        {'name': '1080p', 'width': 1920, 'height': 1080, 'bitrate_h265': 5},
        {'name': '720p', 'width': 1280, 'height': 720, 'bitrate_h265': 3},
        {'name': '480p', 'width': 854, 'height': 480, 'bitrate_h265': 1.5},
        {'name': '360p', 'width': 640, 'height': 360, 'bitrate_h265': 0.8},
    ]
    
    def __init__(self, video_width: int, video_height: int):
        """Initialize ladder.
        
        Args:
            video_width: Input video width
            video_height: Input video height
        """
        self.video_width = video_width
        self.video_height = video_height
        self.aspect_ratio = video_width / video_height
    
    def generate(self, max_resolution: str = '1080p') -> List[Dict]:
        """Generate appropriate bitrate ladder.
        
        Args:
            max_resolution: Maximum resolution to include ('360p', '480p', '720p', '1080p', '1440p', '4K')
            
        Returns:
            List of resolution configs
        """
        max_heights = {
            '360p': 360,
            '480p': 480,
            '720p': 720,
            '1080p': 1080,
            '1440p': 1440,
            '4K': 2160,
        }
        
        max_height = max_heights.get(max_resolution, 1080)
        
        ladder = []
        
        for entry in self.STANDARD_LADDER:
            # Skip resolutions higher than input or max
            if entry['height'] > self.video_height or entry['height'] > max_height:
                continue
            
            # Adjust width to maintain aspect ratio
            width = int(entry['height'] * self.aspect_ratio)
            # Round to nearest multiple of 2 (required for video codecs)
            width = (width // 2) * 2
            
            ladder.append({
                'name': entry['name'],
                'width': width,
                'height': entry['height'],
                'bitrate_h265_mbps': entry['bitrate_h265'],
                'bitrate_h264_mbps': entry['bitrate_h265'] * 1.2,  # H.264 ~20% worse
                'bitrate_av1_mbps': entry['bitrate_h265'] * 0.7,   # AV1 ~30% better
            })
        
        logger.info(f"Generated ladder with {len(ladder)} resolutions")
        for entry in ladder:
            logger.info(f"  {entry['name']}: {entry['width']}x{entry['height']}, "
                       f"{entry['bitrate_h265_mbps']} Mbps (H.265)")
        
        return ladder
    
    @staticmethod
    def estimate_bitrate(
        resolution_name: str,
        codec: str = 'h265',
        content_type: str = 'movie',
    ) -> float:
        """Estimate bitrate for a resolution.
        
        Args:
            resolution_name: Resolution name ('360p', '480p', etc.)
            codec: Codec type ('h264', 'h265', 'av1')
            content_type: Type of content
            
        Returns:
            Estimated bitrate in Mbps
        """
        # Base bitrates (H.265)
        base_rates = {
            '360p': 0.8,
            '480p': 1.5,
            '720p': 3,
            '1080p': 5,
            '1440p': 8,
            '4K': 12,
        }
        
        # Codec multipliers
        codec_multipliers = {
            'h264': 1.2,
            'h265': 1.0,
            'av1': 0.7,
        }
        
        # Content multipliers
        content_multipliers = {
            'animation': 0.8,    # Easier to compress
            'lecture': 0.9,      # Also easier
            'movie': 1.0,        # Baseline
            'sports': 1.3,       # Harder to compress
            'mixed': 1.0,
        }
        
        base = base_rates.get(resolution_name, 5)
        codec_mult = codec_multipliers.get(codec, 1.0)
        content_mult = content_multipliers.get(content_type, 1.0)
        
        return base * codec_mult * content_mult


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test
    ladder = BitrateLadder(video_width=1920, video_height=1080)
    steps = ladder.generate(max_resolution='1080p')
    
    print(f"\nGenerated {len(steps)} resolution steps:")
    for step in steps:
        print(f"  {step['name']}: {step['width']}x{step['height']}")
