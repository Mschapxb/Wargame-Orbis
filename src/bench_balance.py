"""Banc d'équilibrage des affrontements de référence.

    python src/bench_balance.py [N] [OFF] [W H]

Enveloppe de compatibilité: la logique vit dans bench.py (suite « balance »).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bench

bench.legacy_main("balance", sys.argv[1:])
