"""
NanoStream Adaptive Bitrate Engine
Simulate network conditions and choose optimal quality
"""

from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class AdaptiveBitrateEngine:
    """Implement ABR logic for adaptive streaming."""
    
    def __init__(self, variants: List[Dict]):
        """Initialize ABR engine.
        
        Args:
            variants: List of available variants with bitrate info
        """
        self.variants = sorted(variants, key=lambda x: x['bitrate_mbps'])
        self.current_bandwidth_mbps = 5.0  # Start at 5 Mbps
        self.buffer_size = 30  # seconds
        self.quality_switches = 0
    
    def simulate_bandwidth(self, bandwidth_mbps: float):
        """Simulate changing network bandwidth.
        
        Args:
            bandwidth_mbps: Simulated bandwidth in Mbps
        """
        self.current_bandwidth_mbps = bandwidth_mbps
        logger.info(f"Bandwidth: {bandwidth_mbps:.2f} Mbps")
    
    def select_quality(self, buffer_seconds: float) -> Optional[Dict]:
        """Select optimal quality based on bandwidth and buffer.
        
        This implements a simple but effective ABR algorithm:
        - If buffer is low, switch down to prevent stalls
        - If bandwidth is high and buffer is high, switch up
        - Otherwise stay with current quality
        
        Args:
            buffer_seconds: Current buffer level in seconds
            
        Returns:
            Selected variant or None
        """
        # Estimate available bandwidth (conservative: 80% of measured)
        available_bandwidth = self.current_bandwidth_mbps * 0.8
        
        # Buffer thresholds
        low_buffer = 5      # seconds
        high_buffer = 20    # seconds
        
        # If buffer is critical, pick lowest bitrate
        if buffer_seconds < low_buffer:
            logger.info(f"Buffer low ({buffer_seconds:.1f}s), switching to minimum quality")
            return self.variants[0]
        
        # If buffer is high and bandwidth is high, try highest bitrate
        if buffer_seconds > high_buffer and available_bandwidth > self.variants[-1]['bitrate_mbps']:
            logger.info(f"Buffer high ({buffer_seconds:.1f}s), high bandwidth, switching to maximum quality")
            return self.variants[-1]
        
        # Find best variant that fits available bandwidth
        selected = None
        for variant in self.variants:
            if variant['bitrate_mbps'] <= available_bandwidth:
                selected = variant
        
        if selected is None:
            selected = self.variants[0]
        
        return selected
    
    def get_bitrate_ladder(self) -> List[Dict]:
        """Get available bitrate ladder.
        
        Returns:
            List of variants with bitrates
        """
        return [
            {
                'name': v['name'],
                'bitrate_mbps': v['bitrate_mbps'],
                'width': v['width'],
                'height': v['height'],
            }
            for v in self.variants
        ]


class BandwidthSimulator:
    """Simulate realistic network conditions."""
    
    @staticmethod
    def get_simulation_scenarios() -> List[Dict]:
        """Get predefined bandwidth scenarios.
        
        Returns:
            List of simulation scenarios
        """
        return [
            {
                'name': '4G (Good)',
                'bandwidth_mbps': 10,
                'description': 'Fast mobile network'
            },
            {
                'name': '4G (Average)',
                'bandwidth_mbps': 5,
                'description': 'Typical mobile network'
            },
            {
                'name': '4G (Poor)',
                'bandwidth_mbps': 2,
                'description': 'Weak signal'
            },
            {
                'name': 'WiFi (Good)',
                'bandwidth_mbps': 25,
                'description': 'Good WiFi'
            },
            {
                'name': 'WiFi (Average)',
                'bandwidth_mbps': 10,
                'description': 'Typical WiFi'
            },
            {
                'name': 'WiFi (Poor)',
                'bandwidth_mbps': 3,
                'description': 'Weak WiFi'
            },
            {
                'name': 'Broadband',
                'bandwidth_mbps': 50,
                'description': 'Fast broadband'
            },
        ]
    
    @staticmethod
    def simulate_quality_selection(
        abr_engine: AdaptiveBitrateEngine,
        scenarios: List[Dict],
    ) -> Dict:
        """Simulate quality selection across bandwidth scenarios.
        
        Args:
            abr_engine: ABR engine instance
            scenarios: Bandwidth scenarios to simulate
            
        Returns:
            Simulation results
        """
        results = []
        
        for scenario in scenarios:
            abr_engine.simulate_bandwidth(scenario['bandwidth_mbps'])
            
            # Simulate with different buffer levels
            buffer_levels = [5, 15, 30]
            selections = []
            
            for buffer in buffer_levels:
                selected = abr_engine.select_quality(buffer)
                selections.append({
                    'buffer_seconds': buffer,
                    'selected_quality': selected['name'] if selected else 'Unknown',
                    'selected_bitrate_mbps': selected['bitrate_mbps'] if selected else 0,
                })
            
            results.append({
                'scenario': scenario['name'],
                'bandwidth_mbps': scenario['bandwidth_mbps'],
                'description': scenario['description'],
                'quality_selections': selections,
                'quality_range': f"{selections[0]['selected_quality']} - {selections[-1]['selected_quality']}",
            })
        
        return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("ABR Engine ready")
