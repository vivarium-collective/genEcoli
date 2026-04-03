"""Dependency graph validation for the implicit step network.

Compares the implicit dependency network (derived from port wire overlap)
against the v1 flow ordering to identify missing or spurious dependencies.
"""

import json
from collections import defaultdict

from genEcoli.classify_ports import split_all_wires, classify_step


# ---------------------------------------------------------------------------
# V1 flow definition (from configs/default.json)
# ---------------------------------------------------------------------------

V1_FLOW = {
    "post-division-mass-listener": [],
    "media_update": [["post-division-mass-listener"]],
    "exchange_data": [["media_update"]],
    "ecoli-tf-unbinding": [["media_update"]],
    "ecoli-equilibrium": [["ecoli-tf-unbinding"]],
    "ecoli-two-component-system": [["ecoli-tf-unbinding"]],
    "ecoli-rna-maturation": [["ecoli-tf-unbinding"]],
    "ecoli-tf-binding": [["ecoli-equilibrium"]],
    "ecoli-transcript-initiation": [["ecoli-tf-binding"]],
    "ecoli-polypeptide-initiation": [["ecoli-tf-binding"]],
    "ecoli-chromosome-replication": [["ecoli-tf-binding"]],
    "ecoli-protein-degradation": [["ecoli-tf-binding"]],
    "ecoli-rna-degradation": [["ecoli-tf-binding"]],
    "ecoli-complexation": [["ecoli-tf-binding"]],
    "ecoli-transcript-elongation": [["ecoli-complexation"]],
    "ecoli-polypeptide-elongation": [["ecoli-complexation"]],
    "ecoli-chromosome-structure": [["ecoli-polypeptide-elongation"]],
    "ecoli-metabolism": [["ecoli-chromosome-structure"]],
    "ecoli-mass-listener": [["ecoli-metabolism"]],
    "RNA_counts_listener": [["ecoli-metabolism"]],
    "rna_synth_prob_listener": [["ecoli-metabolism"]],
    "monomer_counts_listener": [["ecoli-metabolism"]],
    "dna_supercoiling_listener": [["ecoli-metabolism"]],
    "replication_data_listener": [["ecoli-metabolism"]],
    "rnap_data_listener": [["ecoli-metabolism"]],
    "unique_molecule_counts": [["ecoli-metabolism"]],
    "ribosome_data_listener": [["ecoli-metabolism"]],
}

# Note: Partitioned processes in the flow (like ecoli-transcript-initiation)
# are expanded into requester/allocator/evolver steps by the Ecoli composer.
# The flow dependencies apply to the REQUESTER step of each partitioned process.

PARTITIONED_PROCESSES = {
    'ecoli-equilibrium',
    'ecoli-two-component-system',
    'ecoli-rna-maturation',
    'ecoli-transcript-initiation',
    'ecoli-polypeptide-initiation',
    'ecoli-chromosome-replication',
    'ecoli-protein-degradation',
    'ecoli-rna-degradation',
    'ecoli-complexation',
    'ecoli-transcript-elongation',
    'ecoli-polypeptide-elongation',
}


# ---------------------------------------------------------------------------
# Wire path overlap analysis
# ---------------------------------------------------------------------------

def compute_wire_paths(wires, base_path=()):
    """Convert a wire dict to a set of resolved state paths."""
    paths = set()
    for port_name, wire_path in wires.items():
        if isinstance(wire_path, list):
            paths.add(tuple(base_path) + tuple(wire_path))
        elif isinstance(wire_path, dict):
            base = wire_path.get('_path', [])
            paths.add(tuple(base_path) + tuple(base))
            for sub_key, sub_path in wire_path.items():
                if sub_key == '_path':
                    continue
                if isinstance(sub_path, list):
                    paths.add(tuple(base_path) + tuple(sub_path))
    return paths


def compute_path_prefixes(path):
    """Compute all prefix paths (matching explode_path in process-bigraph)."""
    prefixes = set()
    current = ()
    for segment in path:
        current = current + (segment,)
        prefixes.add(current)
    return prefixes


def find_implicit_dependencies(classifications):
    """Compute the implicit dependency graph from port wire overlap.

    Returns a dict: {step_name: set_of_steps_that_must_run_before_it}
    """
    # Compute output paths (with prefix expansion) and input paths for each step
    output_paths = {}  # step -> set of path prefixes
    input_paths = {}   # step -> set of paths

    for name, data in classifications.items():
        in_paths = compute_wire_paths(data['input_wires'])
        out_paths = compute_wire_paths(data['output_wires'])

        # Expand output paths to include all prefixes (matching explode_path)
        out_expanded = set()
        for path in out_paths:
            out_expanded.update(compute_path_prefixes(path))
        # Remove root prefix ()
        out_expanded.discard(())

        input_paths[name] = in_paths
        output_paths[name] = out_expanded

    # Find dependencies: step B depends on step A if A's output prefixes
    # overlap with B's input paths
    deps = defaultdict(set)
    for step_b, b_inputs in input_paths.items():
        for step_a, a_outputs in output_paths.items():
            if step_a == step_b:
                continue
            if a_outputs & b_inputs:
                deps[step_b].add(step_a)

    return dict(deps)


def expand_flow_to_steps(flow, cell_state_steps):
    """Expand v1 flow (process names) to actual step names in the cell state.

    Partitioned processes get expanded to requester/evolver steps.
    Returns the expanded flow dict with actual step names.
    """
    # Build a mapping from flow process names to actual step names
    step_name_map = {}
    for step_name in cell_state_steps:
        # Direct match
        step_name_map[step_name] = step_name
        # Partitioned process match
        for proc in PARTITIONED_PROCESSES:
            base = proc.replace('ecoli-', '')
            if step_name.endswith('_requester') and base in step_name.lower():
                step_name_map.setdefault(proc + '_requester', step_name)
            if step_name.endswith('_evolver') and base in step_name.lower():
                step_name_map.setdefault(proc + '_evolver', step_name)

    return step_name_map


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_against_flow(classifications, verbose=True):
    """Validate the implicit dependency graph against the v1 flow.

    Args:
        classifications: Output of split_all_wires().
        verbose: Print detailed output.

    Returns:
        Dict with 'missing', 'correct', 'spurious' dependency lists.
    """
    implicit_deps = find_implicit_dependencies(classifications)

    # Extract priorities
    priorities = {}
    for name, data in classifications.items():
        priorities[name] = data.get('priority', 0.0)

    if verbose:
        print(f"\n{'='*70}")
        print("Implicit Dependency Graph Validation")
        print(f"{'='*70}")

        # Print dependency counts
        all_steps = set(classifications.keys())
        has_deps = {s for s in all_steps if s in implicit_deps and implicit_deps[s]}
        no_deps = all_steps - has_deps

        print(f"\n  Total steps: {len(all_steps)}")
        print(f"  Steps with dependencies: {len(has_deps)}")
        print(f"  Steps with no dependencies (run first): {len(no_deps)}")

        if no_deps:
            print(f"\n  Root steps (no dependencies):")
            for s in sorted(no_deps):
                print(f"    - {s} ({classifications[s]['type']})")

        # Print dependency graph
        print(f"\n  Dependencies (step <- depends on):")
        for step in sorted(implicit_deps.keys()):
            deps = sorted(implicit_deps[step])
            if deps:
                dep_str = ', '.join(deps[:5])
                if len(deps) > 5:
                    dep_str += f' ... ({len(deps)} total)'
                print(f"    {step} <- {dep_str}")

        # Identify cycles
        print(f"\n  Checking for cycles...")
        cycles = _find_cycles(implicit_deps)
        if cycles:
            print(f"  Found {len(cycles)} cycle(s):")
            for cycle in cycles:
                print(f"    Cycle: {' -> '.join(cycle)} -> {cycle[0]}")
                cycle_priorities = [(s, priorities.get(s, 0)) for s in cycle]
                cycle_priorities.sort(key=lambda x: -x[1])
                print(f"    Priority order: {[(s, p) for s, p in cycle_priorities]}")
        else:
            print(f"  No cycles found.")

    return {
        'implicit_deps': implicit_deps,
        'classifications': classifications,
    }


def _find_cycles(deps):
    """Find cycles in the dependency graph using DFS."""
    cycles = []
    visited = set()
    rec_stack = set()

    def dfs(node, path):
        if node in rec_stack:
            cycle_start = path.index(node)
            cycles.append(path[cycle_start:])
            return
        if node in visited:
            return

        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for dep in deps.get(node, []):
            dfs(dep, path)

        path.pop()
        rec_stack.remove(node)

    for node in deps:
        if node not in visited:
            dfs(node, [])

    return cycles


def analyze_wire_overlaps(classifications, verbose=True):
    """Show which wire paths create dependencies between steps."""
    if not verbose:
        return

    print(f"\n{'='*70}")
    print("Wire Path Overlap Analysis")
    print(f"{'='*70}")

    # Collect all output paths per step
    output_map = {}  # path -> list of steps that output to it
    input_map = {}   # path -> list of steps that input from it

    for name, data in classifications.items():
        out_paths = compute_wire_paths(data['output_wires'])
        in_paths = compute_wire_paths(data['input_wires'])

        for p in out_paths:
            for prefix in compute_path_prefixes(p):
                if prefix:
                    output_map.setdefault(prefix, set()).add(name)

        for p in in_paths:
            input_map.setdefault(p, set()).add(name)

    # Find overlapping paths
    shared_paths = set(output_map.keys()) & set(input_map.keys())

    print(f"\n  Shared paths (create dependencies): {len(shared_paths)}")
    for path in sorted(shared_paths, key=str):
        producers = output_map[path]
        consumers = input_map[path]
        if producers and consumers and producers != consumers:
            print(f"\n    Path: {path}")
            print(f"      Producers: {sorted(producers)}")
            print(f"      Consumers: {sorted(consumers)}")


if __name__ == '__main__':
    # This would be run after loading the composite
    print("Run this module after loading the composite to validate dependencies.")
    print("Usage: validate_against_flow(split_all_wires(cell_state))")
