import marimo

__generated_with = "0.18.1"
app = marimo.App(width="full")


@app.cell
def _():
    from pathlib import Path

    from process_bigraph import Process as PbgProcess, Composite

    from processes.vecoli_process import core 
    return Composite, Path, core


@app.cell
def _(Composite, Path, core):
    config_path = Path(__file__).parent.parent / "ecoli_configs" / "single_cell.json"
    config = {
        "config_path": str(config_path)
    }
    state = {
        "ecoli0": {
            "_type": 'process',
            "address": "local:vecoli-process",
            "config": config,
            "inputs": {
                "environment": ["environment_store"]
            },
            "outputs": {
                "environment": ["environment_store"],
                "mass": ["mass_store_0"]
            }
        },
        "ecoli1": {
            "_type": 'process',
            "address": "local:vecoli-process",
            "config": config,
            "inputs": {
                "environment": ["environment_store"]
            },
            "outputs": {
                "environment": ["environment_store"],
                "mass": ["mass_store_1"]
            }
        },
        "ecoli2": {
            "_type": 'process',
            "address": "local:vecoli-process",
            "config": config,
            "inputs": {
                "environment": ["environment_store"]
            },
            "outputs": {
                "environment": ["environment_store"],
                "mass": ["mass_store_2"]
            }
        }
    }
    bridge = {
        'outputs': {
            "environment": ["environment_store"],
            "mass_0": ["mass_store_0"],
            "mass_1": ["mass_store_1"],
            "mass_2": ["mass_store_2"]
        }
    }
    composite = Composite(config={"state": state, "bridge": bridge}, core=core)
    # composite.run(2)
    # results = composite.read_bridge()

    def run_composition(composite, results: dict, i: int):
        composite.run(1)
        results[str(i)] = composite.read_bridge()

    results = {}
    for i in range(22):
        run_composition(composite, results, i)
    return


app._unparsable_cell(
    r"""
    |import marimo as mo 

    mo.json(results)
    """,
    name="_"
)


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
