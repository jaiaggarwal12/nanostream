"""
NanoStream Cost Optimizer
Multi-cloud storage, bandwidth, and transcoding cost comparison.

Supported providers: AWS, Cloudflare, GCP, Azure
Pricing as of 2024 (update PRICING dict as rates change)
"""

from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


# ─── Pricing tables (per GB, USD) ────────────────────────────────────────────
PRICING = {
    'aws': {
        'name': 'AWS (S3 + CloudFront)',
        'storage_per_gb_month': 0.023,
        'bandwidth_per_gb':     0.085,
        'transcoding_h264_per_min': 0.0150,
        'transcoding_h265_per_min': 0.0300,
        'transcoding_av1_per_min':  0.0750,
    },
    'gcp': {
        'name': 'GCP (Cloud Storage + CDN)',
        'storage_per_gb_month': 0.020,
        'bandwidth_per_gb':     0.080,
        'transcoding_h264_per_min': 0.0120,
        'transcoding_h265_per_min': 0.0240,
        'transcoding_av1_per_min':  0.0600,
    },
    'azure': {
        'name': 'Azure (Blob + CDN)',
        'storage_per_gb_month': 0.018,
        'bandwidth_per_gb':     0.087,
        'transcoding_h264_per_min': 0.0145,
        'transcoding_h265_per_min': 0.0290,
        'transcoding_av1_per_min':  0.0580,
    },
    'cloudflare': {
        'name': 'Cloudflare (R2 + Stream)',
        'storage_per_gb_month': 0.015,
        'bandwidth_per_gb':     0.000,   # Cloudflare R2 has no egress fees
        'transcoding_h264_per_min': 0.0050,
        'transcoding_h265_per_min': 0.0100,
        'transcoding_av1_per_min':  0.0250,
    },
}

# Typical compression ratios (compressed size / original size)
COMPRESSION_RATIOS = {
    'h264': 0.40,   # H.264 achieves ~2.5x vs raw
    'h265': 0.28,   # H.265 ~3.5x
    'av1':  0.24,   # AV1  ~4x
}

TRANSCODING_KEYS = {
    'h264': 'transcoding_h264_per_min',
    'h265': 'transcoding_h265_per_min',
    'av1':  'transcoding_av1_per_min',
}


class CostOptimizer:
    """Calculate video delivery costs across cloud providers and codecs."""

    def compare_all(
        self,
        original_size_gb: float,
        duration_minutes: float,
        monthly_views: int,
        num_resolutions: int = 4,
        completion_rate: float = 0.70,
        retention_months: int = 12,
    ) -> List[Dict]:
        """
        Compare total cost across all providers × all codecs.

        Args:
            original_size_gb: Uncompressed video size
            duration_minutes: Video duration
            monthly_views: Expected views/month
            num_resolutions: Variants encoded (e.g. 360p, 720p, 1080p, 1440p)
            completion_rate: Average % of video watched (0–1)
            retention_months: Months to keep the video

        Returns:
            Sorted list of cost breakdowns (cheapest first)
        """
        results = []

        for provider_key, prices in PRICING.items():
            for codec in ['h264', 'h265', 'av1']:
                row = self._calculate(
                    provider_key, prices, codec,
                    original_size_gb, duration_minutes,
                    monthly_views, num_resolutions,
                    completion_rate, retention_months,
                )
                results.append(row)

        results.sort(key=lambda r: r['annual_total_usd'])

        # Tag savings vs worst option
        worst = results[-1]['annual_total_usd']
        for r in results:
            r['savings_vs_worst_pct'] = (
                (worst - r['annual_total_usd']) / worst * 100
            )

        return results

    def compare_codecs_on_provider(
        self,
        provider: str,
        original_size_gb: float,
        duration_minutes: float,
        monthly_views: int,
        num_resolutions: int = 4,
    ) -> List[Dict]:
        """Compare codecs on a single provider."""
        prices = PRICING.get(provider)
        if not prices:
            raise ValueError(f"Unknown provider: {provider}. Choose from {list(PRICING)}")

        results = []
        for codec in ['h264', 'h265', 'av1']:
            row = self._calculate(
                provider, prices, codec,
                original_size_gb, duration_minutes,
                monthly_views, num_resolutions,
            )
            results.append(row)

        results.sort(key=lambda r: r['annual_total_usd'])
        baseline = results[-1]['annual_total_usd']
        for r in results:
            r['savings_vs_h264_pct'] = (baseline - r['annual_total_usd']) / baseline * 100
        return results

    def recommend_cheapest(
        self,
        original_size_gb: float,
        duration_minutes: float,
        monthly_views: int,
    ) -> Dict:
        """Return the single cheapest provider+codec combination."""
        results = self.compare_all(original_size_gb, duration_minutes, monthly_views)
        best = results[0]
        worst = results[-1]
        savings = worst['annual_total_usd'] - best['annual_total_usd']

        return {
            'provider': best['provider'],
            'codec': best['codec'],
            'annual_cost_usd': best['annual_total_usd'],
            'annual_savings_vs_worst_usd': savings,
            'savings_pct': best['savings_vs_worst_pct'],
            'breakdown': best,
        }

    @staticmethod
    def _calculate(
        provider_key: str,
        prices: Dict,
        codec: str,
        original_size_gb: float,
        duration_minutes: float,
        monthly_views: int,
        num_resolutions: int = 4,
        completion_rate: float = 0.70,
        retention_months: int = 12,
    ) -> Dict:
        compressed_size_gb = original_size_gb * COMPRESSION_RATIOS[codec]

        # Storage: all resolutions (each variant stored separately)
        total_stored_gb = compressed_size_gb * num_resolutions
        monthly_storage = total_stored_gb * prices['storage_per_gb_month']
        annual_storage  = monthly_storage * retention_months

        # Bandwidth: monthly_views × compressed_size × completion_rate
        monthly_egress_gb = monthly_views * compressed_size_gb * completion_rate
        monthly_bandwidth = monthly_egress_gb * prices['bandwidth_per_gb']
        annual_bandwidth  = monthly_bandwidth * 12

        # Transcoding: once per video per resolution
        tc_key = TRANSCODING_KEYS[codec]
        transcoding_cost = duration_minutes * num_resolutions * prices[tc_key]

        annual_total = annual_storage + annual_bandwidth + transcoding_cost

        return {
            'provider': provider_key,
            'provider_name': prices['name'],
            'codec': codec,
            'compressed_size_gb': round(compressed_size_gb, 3),
            'compression_ratio': round(1 / COMPRESSION_RATIOS[codec], 2),
            'annual_storage_usd': round(annual_storage, 2),
            'annual_bandwidth_usd': round(annual_bandwidth, 2),
            'transcoding_usd': round(transcoding_cost, 2),
            'annual_total_usd': round(annual_total, 2),
            'monthly_egress_gb': round(monthly_egress_gb, 1),
        }


def print_comparison_table(results: List[Dict]):
    """Print a sorted cost comparison table."""
    print("\n" + "="*110)
    print("MULTI-CLOUD COST COMPARISON")
    print("="*110)
    print(f"{'Provider':<30} {'Codec':<7} {'Size(GB)':<10} {'Storage/yr':<13} "
          f"{'Bandwidth/yr':<14} {'Transcoding':<13} {'Total/yr':<12} {'Savings':<10}")
    print("-"*110)

    for r in results:
        savings_str = f"{r.get('savings_vs_worst_pct', 0):.0f}%"
        marker = " ◄ BEST" if results.index(r) == 0 else ""
        print(
            f"{r['provider_name']:<30} {r['codec']:<7} {r['compressed_size_gb']:<10.3f} "
            f"${r['annual_storage_usd']:<12.2f} ${r['annual_bandwidth_usd']:<13.2f} "
            f"${r['transcoding_usd']:<12.2f} ${r['annual_total_usd']:<11.2f} "
            f"{savings_str:<10}{marker}"
        )

    print("="*110)
    best = results[0]
    worst = results[-1]
    saved = worst['annual_total_usd'] - best['annual_total_usd']
    print(f"\n✓ Cheapest: {best['provider_name']} with {best['codec'].upper()}")
    print(f"  Annual cost: ${best['annual_total_usd']:.2f}")
    print(f"  vs most expensive (${worst['annual_total_usd']:.2f}): saves ${saved:.2f}/year ({best['savings_vs_worst_pct']:.0f}%)")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    opt = CostOptimizer()

    print("\nScenario: 1.5 GB video, 120 min, 10,000 views/month")
    results = opt.compare_all(
        original_size_gb=1.5,
        duration_minutes=120,
        monthly_views=10_000,
        num_resolutions=4,
    )
    print_comparison_table(results)

    print("\n" + "="*60)
    print("Best option recommendation:")
    rec = opt.recommend_cheapest(1.5, 120, 10_000)
    print(f"  Provider: {rec['provider']}")
    print(f"  Codec:    {rec['codec'].upper()}")
    print(f"  Annual:   ${rec['annual_cost_usd']:.2f}")
    print(f"  Saves:    ${rec['annual_savings_vs_worst_usd']:.2f} ({rec['savings_pct']:.0f}%) vs worst option")
