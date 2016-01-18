from contextlib import contextmanager

__all__ = ['local_ns']


@contextmanager
def local_ns(expr):
    yield expr
