from process_bigraph import allocate_core
from bigraph_schema.core import Core

from .ecoli_types import ECOLI_TYPES as ECOLI_TYPES_REPRESENTATION


def get_core() -> Core:
    return allocate_core()


def register_types(c: Core) -> Core:
    c.register_types(ECOLI_TYPES_REPRESENTATION)
    return c


def initialize_core() -> Core:
    c = get_core()
    return register_types(c)


# core = initialize_core()
core = get_core()
