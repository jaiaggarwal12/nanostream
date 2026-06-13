"""
NanoStream - Adaptive Video Delivery Platform

A production-grade video compression system with content-aware encoding
optimization, multi-resolution bitrate ladder generation, and comprehensive
codec benchmarking (H.264, H.265, AV1).

Quick start:
    python cli.py full video.mp4
"""

__version__ = "1.0.0"
__author__ = "Your Name"

from analyzer import ContentAnalyzer
from encoder import Encoder
from bitrate_ladder import BitrateLadder
from benchmarker import Benchmarker
from dashboard import Dashboard

__all__ = [
    'ContentAnalyzer',
    'Encoder',
    'BitrateLadder',
    'Benchmarker',
    'Dashboard',
]
