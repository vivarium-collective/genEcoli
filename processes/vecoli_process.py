from pathlib import Path

from process_bigraph import Process as PbgProcess, Composite
from vivarium.core.engine import Engine
from ecoli.library.schema import not_a_process

from processes import core
from processes.data_manager import EcoliDataManager


class VEcoliProcess(PbgProcess):
    config_schema = {
        "config_path": "string"
    }

    def initialize(self, config):
        self.simulation = EcoliDataManager.initialize_ecoli(config_path=config["config_path"])
        self.t = 0

    def initial_state(self):
        y_0: dict = self.simulation.ecoli_experiment.state.get_value(condition=not_a_process)["agents"]["0"]
        return {
            "exchange": y_0["environment"]["exchange"],
            "mass": y_0["listeners"]["mass"],
            "t": self.simulation.ecoli_experiment.global_time
        }

    def inputs(self):
        return {"environment": "tree[any]"}

    def outputs(self):
        return {
            "exchange": "tree[integer]",
            "mass": "tree[float]",
            "t": "float"
        }

    def update(self, state, interval):
        engine: Engine = self.simulation.ecoli_experiment
        if engine is None:
            raise RuntimeError(
                "Build the composite by calling build_ecoli() \
                before updating!"
            )

        env_input = state["environment"]
        state_update = {
         "agents": {
             "0": {
                 "environment": env_input
                 }
             }
         }
        engine.state.set_value(state_update)

        self.simulation.update_experiment(interval)
        self.t = engine.global_time

        y_i = engine.state.get_value(condition=not_a_process)["agents"]["0"]

        return {
            "exchange": y_i["environment"]["exchange"],
            "mass": y_i["listeners"]["mass"],
            "t": self.t
        }


core.process_registry.register('vecoli-process', VEcoliProcess)


def test_vecoli_composition() -> None:
    config_path = Path(__file__).parent.parent / "ecoli_configs" / "single_cell.json"
    config = {
        "config_path": str(config_path)
    }
    state = {
        "ecoli_0": {
            "_type": 'process',
            "address": "local:vecoli-process",
            "config": config,
            "inputs": {
                "environment": ["environment_store"]
            },
            "outputs": {
                "exchange": ["exchange_store_0"],
                "mass": ["mass_store_0"],
                "t": ["t_store_0"]  # sanity check
            }
        },
        "ecoli_1": {
            "_type": 'process',
            "address": "local:vecoli-process",
            "config": config,
            "inputs": {
                "environment": ["environment_store"]
            },
            "outputs": {
                "exchange": ["exchange_store_1"],
                "mass": ["mass_store_1"],
                "t": ["t_store_1"]
            }
        },
        "ecoli_2": {
            "_type": 'process',
            "address": "local:vecoli-process",
            "config": config,
            "inputs": {
                "environment": ["environment_store"]
            },
            "outputs": {
                "exchange": ["exchange_store_2"],
                "mass": ["mass_store_2"],
                "t": ["t_store_2"]
            }
        }
    }
    bridge = {
        'outputs': {
            "environment": ["environment_store"],
            "exchange_e0": ["exchange_store_0"],
            "mass_e0": ["mass_store_0"],
            "t_e0": ["t_store_0"],
            "exchange_e1": ["exchange_store_1"],
            "mass_e1": ["mass_store_1"],
            "t_e1": ["t_store_1"],
            "exchange_e2": ["exchange_store_2"],
            "mass_e2": ["mass_store_2"],
            "t_e2": ["t_store_2"],
        }
    }
    composite = Composite(config={"state": state, "bridge": bridge}, core=core)
    composite.save("/Users/alexanderpatrie/sms/genEcoli/artifacts/colony_state.json", state=True)
    composite.save("/Users/alexanderpatrie/sms/genEcoli/artifacts/colony_state_with_schema.json", schema=True, state=True)
    composite.run(2)

    results = composite.read_bridge()
    assert list(results.keys()) == [
        'exchange_e0',
        'mass_e0',
        't_e0',
        'exchange_e1',
        'mass_e1',
        't_e1',
        'exchange_e2',
        'mass_e2',
        't_e2'
    ]


