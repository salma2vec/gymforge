"""gymforge: reproducible RL environment generation for agent training.

Quick start::

    from gymforge.core import TaskSpec
    from gymforge.envs import BashEnvironment

    task = TaskSpec(
        name="count_errors",
        description="Count lines containing 'ERROR' in logs.txt",
        domain="terminal",
        difficulty=0.2,
        success_criteria={"expected_output": "3"},
        scaffolding={
            "files": {
                "logs.txt": "INFO: ok\\nERROR: fail\\nERROR: bad\\nINFO: ok\\nERROR: crash\\n"
            }
        },
    )

    env = BashEnvironment(task)
    obs = env.reset()
    obs, reward, done, info = env.step("grep -c ERROR logs.txt")
    env.close()
"""

from gymforge.core import (
    BaseEnvironment,
    TaskSpec,
    EpisodeResult,
    EpisodeTrace,
    Step,
    registry,
    register,
    make,
)
from gymforge.envs import (
    BashEnvironment,
    FileSystemEnvironment,
    EditorEnvironment,
    PipelineEnvironment,
)
from gymforge.generation import TaskGenerator
from gymforge.evaluation import Evaluator

__version__ = "0.1.0"

__all__ = [
    # core
    "BaseEnvironment",
    "TaskSpec",
    "EpisodeResult",
    "EpisodeTrace",
    "Step",
    "registry",
    "register",
    "make",
    # envs
    "BashEnvironment",
    "FileSystemEnvironment",
    "EditorEnvironment",
    "PipelineEnvironment",
    # generation
    "TaskGenerator",
    # evaluation
    "Evaluator",
    "__version__",
]

# Register built-in environments in the global registry
register("bash", BashEnvironment, version="v1")
register("filesystem", FileSystemEnvironment, version="v1")
register("editor", EditorEnvironment, version="v1")
register("pipeline", PipelineEnvironment, version="v1")
