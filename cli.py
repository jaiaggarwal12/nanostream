#!/usr/bin/env python3
"""
NanoStream - Adaptive Video Delivery Platform
Analyze, optimize, and benchmark video compression
"""

import argparse
import sys
import logging
from pathlib import Path
from typing import Optional

from analyzer import ContentAnalyzer
from encoder import Encoder
from bitrate_ladder import BitrateLadder
from benchmarker import Benchmarker
from dashboard import Dashboard

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class NanoStream:
    """Main NanoStream application."""
    
    def __init__(self):
        self.analyzer = ContentAnalyzer(sample_frames=10)
        self.benchmarker = Benchmarker(output_dir='./nanostream_results')
        self.dashboard = Dashboard()
    
    def upload_and_analyze(self, video_path: str) -> dict:
        """Upload and analyze video.
        
        Args:
            video_path: Path to video file
            
        Returns:
            Analysis result
        """
        logger.info(f"Analyzing video: {video_path}")
        
        if not Path(video_path).exists():
            logger.error(f"Video not found: {video_path}")
            return None
        
        try:
            analysis = self.analyzer.analyze(video_path)
            self.dashboard.print_analysis(analysis)
            return analysis
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return None
    
    def generate_ladder(self, analysis: dict, max_resolution: str = '1080p') -> list:
        """Generate bitrate ladder.
        
        Args:
            analysis: Analysis result
            max_resolution: Maximum resolution to include
            
        Returns:
            List of resolution configs
        """
        logger.info("Generating bitrate ladder...")
        
        ladder_gen = BitrateLadder(
            video_width=analysis['width'],
            video_height=analysis['height']
        )
        
        ladder = ladder_gen.generate(max_resolution=max_resolution)
        self.dashboard.print_bitrate_ladder(ladder)
        
        return ladder
    
    def benchmark_codecs(
        self,
        video_path: str,
        analysis: dict,
        resolution: tuple = None,
        codecs: list = None,
    ) -> dict:
        """Benchmark different codecs.
        
        Args:
            video_path: Path to video file
            analysis: Analysis result
            resolution: Target resolution (width, height)
            codecs: List of codecs to test ('h264', 'h265', 'av1')
            
        Returns:
            Benchmark results
        """
        if codecs is None:
            codecs = ['h265', 'h264', 'av1']
        
        logger.info(f"Benchmarking codecs: {', '.join(codecs)}")
        
        encoder = Encoder(content_type=analysis['content_type'])
        results = []
        encode_times = {}
        
        output_dir = Path('./nanostream_results')
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for codec in codecs:
            logger.info(f"\nTesting {codec.upper()}...")
            
            output_path = output_dir / f"encoded_{codec}.mp4"
            
            try:
                if codec == 'h265':
                    stats = encoder.encode_h265(
                        video_path,
                        str(output_path),
                        resolution=resolution
                    )
                elif codec == 'h264':
                    stats = encoder.encode_h264(
                        video_path,
                        str(output_path),
                        resolution=resolution
                    )
                elif codec == 'av1':
                    stats = encoder.encode_av1(
                        video_path,
                        str(output_path),
                        resolution=resolution
                    )
                    if stats is None:
                        logger.warning(f"Skipping {codec} - not available")
                        continue
                else:
                    continue
                
                self.dashboard.print_encoding_results(stats)
                encode_times[stats['codec']] = stats['encode_time_seconds']
                
                # Compute metrics
                metrics = self.benchmarker.compute_metrics(
                    video_path,
                    str(output_path),
                    codec.upper()
                )
                
                if metrics:
                    results.append(metrics)
                    logger.info(f"  Compression Ratio: {metrics['compression_ratio']:.2f}x")
                    logger.info(f"  PSNR: {metrics['psnr_mean_db']:.2f} dB")
            
            except Exception as e:
                logger.error(f"Failed to benchmark {codec}: {e}")
        
        return {
            'results': results,
            'encode_times': encode_times,
        }
    
    def run_full_pipeline(
        self,
        video_path: str,
        max_resolution: str = '1080p',
    ):
        """Run complete analysis and benchmark pipeline.
        
        Args:
            video_path: Path to video file
            max_resolution: Maximum resolution for ladder
        """
        print("\n" + "="*70)
        print("NanoStream - Adaptive Video Delivery Platform")
        print("="*70)
        
        # Step 1: Analyze
        analysis = self.upload_and_analyze(video_path)
        if not analysis:
            return False
        
        # Step 2: Generate ladder
        ladder = self.generate_ladder(analysis, max_resolution=max_resolution)
        
        # Step 3: Benchmark on original resolution
        print("\n" + "="*70)
        print("CODEC BENCHMARKING")
        print("="*70)
        
        benchmark = self.benchmark_codecs(
            video_path,
            analysis,
            resolution=None,  # Use original resolution
            codecs=['h265', 'h264', 'av1']
        )
        
        # Step 4: Display results
        if benchmark['results']:
            self.dashboard.print_benchmark_results(
                benchmark['results'],
                analysis['width'] * analysis['height'] * analysis['total_frames'] / (1024 ** 2)  # Rough estimate
            )
            
            best = sorted(benchmark['results'], key=lambda x: x['compression_ratio'], reverse=True)[0]
            
            self.dashboard.print_summary(
                analysis['content_type'],
                benchmark['results'][0]['original_size_mb'],
                best,
                benchmark['encode_times']
            )
        
        logger.info("\n✓ Pipeline complete!")
        return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='NanoStream - Adaptive Video Delivery Platform',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s analyze video.mp4
  %(prog)s benchmark video.mp4 --codecs h265 h264 av1
  %(prog)s full video.mp4 --max-resolution 1080p
        '''
    )
    
    parser.add_argument('command', choices=['analyze', 'benchmark', 'full'],
                       help='Command to run')
    parser.add_argument('video', help='Path to video file')
    parser.add_argument('--max-resolution', default='1080p',
                       choices=['360p', '480p', '720p', '1080p', '1440p', '4K'],
                       help='Maximum resolution (default: 1080p)')
    parser.add_argument('--codecs', nargs='+', default=['h265', 'h264', 'av1'],
                       help='Codecs to benchmark (default: h265 h264 av1)')
    
    args = parser.parse_args()
    
    app = NanoStream()
    
    if args.command == 'analyze':
        app.upload_and_analyze(args.video)
    
    elif args.command == 'benchmark':
        analysis = app.upload_and_analyze(args.video)
        if analysis:
            benchmark = app.benchmark_codecs(
                args.video,
                analysis,
                codecs=args.codecs
            )
            if benchmark['results']:
                app.dashboard.print_benchmark_results(
                    benchmark['results'],
                    benchmark['results'][0]['original_size_mb']
                )
    
    elif args.command == 'full':
        app.run_full_pipeline(args.video, max_resolution=args.max_resolution)


if __name__ == '__main__':
    main()
