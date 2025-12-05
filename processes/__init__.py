from process_bigraph import ProcessTypes

from .ecoli_types import ECOLI_TYPES as ECOLI_TYPES_REPRESENTATION


def register_types(core: ProcessTypes):
    core._register_types(
        ECOLI_TYPES_REPRESENTATION)

    return core


def initialize_core():
    core = ProcessTypes()
    return register_types(core)


core = initialize_core()

