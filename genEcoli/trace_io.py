"""Runtime I/O tracer for the migrated E. coli model.

Instruments EcoliComposite.run_steps to record what each step actually
reads (input port names) and writes (output delta keys) during execution.
"""

import json
import copy
import dill

from ecoli.processes.partition import Requester, Evolver
from ecoli.processes.allocator import Allocator

from bigraph_schema import get_path, allocate_core

from genEcoli.interface import (
    EcoliComposite,
    _build_view,
    fill_missing_state,
    apply_step_update,
    _make_arrays_writeable,
    scan_update,
)
from genEcoli.types import ECOLI_TYPES


# ---------------------------------------------------------------------------
# Step type classification
# ---------------------------------------------------------------------------

def classify_step(step_name, instance):
    """Classify a step by its type in the v1 architecture.

    Returns one of: 'requester', 'evolver', 'allocator', 'unique_update',
    'listener', 'global_clock', 'other'.
    """
    if isinstance(instance, Requester):
        return 'requester'
    if isinstance(instance, Evolver):
        return 'evolver'
    if isinstance(instance, Allocator):
        return 'allocator'

    name = step_name.lower()
    if 'unique_update' in name or 'unique-update' in name:
        return 'unique_update'
    if ('listener' in name or name in (
            'rna_counts_listener', 'RNA_counts_listener',
            'rna_synth_prob_listener', 'monomer_counts_listener',
            'dna_supercoiling_listener', 'replication_data_listener',
            'rnap_data_listener', 'unique_molecule_counts',
            'ribosome_data_listener', 'aggregator',
            'concentrations_deriver', 'shape')):
        return 'listener'
    if name in ('global_clock', 'global-clock'):
        return 'global_clock'
    return 'other'


# ---------------------------------------------------------------------------
# Tracing harness
# ---------------------------------------------------------------------------

def trace_model_io(pickle_path='out/migrate.pickle', timesteps=2, outpath='out/io_trace.json'):
    """Load the composite, run for N timesteps, and record I/O per step.

    Saves a JSON file with:
      {step_name: {
          type: str,
          input_wires: {port: wire_path},
          output_wires: {port: wire_path},
          delta_keys: [list of keys returned by next_update across all timesteps],
          view_keys: [list of keys in the state view across all timesteps],
      }}
    """
    core = allocate_core()
    core.register_types(ECOLI_TYPES)
    core = scan_update(core, 'ecoli.processes')

    with open(pickle_path, 'rb') as f:
        document = dill.load(f)

    ecoli = EcoliComposite(document, core=core)

    if not ecoli._cell_path:
        raise RuntimeError("Could not find cell state path in composite")

    cell_state = get_path(ecoli.state, ecoli._cell_path)

    # Collect step metadata
    trace = {}
    for step_name, edge in cell_state.items():
        if not isinstance(edge, dict) or 'instance' not in edge:
            continue
        instance = edge['instance']
        step_type = classify_step(step_name, instance)

        input_wires = edge.get('inputs', {})
        output_wires = edge.get('outputs', {})

        trace[step_name] = {
            'type': step_type,
            'input_wires': _serialize_wires(input_wires),
            'output_wires': _serialize_wires(output_wires),
            'delta_keys': set(),
            'view_keys': set(),
        }

    # Instrument run_steps to capture deltas
    original_run_steps = EcoliComposite.run_steps

    def tracing_run_steps(self, step_paths):
        if not step_paths:
            self.steps_run = set()
            return

        self._ensure_unique_updaters()
        update_paths = []

        for step_path in step_paths:
            step = get_path(self.state, step_path)
            if not isinstance(step, dict) or 'instance' not in step:
                continue

            instance = step['instance']
            cell_state_path = step_path[:-1]
            cs = get_path(self.state, cell_state_path)
            _make_arrays_writeable(cs)

            # Get step name (last element of path)
            step_name = step_path[-1]

            try:
                view = _build_view(cs, step, instance)
                if hasattr(instance, 'next_update'):
                    view = fill_missing_state(view, instance)
                    timestep_val = instance.parameters.get('timestep', 1.0)
                    delta = instance.next_update(timestep_val, view)
                else:
                    delta = instance.update(view)

                # Record trace data
                if step_name in trace:
                    if view:
                        trace[step_name]['view_keys'].update(view.keys())
                    if delta:
                        trace[step_name]['delta_keys'].update(delta.keys())

                if delta:
                    apply_step_update(cs, step, instance, delta,
                                      unique_updaters=self._unique_updaters)

                output_wires = step.get('outputs', {})
                for port_name, wire_path in output_wires.items():
                    if isinstance(wire_path, list) and wire_path:
                        full_path = tuple(list(cell_state_path) + wire_path)
                        update_paths.append(full_path)
                    elif isinstance(wire_path, dict):
                        base = wire_path.get('_path', [])
                        if base:
                            full_path = tuple(list(cell_state_path) + base)
                            update_paths.append(full_path)
            except Exception as e:
                print(f"  Warning: {step_name} failed: {e}")

        self.expire_process_paths(update_paths)
        to_run = self.cycle_step_state()
        if to_run:
            self.run_steps(to_run)
        else:
            self.steps_run = set()

    # Patch and run
    EcoliComposite.run_steps = tracing_run_steps
    try:
        for i in range(timesteps):
            ecoli.run(1.0)
            print(f"  Timestep {i+1}/{timesteps} complete")
    finally:
        EcoliComposite.run_steps = original_run_steps

    # Convert sets to sorted lists for JSON serialization
    result = {}
    for step_name, data in trace.items():
        result[step_name] = {
            'type': data['type'],
            'input_wires': data['input_wires'],
            'output_wires': data['output_wires'],
            'delta_keys': sorted(data['delta_keys']),
            'view_keys': sorted(data['view_keys']),
        }

    import os
    os.makedirs(os.path.dirname(outpath) or '.', exist_ok=True)
    with open(outpath, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"Saved I/O trace to {outpath}")
    _print_trace_summary(result)
    return result


def _serialize_wires(wires):
    """Convert wire paths to JSON-serializable format."""
    result = {}
    for key, value in wires.items():
        if isinstance(value, list):
            result[key] = value
        elif isinstance(value, dict):
            result[key] = _serialize_wires(value)
        elif isinstance(value, tuple):
            result[key] = list(value)
        else:
            result[key] = str(value)
    return result


def _print_trace_summary(trace):
    """Print a summary of the trace data."""
    print(f"\n{'='*70}")
    print(f"I/O Trace Summary: {len(trace)} steps")
    print(f"{'='*70}")

    by_type = {}
    for name, data in trace.items():
        t = data['type']
        by_type.setdefault(t, []).append(name)

    for step_type, names in sorted(by_type.items()):
        print(f"\n  {step_type} ({len(names)} steps):")
        for name in sorted(names):
            data = trace[name]
            in_ports = sorted(data['input_wires'].keys())
            delta = data['delta_keys']
            # Filter out flow tokens
            delta = [k for k in delta if not k.startswith('_flow_')]
            print(f"    {name}:")
            print(f"      inputs:  {in_ports}")
            print(f"      outputs: {delta}")


def load_trace(path='out/io_trace.json'):
    """Load a previously saved trace."""
    with open(path) as f:
        return json.load(f)


if __name__ == '__main__':
    trace_model_io()
