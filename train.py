#!/usr/bin/env python3
"""
NanoStream - Retrain ML models on new benchmark data.

Usage:
    # Train on synthetic data (default)
    python train.py

    # Train on your own benchmark CSV
    python train.py --data my_benchmarks.csv

CSV format:
    motion,fps,entropy,resolution,scene_cuts,color_variance,edge_density,content_type,best_codec,optimal_crf
    4.5,30,6.2,1080,12.5,75.2,0.041,movie,h265,23
    ...
"""

import json
import argparse
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def generate_synthetic_data(n: int = 2000) -> list:
    """Generate synthetic training data based on codec benchmark research."""
    import numpy as np
    np.random.seed(42)

    CT_MAP = {
        'animation': {'motion': (0.5, 4), 'fps': [24, 30], 'entropy': (3.5, 5.5),
                      'resolution': [720, 1080], 'scene_cuts': (0.5, 5),
                      'color_variance': (20, 60), 'edge_density': (0.01, 0.04),
                      'weights': [0.1, 0.7, 0.2]},
        'sports':    {'motion': (8, 20),  'fps': [50, 60], 'entropy': (6, 8),
                      'resolution': [1080, 1440, 2160], 'scene_cuts': (15, 40),
                      'color_variance': (60, 120), 'edge_density': (0.04, 0.09),
                      'weights': [0.05, 0.35, 0.6]},
        'lecture':   {'motion': (0.1, 2), 'fps': [24, 30], 'entropy': (2, 4),
                      'resolution': [720, 1080], 'scene_cuts': (0.1, 3),
                      'color_variance': (10, 40), 'edge_density': (0.05, 0.12),
                      'weights': [0.15, 0.75, 0.1]},
        'movie':     {'motion': (2, 9),   'fps': [24, 30], 'entropy': (5, 7.5),
                      'resolution': [1080, 1440, 2160], 'scene_cuts': (5, 20),
                      'color_variance': (50, 110), 'edge_density': (0.02, 0.07),
                      'weights': [0.1, 0.5, 0.4]},
        'gaming':    {'motion': (5, 18),  'fps': [60, 120, 144], 'entropy': (5.5, 7.5),
                      'resolution': [1080, 1440, 2160], 'scene_cuts': (10, 35),
                      'color_variance': (40, 100), 'edge_density': (0.03, 0.08),
                      'weights': [0.2, 0.3, 0.5]},
    }
    CODECS = ['h264', 'h265', 'av1']
    BASE_CRFS = {'h264': 22, 'h265': 24, 'av1': 30}

    samples = []
    cts = list(CT_MAP.keys())
    for i in range(n):
        ct = cts[i % len(cts)]
        p = CT_MAP[ct]

        motion = np.random.uniform(*p['motion'])
        fps    = np.random.choice(p['fps'])
        entropy = np.random.uniform(*p['entropy'])
        resolution = np.random.choice(p['resolution'])
        scene_cuts = np.random.uniform(*p['scene_cuts'])
        color_variance = np.random.uniform(*p['color_variance'])
        edge_density = np.random.uniform(*p['edge_density'])
        codec = CODECS[np.random.choice(3, p=p['weights'])]
        crf = int(np.clip(BASE_CRFS[codec] + np.random.randint(-3, 4) - int(motion / 5), 10, 51))

        samples.append({
            'content_type': ct,
            'motion': round(float(motion), 3),
            'fps': int(fps),
            'entropy': round(float(entropy), 3),
            'resolution': int(resolution),
            'scene_cuts': round(float(scene_cuts), 3),
            'color_variance': round(float(color_variance), 3),
            'edge_density': round(float(edge_density), 5),
            'best_codec': codec,
            'optimal_crf': crf,
        })

    return samples


def load_csv_data(path: str) -> list:
    """Load benchmark data from CSV file."""
    import csv
    samples = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            samples.append({
                'content_type': row['content_type'],
                'motion': float(row['motion']),
                'fps': int(row['fps']),
                'entropy': float(row['entropy']),
                'resolution': int(row['resolution']),
                'scene_cuts': float(row['scene_cuts']),
                'color_variance': float(row['color_variance']),
                'edge_density': float(row['edge_density']),
                'best_codec': row['best_codec'],
                'optimal_crf': int(row['optimal_crf']),
            })
    return samples


def main():
    parser = argparse.ArgumentParser(description='Train NanoStream ML models')
    parser.add_argument('--data', help='CSV file with benchmark data (optional)')
    parser.add_argument('--n', type=int, default=2000, help='Synthetic samples if no CSV')
    parser.add_argument('--output', default='models.pkl', help='Output model file')
    args = parser.parse_args()

    if args.data:
        logger.info(f"Loading data from {args.data}")
        samples = load_csv_data(args.data)
    else:
        logger.info(f"Generating {args.n} synthetic training samples")
        samples = generate_synthetic_data(args.n)

    logger.info(f"Training on {len(samples)} samples → {args.output}")

    from ml_encoder import ModelTrainer
    trainer = ModelTrainer(save_path=args.output)
    metrics = trainer.train(samples)

    print(f"\n✓ Training complete")
    print(f"  Codec accuracy:  {metrics['accuracy']:.1%}")
    print(f"  5-fold CV:       {metrics['cv_mean']:.1%}")
    print(f"  CRF MAE:         {metrics['crf_mae']:.2f}")
    print(f"  Model saved:     {args.output}")
    print(f"\nNote: ~58-65% accuracy is near-optimal for this task.")
    print(f"The Bayes error ceiling is ~60% due to codec choice being")
    print(f"content-dependent but not fully deterministic.")


if __name__ == '__main__':
    main()
