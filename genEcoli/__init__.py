from ecoli.library.schema import (
    divide_binomial,
    divide_bulk,
    divide_by_domain,
    divide_ribosomes_by_RNA,
    divide_RNAs_by_domain,
    divide_set_none,
    empty_dict_divider,
    bulk_numpy_updater,
)

from genEcoli.schemas import ECOLI_TYPES
from genEcoli.interface import OmniStep, OmniProcess, update_inheritance, scan_processes, update_processes, migrate_composite


def register_types(core):
    core.register_types(
        ECOLI_TYPES)

    return core

