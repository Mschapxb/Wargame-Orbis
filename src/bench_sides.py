"""Banc de biais de côté (une armée contre son double).

    python src/bench_sides.py [N] [OFF] [W H]

Enveloppe de compatibilité: la logique vit dans bench.py (suite « sides »).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bench

bench.legacy_main("sides", sys.argv[1:])
