"""Banc d'équilibrage Village et Défilé.

    python src/bench_maps.py [N] [OFF] [W H]

Enveloppe de compatibilité: la logique vit dans bench.py (suite « maps »).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bench

bench.legacy_main("maps", sys.argv[1:])
