"""
NanoStream Content Analyzer
Detects video type and extracts features for encoding optimization
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Dict, Tuple
import logging

logger = logging.getLogger(__name__)


class ContentAnalyzer:
    """Analyze video content to determine optimal encoding strategy."""
    
    def __init__(self, sample_frames: int = 10):
        """Initialize analyzer.
        
        Args:
            sample_frames: Number of frames to sample for analysis
        """
        self.sample_frames = sample_frames
    
    def analyze(self, video_path: str) -> Dict:
        """Analyze video content.
        
        Args:
            video_path: Path to video file
            
        Returns:
            Dict with content type and metrics
        """
        logger.info(f"Analyzing video: {video_path}")
        
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video: {video_path}")
        
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        # Sample frames
        frame_indices = np.linspace(0, total_frames - 1, self.sample_frames, dtype=int)
        frames = []
        
        for idx in frame_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if ret:
                frames.append(frame)
        
        cap.release()
        
        if not frames:
            raise RuntimeError("Could not extract frames from video")
        
        # Extract features
        motion = self._compute_motion(frames)
        color_variance = self._compute_color_variance(frames)
        edge_density = self._compute_edge_density(frames)
        scene_cut_rate = self._compute_scene_cuts(frames)
        
        # Classify content
        content_type = self._classify_content(
            motion, color_variance, edge_density, scene_cut_rate
        )
        
        result = {
            'video_path': str(video_path),
            'width': width,
            'height': height,
            'fps': fps,
            'total_frames': total_frames,
            'duration_seconds': total_frames / fps,
            'content_type': content_type,
            'metrics': {
                'motion': motion,
                'color_variance': color_variance,
                'edge_density': edge_density,
                'scene_cut_rate': scene_cut_rate,
            }
        }
        
        logger.info(f"Content type: {content_type}")
        logger.info(f"Motion: {motion:.3f}, Colors: {color_variance:.3f}, Edges: {edge_density:.3f}")
        
        return result
    
    @staticmethod
    def _compute_motion(frames: list) -> float:
        """Compute average motion between frames."""
        if len(frames) < 2:
            return 0.0
        
        motion_values = []
        prev_gray = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY)
        
        for frame in frames[1:]:
            curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            flow = cv2.calcOpticalFlowFarneback(
                prev_gray, curr_gray, None, 0.5, 3, 15, 3, 5, 1.2, 0
            )
            magnitude = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
            motion_values.append(magnitude.mean())
            prev_gray = curr_gray
        
        return float(np.mean(motion_values))
    
    @staticmethod
    def _compute_color_variance(frames: list) -> float:
        """Compute color/saturation variance."""
        hsv_vars = []
        
        for frame in frames:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            s_channel = hsv[:, :, 1]
            hsv_vars.append(s_channel.std())
        
        return float(np.mean(hsv_vars))
    
    @staticmethod
    def _compute_edge_density(frames: list) -> float:
        """Compute edge density (detail level)."""
        edge_densities = []
        
        for frame in frames:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 100, 200)
            edge_density = edges.sum() / (edges.shape[0] * edges.shape[1])
            edge_densities.append(edge_density)
        
        return float(np.mean(edge_densities))
    
    @staticmethod
    def _compute_scene_cuts(frames: list) -> float:
        """Detect scene cuts (frame-to-frame differences)."""
        if len(frames) < 2:
            return 0.0
        
        differences = []
        prev_gray = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY)
        
        for frame in frames[1:]:
            curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            diff = cv2.absdiff(prev_gray, curr_gray)
            differences.append(diff.mean())
            prev_gray = curr_gray
        
        return float(np.mean(differences))
    
    @staticmethod
    def _classify_content(
        motion: float,
        color_variance: float,
        edge_density: float,
        scene_cut_rate: float,
    ) -> str:
        """Classify content based on extracted features.
        
        Returns:
            One of: 'animation', 'sports', 'movie', 'lecture', 'mixed'
        """
        # Animation: low motion, low color variance, clean edges
        if motion < 5 and edge_density < 0.03 and color_variance < 50:
            return 'animation'
        
        # Sports: high motion, scene cuts, varied colors
        if motion > 8 and scene_cut_rate > 15 and color_variance > 80:
            return 'sports'
        
        # Lecture: low motion, high edge density (text/slides)
        if motion < 3 and edge_density > 0.05:
            return 'lecture'
        
        # Movie: moderate motion, moderate details, balanced colors
        if motion > 3 and motion < 8 and edge_density > 0.02:
            return 'movie'
        
        return 'mixed'


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test
    analyzer = ContentAnalyzer(sample_frames=10)
    print("ContentAnalyzer initialized and ready to use")
