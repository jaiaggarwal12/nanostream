"""
NanoStream Live Dashboard
Real-time monitoring of encoding jobs and system performance
"""

from typing import List, Dict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class LiveDashboard:
    """Display real-time system metrics and job status."""
    
    @staticmethod
    def print_job_queue_status(queue_stats: Dict):
        """Print job queue status.
        
        Args:
            queue_stats: Stats from JobQueue.get_queue_stats()
        """
        print("\n" + "="*70)
        print("ENCODING QUEUE STATUS")
        print("="*70)
        print(f"Total Jobs: {queue_stats['total_jobs']}")
        print(f"  ⏳ Queued:    {queue_stats['queued']}")
        print(f"  ⚙️  Processing: {queue_stats['processing']}")
        print(f"  ✓ Completed:  {queue_stats['completed']}")
        print(f"  ✗ Failed:     {queue_stats['failed']}")
    
    @staticmethod
    def print_job_details(job: Dict):
        """Print details of a single job.
        
        Args:
            job: Job dict from JobQueue
        """
        status_icons = {
            'queued': '⏳',
            'processing': '⚙️ ',
            'completed': '✓',
            'failed': '✗',
        }
        
        icon = status_icons.get(job['status'], '?')
        
        print(f"\n{icon} Job {job['job_id']}")
        print(f"  Status: {job['status'].upper()}")
        print(f"  Video: {job['video_path']}")
        print(f"  Codec: {job['codec'].upper()}")
        print(f"  Progress: {job['progress']}%")
        print(f"  Created: {job['created_at']}")
        
        if job['status'] == 'processing' and job['started_at']:
            print(f"  Started: {job['started_at']}")
        
        if job['status'] in ['completed', 'failed'] and job['completed_at']:
            print(f"  Completed: {job['completed_at']}")
        
        if job['error_message']:
            print(f"  Error: {job['error_message']}")
    
    @staticmethod
    def print_system_metrics(metrics: Dict):
        """Print system metrics.
        
        Args:
            metrics: Dict with system metrics
        """
        print("\n" + "="*70)
        print("SYSTEM METRICS")
        print("="*70)
        print(f"Videos Processed: {metrics.get('videos_processed', 0):,}")
        print(f"Storage Saved: {metrics.get('storage_saved_tb', 0):.1f} TB")
        print(f"Bandwidth Saved: {metrics.get('bandwidth_saved_percent', 0):.1f}%")
        print(f"Average Quality: SSIM {metrics.get('average_ssim', 0):.4f}")
        print(f"Average Compression: {metrics.get('average_compression_ratio', 0):.2f}x")
        print(f"Average Encode Time: {metrics.get('average_encode_minutes', 0):.1f} min")
        print(f"Cost Saved YTD: ${metrics.get('cost_saved_usd', 0):,.2f}")
    
    @staticmethod
    def print_abr_simulation(simulation_results: List[Dict]):
        """Print ABR simulation results.
        
        Args:
            simulation_results: Results from BandwidthSimulator
        """
        print("\n" + "="*70)
        print("ADAPTIVE BITRATE SIMULATION")
        print("="*70)
        print(f"\n{'Scenario':<20} {'Bandwidth':<12} {'Low Buffer':<15} {'Normal Buffer':<15} {'High Buffer':<15}")
        print("-"*77)
        
        for result in simulation_results:
            scenario = result['scenario']
            bandwidth = f"{result['bandwidth_mbps']:.1f} Mbps"
            
            selections = result['quality_selections']
            low_buf = selections[0]['selected_quality']
            norm_buf = selections[1]['selected_quality']
            high_buf = selections[2]['selected_quality']
            
            print(f"{scenario:<20} {bandwidth:<12} {low_buf:<15} {norm_buf:<15} {high_buf:<15}")
    
    @staticmethod
    def print_cost_comparison(codec_costs: List[Dict]):
        """Print codec cost comparison.
        
        Args:
            codec_costs: Results from CostOptimizer.compare_codec_costs()
        """
        print("\n" + "="*70)
        print("CODEC COST ANALYSIS")
        print("="*70)
        print(f"\n{'Codec':<10} {'Storage':<12} {'Bandwidth':<12} {'Encoding':<12} {'Total Annual':<15} {'Savings':<12}")
        print("-"*73)
        
        for cost in codec_costs:
            codec = cost['codec'].upper()
            storage = f"${cost['storage_annual']:.2f}"
            bandwidth = f"${cost['bandwidth_annual']:.2f}"
            encoding = f"${cost['encoding_cost']:.2f}"
            total = f"${cost['annual_total']:.2f}"
            savings = f"{cost['savings_vs_h264_percent']:.1f}%"
            
            print(f"{codec:<10} {storage:<12} {bandwidth:<12} {encoding:<12} {total:<15} {savings:<12}")
    
    @staticmethod
    def print_ml_recommendation(recommendation: Dict):
        """Print ML encoder recommendation.
        
        Args:
            recommendation: From MLEncoderSelector.get_recommendation()
        """
        print("\n" + "="*70)
        print("ML ENCODER RECOMMENDATION")
        print("="*70)
        print(f"Recommended Codec: {recommendation['recommended_codec'].upper()}")
        print(f"Confidence: {recommendation['confidence']:.1%}")
        print(f"Predicted Compression: {recommendation['predicted_compression_ratio']:.2f}x")
        print(f"\nCRF Settings:")
        print(f"  High Quality: {recommendation['crf_settings']['high_quality']}")
        print(f"  Balanced: {recommendation['crf_settings']['balanced']}")
        print(f"  Low Bitrate: {recommendation['crf_settings']['low_bitrate']}")
        print(f"\nRationale: {recommendation['rationale']}")
    
    @staticmethod
    def print_performance_summary(summary: Dict):
        """Print performance summary.
        
        Args:
            summary: Summary dict with performance metrics
        """
        print("\n" + "="*70)
        print("PERFORMANCE SUMMARY")
        print("="*70)
        print(f"Encoding Performance:")
        print(f"  H.264:   {summary.get('h264_speed', 0):.1f}x realtime")
        print(f"  H.265:   {summary.get('h265_speed', 0):.1f}x realtime")
        print(f"  AV1:     {summary.get('av1_speed', 0):.1f}x realtime")
        print(f"\nQuality Metrics:")
        print(f"  H.264 PSNR: {summary.get('h264_psnr', 0):.2f} dB")
        print(f"  H.265 PSNR: {summary.get('h265_psnr', 0):.2f} dB")
        print(f"  AV1 PSNR:   {summary.get('av1_psnr', 0):.2f} dB")
        print(f"\nCompression Ratios:")
        print(f"  H.264:   {summary.get('h264_ratio', 0):.2f}x")
        print(f"  H.265:   {summary.get('h265_ratio', 0):.2f}x")
        print(f"  AV1:     {summary.get('av1_ratio', 0):.2f}x")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Live Dashboard ready")
