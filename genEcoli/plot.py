"""Bigraph visualization for the E. coli composite."""

import os
from bigraph_viz import plot_bigraph


ALWAYS_SKIP = {'unique_update', 'global_clock', 'bulk-timeline',
               'mark_d_period', 'division', 'exchange_data', 'media_update',
               'post-division-mass-listener'}

SKIP_PORTS = {'timestep', 'global_time', 'next_update_time', 'process'}

COLOR_GROUPS = {
    'dna':      ('#FFB6C1', lambda n: 'chromosome' in n),
    'rna':      ('#ADD8E6', lambda n: any(s in n for s in ('transcript', 'rna-', 'RNA', 'rnap'))),
    'protein':  ('#90EE90', lambda n: any(s in n for s in ('polypeptide', 'protein', 'ribosome'))),
    'meta':     ('#FFD700', lambda n: any(s in n for s in ('metabolism', 'equilibrium', 'complexation', 'two-component'))),
    'reg':      ('#DDA0DD', lambda n: any(s in n for s in ('tf-', 'tf_'))),
    'listen':   ('#D3D3D3', lambda n: 'listener' in n),
    'allocate': ('#FFA07A', lambda n: 'allocator' in n),
}


def _find_cell(state):
    """Find the cell-level dict (agents/0) in the state tree."""
    for v in state.values():
        if isinstance(v, dict):
            for v2 in v.values():
                if isinstance(v2, dict) and len(v2) > 10:
                    return v2
    return state


def _build_viz_cell(cell, show_partitioning=False):
    """Build a filtered visualization dict from the cell state.

    Args:
        cell: The cell-level state dict.
        show_partitioning: If True, show requesters, allocators, evolvers,
            and the request/allocate stores. If False, hide internal
            partitioning and show only the merged biological processes.
    """
    skip = set(ALWAYS_SKIP)
    if not show_partitioning:
        skip.add('allocator')

    viz_cell = {}
    for name, edge in cell.items():
        if not isinstance(edge, dict):
            continue

        if '_type' in edge:
            if any(s in name for s in skip):
                continue
            if not show_partitioning and '_requester' in name:
                continue

            inputs = {}
            for port, wire in edge.get('inputs', {}).items():
                if port.startswith('_flow'):
                    continue
                if port in SKIP_PORTS:
                    continue
                if not show_partitioning and isinstance(wire, list) and wire and wire[0] in ('request', 'allocate'):
                    continue
                if isinstance(wire, list):
                    inputs[port] = wire
                elif isinstance(wire, dict) and '_path' in wire:
                    inputs[port] = wire['_path']

            if show_partitioning:
                clean_name = name.replace('ecoli-', '')
            else:
                clean_name = name.replace('ecoli-', '').replace('_evolver', '')

            viz_cell[clean_name] = {'_type': edge['_type'], 'inputs': inputs}

        elif name == 'unique' and isinstance(edge, dict):
            viz_cell[name] = {k: {} for k in edge.keys()}
        elif name in ('bulk', 'listeners', 'environment'):
            viz_cell[name] = {}
        elif show_partitioning and name in ('request', 'allocate'):
            if isinstance(edge, dict):
                viz_cell[name] = {k: {} for k in edge.keys()}
            else:
                viz_cell[name] = {}

    return viz_cell


def _assign_colors(viz_cell, prefix, show_partitioning=False):
    """Assign colors and groups to nodes based on their names."""
    colors = {}
    groups_dict = {k: [] for k in COLOR_GROUPS}

    for name in viz_cell:
        if '_type' not in viz_cell.get(name, {}):
            continue
        path = prefix + (name,)
        for group_key, (color, matcher) in COLOR_GROUPS.items():
            if group_key == 'allocate' and not show_partitioning:
                continue
            if matcher(name):
                colors[path] = color
                groups_dict[group_key].append(path)
                break

    groups = [g for g in groups_dict.values() if g]
    return colors, groups


def plot_ecoli_bigraph(document, outpath='out/ecoli.pickle', show_partitioning=False):
    """Plot the E. coli bigraph from a migrated document.

    Generates a visualization showing the biological processes and their
    connections to shared state stores (bulk molecules, unique molecules,
    listeners, environment).

    Processes are color-coded by function:
        pink = DNA, blue = RNA, green = protein,
        yellow = metabolism, purple = regulation, gray = listeners,
        salmon = allocators (only when show_partitioning=True)

    Args:
        document: Dict with 'state' key containing the migrated composite state.
        outpath: Base path -- figure is saved next to it as .png and .svg.
        show_partitioning: If True, show requesters, allocators, evolvers,
            and request/allocate stores. If False (default), hide internal
            partitioning and show only the merged biological processes.
    """
    state = document.get('state', document)
    cell = _find_cell(state)
    viz_cell = _build_viz_cell(cell, show_partitioning=show_partitioning)

    viz_state = {'agents': {'0': viz_cell}}
    prefix = ('agents', '0')

    colors, groups = _assign_colors(viz_cell, prefix, show_partitioning=show_partitioning)

    out_dir = os.path.dirname(outpath) or '.'
    basename = os.path.splitext(os.path.basename(outpath))[0]
    if show_partitioning:
        basename += '_partitioned'

    layouts = {
        'TB': {'size': '20,16', 'suffix': ''},
        'LR': {'size': '16,20', 'suffix': '_LR'},
    }

    for layout_dir, layout_opts in layouts.items():
        name = basename + layout_opts['suffix']
        for fmt in ['png', 'svg']:
            plot_bigraph(
                viz_state,
                remove_process_place_edges=True,
                node_groups=groups,
                node_fill_colors=colors,
                size=layout_opts['size'],
                rankdir=layout_dir,
                dpi='200',
                port_labels=False,
                node_label_size='32pt',
                label_margin='0.08',
                out_dir=out_dir,
                filename=name,
                file_format=fmt,
            )
        print(f"Saved bigraph plot to {out_dir}/{name}.png and .svg")
