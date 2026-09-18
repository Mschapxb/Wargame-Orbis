"""Hasard de génération à portée limitée.

La carte, la météo tirée au sort et le déploiement tirent leur hasard via
`RNG`. Hors de tout bloc `using`, `RNG` délègue au random global: une
bataille non graînée se comporte exactement comme avant. Dans un bloc

    with using(random.Random(graine)):
        ...

tous ces tirages viennent du générateur fourni, et le random global n'est
ni lu ni réinitialisé. Random(graine) produit la même suite que
random.seed(graine): une graine donne la même carte qu'avant ce module.
"""
import contextlib
import contextvars
import random

_current = contextvars.ContextVar("rng_scope", default=random)


class _Proxy:
    """Délègue chaque attribut (randint, uniform, choice…) au générateur
    actif."""

    def __getattr__(self, name):
        return getattr(_current.get(), name)


RNG = _Proxy()


@contextlib.contextmanager
def using(rng):
    """Fait de `rng` la source de RNG le temps du bloc (imbriquable)."""
    token = _current.set(rng)
    try:
        yield rng
    finally:
        _current.reset(token)
