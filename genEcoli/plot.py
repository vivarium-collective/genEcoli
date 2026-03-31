"""Visualization functions for the E. coli composite."""

import os
import base64
from datetime import datetime

import numpy as np
import matplotlib.pyplot as plt
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


# ---------------------------------------------------------------------------
# Mass fraction summary plot
# ---------------------------------------------------------------------------

MASS_COMPONENTS = {
    'Protein': 'protein_mass',
    'tRNA': 'tRna_mass',
    'rRNA': 'rRna_mass',
    'mRNA': 'mRna_mass',
    'DNA': 'dna_mass',
    'Small Mol': 'smallMolecule_mass',
    'Dry Mass': 'dry_mass',
}

MASS_COLORS = [
    '#e41a1c', '#377eb8', '#4daf4a', '#984ea3',
    '#ff7f00', '#ffff33', '#a65628',
]


def emitter_to_mass_timeseries(emitter):
    """Convert a RAMEmitter's history to mass timeseries arrays.

    Args:
        emitter: A RAMEmitter instance (from EcoliComposite.emitter).

    Returns:
        dict with 'time' array and arrays for each mass component.
    """
    history = emitter.history
    result = {'time': np.array([s.get('global_time', 0.0) for s in history])}
    for label, key in MASS_COMPONENTS.items():
        result[label] = np.array([s.get(key, 0.0) for s in history])
    return result


def v1_query_to_mass_timeseries(timeseries):
    """Convert v1 sim.query() output to mass timeseries arrays.

    Handles the raw format {time: {path: value}} returned by query().
    """
    times = sorted(t for t in timeseries.keys() if isinstance(t, (int, float)))
    result = {'time': np.array(times)}
    for label, key in MASS_COMPONENTS.items():
        values = []
        for t in times:
            snapshot = timeseries[t]
            mass = snapshot.get('listeners', {}).get('mass', {})
            values.append(mass.get(key, 0.0))
        result[label] = np.array(values)
    return result


def plot_mass_fractions(datasets, outpath='out/mass_fraction_summary.png'):
    """Plot mass fraction summary comparing one or more simulation runs.

    Reproduces the vEcoli mass_fraction_summary analysis: shows biomass
    component fold-changes over time, normalized to t=0.

    Args:
        datasets: Dict of {label: timeseries} where each timeseries has
            'time' and mass component arrays (from history_to_mass_timeseries
            or v1_query_to_mass_timeseries).
        outpath: Path for the output PNG.
    """
    n_datasets = len(datasets)
    fig, axes = plt.subplots(1, n_datasets, figsize=(8 * n_datasets, 6),
                             squeeze=False)

    for col, (ds_label, ts) in enumerate(datasets.items()):
        ax = axes[0, col]
        time_min = (ts['time'] - ts['time'][0]) / 60.0

        for i, (label, key) in enumerate(MASS_COMPONENTS.items()):
            values = ts.get(label)
            if values is None or len(values) == 0 or values[0] == 0:
                continue
            fold_change = values / values[0]
            fraction = np.mean(values / ts['Dry Mass']) if 'Dry Mass' in ts else 0
            ax.plot(time_min, fold_change,
                    color=MASS_COLORS[i % len(MASS_COLORS)],
                    label=f'{label} ({fraction:.3f})')

        ax.set_xlabel('Time (min)')
        ax.set_ylabel('Mass (normalized to t=0)')
        ax.set_title(ds_label)
        ax.legend(fontsize=8)

    fig.suptitle('Biomass components (avg fraction of dry mass in parentheses)',
                 fontsize=12)
    fig.tight_layout()

    os.makedirs(os.path.dirname(outpath) or '.', exist_ok=True)
    fig.savefig(outpath, dpi=200)
    plt.close(fig)
    print(f"Saved mass fraction plot to {outpath}")


# ---------------------------------------------------------------------------
# HTML comparison report
# ---------------------------------------------------------------------------

def _img_to_base64(path):
    """Read an image file and return a base64-encoded data URI."""
    if not os.path.exists(path):
        return ''
    with open(path, 'rb') as f:
        data = base64.b64encode(f.read()).decode('utf-8')
    ext = os.path.splitext(path)[1].lstrip('.')
    return f'data:image/{ext};base64,{data}'


def generate_comparison_report(
    v1_mass,
    v2_mass,
    v1_runtime,
    v2_runtime,
    v1_changed,
    v2_changed,
    both_changed,
    bulk_corr,
    duration,
    outdir='out',
):
    """Generate an HTML report comparing v1 and v2 simulation results.

    Args:
        v1_mass, v2_mass: Mass timeseries dicts (from emitter/query converters).
        v1_runtime, v2_runtime: Wall-clock seconds for each run.
        v1_changed, v2_changed: Number of bulk molecules that changed.
        both_changed: Number changed in both.
        bulk_corr: Pearson correlation of shared bulk deltas.
        duration: Simulated time in seconds.
        outdir: Output directory for the report and images.
    """
    # --- Build component comparison table ---
    v1_times = set(np.round(v1_mass['time'], 2))
    v2_times = set(np.round(v2_mass['time'], 2))
    common_times = sorted(v1_times & v2_times)

    rows = []
    if len(common_times) >= 2:
        v1_idx = [i for i, t in enumerate(v1_mass['time']) if round(t, 2) in set(common_times)]
        v2_idx = [i for i, t in enumerate(v2_mass['time']) if round(t, 2) in set(common_times)]

        for label in MASS_COMPONENTS:
            v1_vals = v1_mass[label][v1_idx]
            v2_vals = v2_mass[label][v2_idx]
            n = min(len(v1_vals), len(v2_vals))
            v1_vals, v2_vals = v1_vals[:n], v2_vals[:n]

            v1_final = v1_vals[-1] if len(v1_vals) > 0 else 0
            v2_final = v2_vals[-1] if len(v2_vals) > 0 else 0
            diff = v2_final - v1_final
            pct = 100 * diff / v1_final if v1_final != 0 else 0

            if n >= 2 and np.std(v1_vals) > 0 and np.std(v2_vals) > 0:
                corr = np.corrcoef(v1_vals, v2_vals)[0, 1]
            else:
                corr = float('nan')

            rows.append((label, v1_final, v2_final, diff, pct, corr))

    table_html = ''
    for label, v1f, v2f, diff, pct, corr in rows:
        color = '#e8f5e9' if abs(pct) < 1 else ('#fff3e0' if abs(pct) < 5 else '#ffebee')
        corr_str = f'{corr:.4f}' if not np.isnan(corr) else 'N/A'
        table_html += f'''<tr style="background:{color}">
            <td>{label}</td><td>{v1f:.2f}</td><td>{v2f:.2f}</td>
            <td>{diff:+.2f}</td><td>{pct:+.2f}%</td><td>{corr_str}</td></tr>\n'''

    # --- Embed images ---
    mass_img = _img_to_base64(os.path.join(outdir, 'mass_fraction_summary.png'))
    bigraph_img = _img_to_base64(os.path.join(outdir, 'ecoli_LR.png'))
    bigraph_part_img = _img_to_base64(os.path.join(outdir, 'ecoli_partitioned_LR.png'))

    html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>genEcoli: v1 vs v2 Comparison Report</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
         max-width: 1200px; margin: 0 auto; padding: 20px; color: #333; }}
  h1 {{ border-bottom: 2px solid #2196F3; padding-bottom: 10px; }}
  h2 {{ color: #1565C0; margin-top: 40px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: right; }}
  th {{ background: #1565C0; color: white; }}
  td:first-child, th:first-child {{ text-align: left; }}
  .summary {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; margin: 20px 0; }}
  .card {{ background: #f5f5f5; border-radius: 8px; padding: 20px; text-align: center; }}
  .card .value {{ font-size: 2em; font-weight: bold; color: #1565C0; }}
  .card .label {{ color: #666; margin-top: 5px; }}
  img {{ max-width: 100%; border: 1px solid #ddd; border-radius: 4px; margin: 10px 0; }}
  .pass {{ color: #2e7d32; font-weight: bold; }}
  .warn {{ color: #e65100; font-weight: bold; }}
  .timestamp {{ color: #999; font-size: 0.9em; }}
</style></head><body>

<h1>genEcoli: v1 vs v2 Comparison Report</h1>
<p class="timestamp">Generated {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | Duration: {duration:.0f}s simulated</p>

<h2>Summary</h2>
<div class="summary">
  <div class="card">
    <div class="value">{bulk_corr:.4f}</div>
    <div class="label">Bulk delta correlation</div>
  </div>
  <div class="card">
    <div class="value">{v2_runtime:.2f}s</div>
    <div class="label">v2 runtime ({v2_runtime/v1_runtime:.1f}x vs v1 {v1_runtime:.2f}s)</div>
  </div>
  <div class="card">
    <div class="value">{both_changed}</div>
    <div class="label">Molecules changed in both (v1: {v1_changed}, v2: {v2_changed})</div>
  </div>
</div>

<h2>Mass Fraction Timeseries</h2>
<img src="{mass_img}" alt="Mass fraction comparison">

<h2>Component Comparison</h2>
<p>Final values after {duration:.0f}s. Color: <span style="background:#e8f5e9;padding:2px 6px">{'<'}1%</span>
<span style="background:#fff3e0;padding:2px 6px">1-5%</span>
<span style="background:#ffebee;padding:2px 6px">{'>'}5%</span> difference.</p>
<table>
<tr><th>Component</th><th>v1 final (fg)</th><th>v2 final (fg)</th>
<th>Difference</th><th>% Diff</th><th>Correlation</th></tr>
{table_html}
</table>

<h2>Bigraph Visualization (v2)</h2>
<h3>Simplified</h3>
<img src="{bigraph_img}" alt="E. coli bigraph (simplified)">
<h3>With Partitioning (Requesters / Allocators / Evolvers)</h3>
<img src="{bigraph_part_img}" alt="E. coli bigraph (partitioned)">

</body></html>'''

    report_path = os.path.join(outdir, 'comparison_report.html')
    os.makedirs(outdir, exist_ok=True)
    with open(report_path, 'w') as f:
        f.write(html)
    print(f"Saved comparison report to {report_path}")
