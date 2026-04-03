"""Step classification and wire splitting for implicit dependency network.

Classifies each step in the migrated E. coli model by type and generates
separate input/output wire dicts that produce the correct implicit
dependency network when used with process-bigraph's build_step_network.
"""

from ecoli.processes.partition import Requester, Evolver
try:
    from ecoli.processes.allocator import Allocator
except ImportError:
    Allocator = None


# ---------------------------------------------------------------------------
# Step type classification
# ---------------------------------------------------------------------------

def classify_step(step_name, instance):
    """Classify a step instance into a category for port splitting.

    Returns: 'requester', 'evolver', 'allocator', 'unique_update',
             'listener', 'global_clock', 'emitter', or 'other'.
    """
    if isinstance(instance, Requester):
        return 'requester'
    if isinstance(instance, Evolver):
        return 'evolver'
    if Allocator and isinstance(instance, Allocator):
        return 'allocator'

    name = step_name.lower().replace('-', '_')
    if 'unique_update' in name or 'unique-update' in name:
        return 'unique_update'
    if name == 'emitter':
        return 'emitter'
    if name in ('global_clock', 'global-clock'):
        return 'global_clock'
    if _is_listener(name):
        return 'listener'
    return 'other'


def _is_listener(name):
    """Check if a step name corresponds to a listener/observer."""
    listener_names = {
        'ecoli_mass_listener', 'ecoli-mass-listener',
        'post_division_mass_listener', 'post-division-mass-listener',
        'rna_counts_listener', 'rna-counts-listener',
        'rna_synth_prob_listener', 'rna-synth-prob-listener',
        'monomer_counts_listener', 'monomer-counts-listener',
        'dna_supercoiling_listener', 'dna-supercoiling-listener',
        'replication_data_listener', 'replication-data-listener',
        'rnap_data_listener', 'rnap-data-listener',
        'unique_molecule_counts', 'unique-molecule-counts',
        'ribosome_data_listener', 'ribosome-data-listener',
        'aggregator',
        'concentrations_deriver', 'concentrations-deriver',
        'shape', 'ecoli_shape', 'ecoli-shape',
    }
    return name in listener_names or 'listener' in name


# ---------------------------------------------------------------------------
# Known output ports per step type
# ---------------------------------------------------------------------------

# For non-partitioned steps, these are the ports that appear as keys
# in the delta dict returned by next_update(). Derived from code analysis.
# Keys NOT in this set are input-only.

KNOWN_OUTPUTS = {
    # Non-partitioned steps that read+write bulk
    'ecoli-tf-unbinding': {'bulk', 'promoters', 'next_update_time'},
    'ecoli-tf-binding': {'bulk', 'promoters', 'listeners', 'next_update_time'},
    'ecoli-chromosome-structure': {
        'listeners', 'bulk', 'active_replisomes', 'oriCs',
        'chromosome_domains', 'active_RNAPs', 'RNAs', 'active_ribosome',
        'full_chromosomes', 'chromosomal_segments', 'promoters', 'genes',
        'DnaA_boxes', 'next_update_time',
    },

    # Metabolism (non-partitioned Step) — various class names map to same flow entry
    'ecoli-metabolism': {'bulk', 'environment', 'listeners', 'next_update_time'},
    'ecoli-metabolism-redux': {'bulk', 'environment', 'listeners', 'next_update_time'},
    'ecoli-metabolism-redux-classic': {'bulk', 'environment', 'listeners', 'next_update_time'},

    # Environment steps
    'media_update': {'boundary'},
    'exchange_data': {'environment'},

    # Listeners - only write to their specific listener sub-paths
    'post-division-mass-listener': {'listeners'},
    'ecoli-mass-listener': {'listeners'},
    'RNA_counts_listener': {'listeners'},
    'rna_synth_prob_listener': {'rna_synth_prob'},  # wired to listeners
    'monomer_counts_listener': {'listeners'},
    'dna_supercoiling_listener': {'listeners'},
    'replication_data_listener': {'listeners'},
    'rnap_data_listener': {'listeners', 'next_update_time'},
    'unique_molecule_counts': {'listeners'},
    'ribosome_data_listener': {'listeners', 'next_update_time'},

    # Global clock
    'global_clock': {'global_time'},
}


# ---------------------------------------------------------------------------
# Wire splitting logic
# ---------------------------------------------------------------------------

def split_wires(step_name, instance, wires):
    """Split a step's wire dict into separate input and output wire dicts.

    IMPORTANT: Input wires are always the FULL wire set (all ports).
    This ensures the state view passed to next_update() is complete.
    Only output wires are narrowed to reflect actual writes, which
    controls the dependency graph without affecting step behavior.

    Args:
        step_name: Name of the step in the cell state.
        instance: The v1 process/step instance.
        wires: The combined wire dict (port_name -> wire_path).

    Returns:
        (input_wires, output_wires) tuple of wire dicts.
    """
    # Inputs are ALWAYS the full wire set for correct view building
    input_wires = dict(wires)

    step_type = classify_step(step_name, instance)

    if step_type == 'requester':
        output_wires = _output_requester(instance, wires)
    elif step_type == 'evolver':
        output_wires = _output_evolver(instance, wires)
    elif step_type == 'allocator':
        output_wires = _output_allocator(instance, wires)
    elif step_type == 'unique_update':
        output_wires = dict(wires)  # unique_update reads+writes all unique types
    elif step_type == 'listener':
        output_wires = _output_listener(instance, step_name, wires)
    elif step_type == 'global_clock':
        ports = _get_output_ports(instance, step_name)
        if ports is not None:
            output_wires = {k: v for k, v in wires.items() if k in ports}
        else:
            output_wires = {k: v for k, v in wires.items() if k == 'global_time'}
    elif step_type == 'emitter':
        output_wires = {}
    elif step_type == 'other':
        output_wires = _output_other(instance, step_name, wires)
    else:
        output_wires = dict(wires)

    return input_wires, output_wires


def _get_output_ports(instance, step_name):
    """Get output port names from the instance's _output_ports attribute,
    falling back to KNOWN_OUTPUTS, then to None (meaning all ports)."""
    if hasattr(instance, '_output_ports') and instance._output_ports is not None:
        return instance._output_ports
    return KNOWN_OUTPUTS.get(step_name)


def _output_requester(instance, wires):
    """Requester outputs: from _output_ports or default set."""
    ports = _get_output_ports(instance, None)
    if ports is None:
        ports = {'request', 'process', 'next_update_time', 'listeners'}
    return {k: v for k, v in wires.items() if k in ports}


def _output_evolver(instance, wires):
    """Evolver outputs: everything except _input_only_ports."""
    input_only = getattr(instance, '_input_only_ports',
                         {'allocate', 'global_time', 'timestep'})
    return {k: v for k, v in wires.items() if k not in input_only}


def _output_allocator(instance, wires):
    """Allocator outputs: from _output_ports or default set."""
    ports = _get_output_ports(instance, None)
    if ports is None:
        ports = {'allocate', 'request', 'listeners'}
    return {k: v for k, v in wires.items() if k in ports}


def _output_listener(instance, step_name, wires):
    """Listener outputs: from _output_ports, KNOWN_OUTPUTS, or default."""
    ports = _get_output_ports(instance, step_name)
    if ports is None:
        ports = {'listeners', 'rna_synth_prob', 'next_update_time'}
    return {k: v for k, v in wires.items() if k in ports}


def _output_other(instance, step_name, wires):
    """Non-partitioned step outputs: from _output_ports, KNOWN_OUTPUTS, or all."""
    ports = _get_output_ports(instance, step_name)
    if ports is not None:
        return {k: v for k, v in wires.items() if k in ports}
    return dict(wires)


# ---------------------------------------------------------------------------
# Bulk-specific handling
# ---------------------------------------------------------------------------

def remove_bulk_total_from_outputs(step_name, output_wires):
    """Remove bulk_total from outputs since it's always read-only.

    Several processes have both 'bulk' and 'bulk_total' ports wired to
    ('bulk',). bulk_total is used for read-only access to total counts
    (not partitioned). It should never appear as an output.
    """
    if 'bulk_total' in output_wires:
        del output_wires['bulk_total']
    return output_wires


# ---------------------------------------------------------------------------
# Full pipeline: split all wires in a cell state
# ---------------------------------------------------------------------------

def split_all_wires(cell_state):
    """Split wires for all steps in a cell state dict.

    Args:
        cell_state: Dict of {step_name: edge_dict} from the migrated composite.

    Returns:
        Dict of {step_name: {'input_wires': {...}, 'output_wires': {...}, 'type': str}}
    """
    result = {}

    for step_name, edge in cell_state.items():
        if not isinstance(edge, dict) or 'instance' not in edge:
            continue

        instance = edge['instance']
        wires = edge.get('inputs', {})  # In current code, inputs == outputs == topology

        input_wires, output_wires = split_wires(step_name, instance, wires)
        output_wires = remove_bulk_total_from_outputs(step_name, output_wires)

        result[step_name] = {
            'type': classify_step(step_name, instance),
            'input_wires': input_wires,
            'output_wires': output_wires,
        }

    return result


def print_classification(classifications):
    """Print a summary of step classifications and wire splits."""
    by_type = {}
    for name, data in classifications.items():
        t = data['type']
        by_type.setdefault(t, []).append(name)

    print(f"\n{'='*70}")
    print(f"Step Classification Summary: {len(classifications)} steps")
    print(f"{'='*70}")

    for step_type, names in sorted(by_type.items()):
        print(f"\n  {step_type} ({len(names)} steps):")
        for name in sorted(names):
            data = classifications[name]
            in_ports = sorted(data['input_wires'].keys())
            out_ports = sorted(data['output_wires'].keys())
            print(f"    {name}:")
            print(f"      IN:  {in_ports}")
            print(f"      OUT: {out_ports}")
