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

    def inputs(self):
        return {"environment": "tree[any]"}

    def outputs(self):
        return {
            # "exchange": "tree[integer]",
            "environment": "tree[any]",
            "mass": "tree[float]"
        }

    def update(self, state, interval):
        """
        update(state, interval) => (
            1. env_input = state['environment']
            2. state_update = {
                "agents": {
                    "0": {
                        "environment": env_input
                        }
                    }
                }
            3. self.sim.ecoli_experiment.state.set_value(state_update)  # set/update the sim state for THAT cell based on the incoming env
            4. self.sim.ecoli_experiment.state.update_experiment(interval)  # increment the simulation for THAT cell based on the updated sim state
            5. y_i = self.sim.ecoli_experiment.state.get_value(condition=not_a_process)["agents"]["0"]
            6. return {  #
                # "exchange": y_i["environment"]["exchange"],
                "environment": y_i["environment"],
                "mass": y_i["listeners"]["mass"]
            }
        )
        """
        engine: Engine = self.simulation.ecoli_experiment
        if engine is None:
            raise RuntimeError(
                "Build the composite by calling build_ecoli() \
                before updating!"
            )

        # set/update the sim state for THAT cell based on the incoming env
        env_input = state["environment"]
        state_update = {
         "agents": {
             "0": {
                 "environment": env_input
                 }
             }
         }
        # self.simulation.ecoli_experiment.state.set_value(state_update)
        engine.state.set_value(state_update)

        # increment the simulation for THAT(this) cell based on the updated sim state
        self.simulation.update_experiment(interval)

        # read the appropriate data to output ports
        # y_i = self.simulation.ecoli_experiment.state.get_value(condition=not_a_process)["agents"]["0"]
        y_i = engine.state.get_value(condition=not_a_process)["agents"]["0"]
        return {  #
            # "exchange": y_i["environment"]["exchange"],
            "environment": y_i["environment"],
            "mass": y_i["listeners"]["mass"]
        }


core.process_registry.register('vecoli-process', VEcoliProcess)


def test_vecoli_composition() -> None:
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
                "environment": ["env0"],
            },
            "outputs": {
                "environment": ["env0"],
                "mass": ["mass0"]
            }
        },
        "ecoli1": {
            "_type": 'process',
            "address": "local:vecoli-process",
            "config": config,
            "inputs": {
                "environment": ["env1"]
            },
            "outputs": {
                "environment": ["env1"],
                "mass": ["mass1"]
            }
        }
    }
    bridge = {
        'outputs': {
            "environment0": ["env0"],
            "environment1": ["env1"],
            "mass0": ["mass0"],
            "mass1": ["mass1"]
        }
    }
    composite = Composite(config={"state": state, "bridge": bridge}, core=core)

    composite.run(2)

    results = composite.read_bridge()
    print(results)

