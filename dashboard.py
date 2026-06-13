"""
NanoStream Dashboard
Display and visualize compression results
"""

from typing import List, Dict
import logging

logger = logging.getLogger(__name__)


class Dashboard:
    """Display compression and benchmark results."""
    
    @staticmethod
    def print_analysis(analysis_result: Dict):
        """Print content analysis results.
        
        Args:
            analysis_result: Result from ContentAnalyzer.analyze()
        """
        print("\n" + "="*70)
        print("CONTENT ANALYSIS")
        print("="*70)
        print(f"Video: {analysis_result['video_path']}")
        print(f"Resolution: {analysis_result['width']}x{analysis_result['height']}")
        print(f"FPS: {analysis_result['fps']}")
        print(f"Duration: {analysis_result['duration_seconds']:.1f} seconds")
        print(f"Total Frames: {analysis_result['total_frames']:,}")
        print(f"\nContent Type: {analysis_result['content_type'].upper()}")
        
        metrics = analysis_result['metrics']
        print(f"\nContent Metrics:")
        print(f"  Motion Score: {metrics['motion']:.3f}")
        print(f"  Color Variance: {metrics['color_variance']:.3f}")
        print(f"  Edge Density: {metrics['edge_density']:.5f}")
        print(f"  Scene Cut Rate: {metrics['scene_cut_rate']:.3f}")
    
    @staticmethod
    def print_bitrate_ladder(ladder: List[Dict]):
        """Print bitrate ladder.
        
        Args:
            ladder: List of resolution configs from BitrateLadder
        """
        print("\n" + "="*70)
        print("BITRATE LADDER (Multi-Resolution Encoding)")
        print("="*70)
        print(f"{'Resolution':<12} {'Size':<12} {'H.264':<12} {'H.265':<12} {'AV1':<12}")
        print("-"*70)
        
        for entry in ladder:
            res_name = entry['name']
            size = f"{entry['width']}x{entry['height']}"
            h264 = f"{entry['bitrate_h264_mbps']:.1f} Mbps"
            h265 = f"{entry['bitrate_h265_mbps']:.1f} Mbps"
            av1 = f"{entry['bitrate_av1_mbps']:.1f} Mbps"
            
            print(f"{res_name:<12} {size:<12} {h264:<12} {h265:<12} {av1:<12}")
    
    @staticmethod
    def print_encoding_results(encoding_stats: Dict):
        """Print encoding results.
        
        Args:
            encoding_stats: Result from encoder.encode_*()
        """
        print(f"\n{encoding_stats['codec']}:")
        print(f"  File Size: {encoding_stats['file_size_mb']:.2f} MB")
        print(f"  Encode Time: {encoding_stats['encode_time_seconds']:.1f}s")
    
    @staticmethod
    def print_benchmark_results(results: List[Dict], original_size_mb: float):
        """Print benchmark comparison.
        
        Args:
            results: List of benchmark results
            original_size_mb: Original file size in MB
        """
        print("\n" + "="*100)
        print("CODEC BENCHMARK COMPARISON")
        print("="*100)
        
        print(f"\nOriginal Video: {original_size_mb:.2f} MB\n")
        
        # Print header
        print(f"{'Codec':<12} {'Size (MB)':<12} {'Ratio':<10} {'Reduction':<12} {'PSNR (dB)':<14} {'SSIM':<10}")
        print("-"*100)
        
        # Sort by compression ratio (best first)
        sorted_results = sorted(results, key=lambda x: x['compression_ratio'], reverse=True)
        
        for result in sorted_results:
            if result is None:
                continue
                
            codec = result['codec']
            size = result['compressed_size_mb']
            ratio = result['compression_ratio']
            reduction = result['bitrate_reduction_percent']
            psnr = result['psnr_mean_db']
            ssim = result['ssim_mean']
            
            print(f"{codec:<12} {size:<12.2f} {ratio:<10.2f}x {reduction:<12.1f}% {psnr:<14.2f} {ssim:<10.4f}")
        
        print("="*100)
        
        # Find best performer
        if sorted_results and sorted_results[0]:
            best = sorted_results[0]
            print(f"\n✓ Best Compression: {best['codec']} ({best['compression_ratio']:.2f}x)")
            print(f"  File Size: {best['compressed_size_mb']:.2f} MB (saved {best['bitrate_reduction_percent']:.1f}%)")
            print(f"  Quality: PSNR {best['psnr_mean_db']:.2f} dB, SSIM {best['ssim_mean']:.4f}")
    
    @staticmethod
    def print_summary(
        content_type: str,
        original_size_mb: float,
        best_result: Dict,
        encode_times: Dict,
    ):
        """Print executive summary.
        
        Args:
            content_type: Type of content detected
            original_size_mb: Original file size
            best_result: Best codec result
            encode_times: Encoding times per codec
        """
        print("\n" + "="*70)
        print("SUMMARY")
        print("="*70)
        print(f"Content Type: {content_type.upper()}")
        print(f"Original Size: {original_size_mb:.2f} MB")
        print(f"\nBest Codec: {best_result['codec']}")
        print(f"  Compressed: {best_result['compressed_size_mb']:.2f} MB")
        print(f"  Compression Ratio: {best_result['compression_ratio']:.2f}x")
        print(f"  Storage Saved: {best_result['bitrate_reduction_percent']:.1f}%")
        print(f"  Quality: PSNR {best_result['psnr_mean_db']:.2f} dB")
        
        if best_result['codec'] in encode_times:
            print(f"  Encoding Time: {encode_times[best_result['codec']]:.1f}s")
        
        print("\n" + "="*70)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Dashboard module ready")
