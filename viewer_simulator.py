"""
NanoStream Viewer Simulator
Simulate realistic viewer populations and streaming behavior.

Models:
    - Bandwidth distribution by region
    - Device type (mobile, desktop, TV)
    - Watch time / completion rate
    - Buffering events

Outputs:
    - Average startup delay
    - Rebuffer rate
    - Average bitrate served
    - Quality switch frequency
    - Monthly delivery cost
"""

import numpy as np
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


# ── Regional bandwidth distributions (Mbps) ──────────────────────────────────
REGIONAL_PROFILES = {
    'north_america': {
        'share': 0.30,
        'bandwidth_mean': 25,
        'bandwidth_std': 15,
        'bandwidth_min': 1,
        'bandwidth_max': 200,
    },
    'western_europe': {
        'share': 0.25,
        'bandwidth_mean': 20,
        'bandwidth_std': 12,
        'bandwidth_min': 1,
        'bandwidth_max': 150,
    },
    'asia_pacific': {
        'share': 0.30,
        'bandwidth_mean': 15,
        'bandwidth_std': 18,
        'bandwidth_min': 0.5,
        'bandwidth_max': 200,
    },
    'latin_america': {
        'share': 0.08,
        'bandwidth_mean': 8,
        'bandwidth_std': 6,
        'bandwidth_min': 0.5,
        'bandwidth_max': 50,
    },
    'africa_middle_east': {
        'share': 0.07,
        'bandwidth_mean': 5,
        'bandwidth_std': 5,
        'bandwidth_min': 0.3,
        'bandwidth_max': 30,
    },
}

# ── Device profiles ───────────────────────────────────────────────────────────
DEVICE_PROFILES = {
    'mobile': {
        'share': 0.55,
        'max_resolution': 720,
        'startup_delay_s': 2.0,
        'buffer_threshold_s': 8,
        'completion_rate': 0.55,
    },
    'desktop': {
        'share': 0.30,
        'max_resolution': 1080,
        'startup_delay_s': 1.2,
        'buffer_threshold_s': 15,
        'completion_rate': 0.72,
    },
    'smart_tv': {
        'share': 0.15,
        'max_resolution': 2160,
        'startup_delay_s': 3.5,
        'buffer_threshold_s': 20,
        'completion_rate': 0.85,
    },
}


class ViewerSimulator:
    """
    Simulate viewer populations and derive delivery metrics.

    Usage:
        sim = ViewerSimulator(variants=[...])
        report = sim.run(n_viewers=10_000, video_duration_s=3600)
        print_report(report)
    """

    def __init__(self, variants: List[Dict], rng_seed: int = 42):
        """
        Args:
            variants: List of available variants, each with
                      {name, width, height, bitrate_mbps}
            rng_seed: Random seed for reproducibility
        """
        self.variants = sorted(variants, key=lambda v: v['bitrate_mbps'])
        self.rng = np.random.default_rng(rng_seed)

    # ── Simulation core ───────────────────────────────────────────────────────

    def run(self, n_viewers: int = 10_000, video_duration_s: float = 3600) -> Dict:
        """
        Run simulation and return aggregated metrics.

        Args:
            n_viewers: Number of simulated viewers
            video_duration_s: Video duration in seconds

        Returns:
            Report dict with KPIs
        """
        logger.info(f"Simulating {n_viewers:,} viewers × {video_duration_s/60:.0f} min video")

        viewers = self._generate_viewers(n_viewers)
        results = [self._simulate_one(v, video_duration_s) for v in viewers]

        return self._aggregate(results, n_viewers, video_duration_s)

    def _generate_viewers(self, n: int) -> List[Dict]:
        """Sample viewer attributes from regional and device distributions."""
        viewers = []

        region_keys   = list(REGIONAL_PROFILES.keys())
        region_shares = [REGIONAL_PROFILES[r]['share'] for r in region_keys]
        device_keys   = list(DEVICE_PROFILES.keys())
        device_shares = [DEVICE_PROFILES[d]['share'] for d in device_keys]

        region_idx = self.rng.choice(len(region_keys), size=n, p=region_shares)
        device_idx = self.rng.choice(len(device_keys), size=n, p=device_shares)

        for i in range(n):
            region = REGIONAL_PROFILES[region_keys[region_idx[i]]]
            device = DEVICE_PROFILES[device_keys[device_idx[i]]]

            # Bandwidth: truncated normal
            bw = self.rng.normal(region['bandwidth_mean'], region['bandwidth_std'])
            bw = float(np.clip(bw, region['bandwidth_min'], region['bandwidth_max']))

            viewers.append({
                'region': region_keys[region_idx[i]],
                'device': device_keys[device_idx[i]],
                'bandwidth_mbps': bw,
                'max_resolution': device['max_resolution'],
                'startup_delay_s': device['startup_delay_s'],
                'buffer_threshold_s': device['buffer_threshold_s'],
                'completion_rate': device['completion_rate'],
            })

        return viewers

    def _select_quality(self, viewer: Dict) -> Dict:
        """ABR: pick highest variant fitting bandwidth and device."""
        available_bw = viewer['bandwidth_mbps'] * 0.8  # 80% headroom
        max_res = viewer['max_resolution']

        best = self.variants[0]  # lowest as fallback
        for v in self.variants:
            if v['bitrate_mbps'] <= available_bw and v['height'] <= max_res:
                best = v
        return best

    def _simulate_one(self, viewer: Dict, duration_s: float) -> Dict:
        """Simulate a single viewer session."""
        quality = self._select_quality(viewer)

        # Startup delay (device base + 1/bandwidth factor)
        startup_delay = viewer['startup_delay_s'] + (2.0 / max(viewer['bandwidth_mbps'], 0.1))
        startup_delay = min(startup_delay, 15.0)

        # Buffering: probability based on bandwidth vs bitrate margin
        margin = viewer['bandwidth_mbps'] / max(quality['bitrate_mbps'], 0.01)
        rebuffer_prob = max(0, 1 - margin) * 0.6  # 60% max rebuffer rate when bw == bitrate
        rebuffer_events = int(self.rng.binomial(
            n=max(1, int(duration_s / 120)),   # opportunity every 2 min
            p=rebuffer_prob
        ))
        rebuffer_duration_s = rebuffer_events * self.rng.exponential(scale=3.0)

        # Quality switches (triggered by simulated bandwidth fluctuation)
        n_switches = int(self.rng.poisson(lam=max(0, rebuffer_prob * 3)))

        # Watch time
        completion = viewer['completion_rate'] * self.rng.uniform(0.7, 1.3)
        completion = float(np.clip(completion, 0, 1))
        watch_time_s = duration_s * completion

        # Data consumed (bitrate × watch_time × completion)
        data_consumed_gb = (quality['bitrate_mbps'] * watch_time_s / 8) / 1024

        return {
            'region': viewer['region'],
            'device': viewer['device'],
            'bandwidth_mbps': viewer['bandwidth_mbps'],
            'quality_selected': quality['name'],
            'bitrate_served_mbps': quality['bitrate_mbps'],
            'startup_delay_s': round(startup_delay, 2),
            'rebuffer_events': rebuffer_events,
            'rebuffer_duration_s': round(float(rebuffer_duration_s), 2),
            'quality_switches': n_switches,
            'completion_rate': round(completion, 3),
            'watch_time_s': round(watch_time_s, 1),
            'data_consumed_gb': round(data_consumed_gb, 4),
        }

    @staticmethod
    def _aggregate(results: List[Dict], n_viewers: int, duration_s: float) -> Dict:
        """Aggregate per-viewer results into KPIs."""
        # Per-viewer arrays
        startups  = np.array([r['startup_delay_s']     for r in results])
        rebuf_ev  = np.array([r['rebuffer_events']      for r in results])
        rebuf_dur = np.array([r['rebuffer_duration_s']  for r in results])
        switches  = np.array([r['quality_switches']      for r in results])
        bitrates  = np.array([r['bitrate_served_mbps']  for r in results])
        data      = np.array([r['data_consumed_gb']      for r in results])
        comps     = np.array([r['completion_rate']       for r in results])

        # Quality distribution
        from collections import Counter
        quality_dist = dict(Counter(r['quality_selected'] for r in results))
        device_dist  = dict(Counter(r['device']           for r in results))
        region_dist  = dict(Counter(r['region']           for r in results))

        total_data_gb = float(data.sum())

        return {
            'simulation': {
                'n_viewers': n_viewers,
                'video_duration_min': round(duration_s / 60, 1),
            },
            'kpis': {
                'avg_startup_delay_s':    round(float(startups.mean()), 2),
                'p95_startup_delay_s':    round(float(np.percentile(startups, 95)), 2),
                'rebuffer_rate_pct':      round(float((rebuf_ev > 0).mean() * 100), 1),
                'avg_rebuffer_duration_s':round(float(rebuf_dur[rebuf_ev > 0].mean()) if (rebuf_ev > 0).any() else 0, 2),
                'avg_quality_switches':   round(float(switches.mean()), 2),
                'avg_bitrate_mbps':       round(float(bitrates.mean()), 3),
                'avg_completion_rate_pct':round(float(comps.mean() * 100), 1),
                'total_data_delivered_gb':round(total_data_gb, 1),
            },
            'quality_distribution': {
                k: round(v / n_viewers * 100, 1)
                for k, v in sorted(quality_dist.items())
            },
            'device_distribution': {
                k: round(v / n_viewers * 100, 1)
                for k, v in sorted(device_dist.items())
            },
            'region_distribution': {
                k: round(v / n_viewers * 100, 1)
                for k, v in sorted(region_dist.items())
            },
        }


def print_simulation_report(report: Dict):
    """Print a formatted simulation report."""
    sim = report['simulation']
    kpis = report['kpis']

    print("\n" + "="*70)
    print("VIEWER SIMULATION REPORT")
    print("="*70)
    print(f"Viewers simulated: {sim['n_viewers']:,}  |  Video: {sim['video_duration_min']} min")

    print("\n── Key Performance Indicators ──────────────────────────────")
    print(f"  Avg startup delay:     {kpis['avg_startup_delay_s']:.2f}s  "
          f"(p95: {kpis['p95_startup_delay_s']:.2f}s)")
    print(f"  Rebuffer rate:         {kpis['rebuffer_rate_pct']:.1f}%  "
          f"(avg {kpis['avg_rebuffer_duration_s']:.1f}s when rebuffering)")
    print(f"  Avg quality switches:  {kpis['avg_quality_switches']:.2f} per session")
    print(f"  Avg bitrate served:    {kpis['avg_bitrate_mbps']:.2f} Mbps")
    print(f"  Avg completion rate:   {kpis['avg_completion_rate_pct']:.1f}%")
    print(f"  Total data delivered:  {kpis['total_data_delivered_gb']:.1f} GB")

    print("\n── Quality Distribution ────────────────────────────────────")
    for q, pct in sorted(report['quality_distribution'].items()):
        bar = '█' * int(pct / 2)
        print(f"  {q:<8} {pct:>5.1f}%  {bar}")

    print("\n── Device Mix ──────────────────────────────────────────────")
    for d, pct in sorted(report['device_distribution'].items()):
        bar = '█' * int(pct / 2)
        print(f"  {d:<12} {pct:>5.1f}%  {bar}")

    print("\n── Region Mix ──────────────────────────────────────────────")
    for r, pct in sorted(report['region_distribution'].items()):
        bar = '█' * int(pct / 3)
        print(f"  {r:<22} {pct:>5.1f}%  {bar}")
    print()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    variants = [
        {'name': '360p',  'width': 640,  'height': 360,  'bitrate_mbps': 0.8},
        {'name': '480p',  'width': 854,  'height': 480,  'bitrate_mbps': 1.5},
        {'name': '720p',  'width': 1280, 'height': 720,  'bitrate_mbps': 3.0},
        {'name': '1080p', 'width': 1920, 'height': 1080, 'bitrate_mbps': 5.0},
    ]

    sim = ViewerSimulator(variants)
    report = sim.run(n_viewers=10_000, video_duration_s=3600)
    print_simulation_report(report)
