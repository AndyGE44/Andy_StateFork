# 🌟 StateFork Controller 

## 🔧 Developer Guide

### Design Overview
1. Template Method Pattern
  - Base manager classes (e.g., `EnvironmentManager` and its subclasses)
  - The base class defines the overall workflow, while subclasses implement only the core logic steps. This ensures consistent process flow and reduces code duplication.
2. Factory Method Pattern
  - `create_env_manager` function in `__init__.py`
  - Centralizes the creation of different environment manager instances. Developers can register new manager types and instantiate them through a single interface, improving extensibility.
3. Strategy Pattern
  - Manager classes and their use of `Calculator` components (e.g., for benchmarking)
  - Allows managers to dynamically select and attach different `Calculator` strategies for benchmarking. This enables flexible and interchangeable calculation logic without modifying the manager code.
4. Iterator Pattern
  - Benchmarking components (e.g., `BenchmarkStats`)
  - Used when iterating over a collection of attached `Calculators` to perform operations. This pattern provides a uniform way to access and process multiple strategies or components.

These patterns help keep the codebase modular, extensible, and easy to maintain for future development.


## 🧱 User Guide

### ⚙️ Env Manager
All the controller classes are subclasses of `EnvironmentManager`, which provides a unified interface for managing
environments, snapshots, and containers.  

The usage of these controllers is well-documented in the `EnvironmentManager` base class, utilizing IDE-supported docstrings.
They are:
- `.snapshot()`: Create a snapshot of the current environment and return a unique identifier for the snapshot.
- `.restore(snapshot_id: str)`: Restore the environment to a specific snapshot and returns True if successful.
- `.create_env_from_snapshot(snapshot_id: str)`: Create a container from a snapshot and return the name for the container.
- `.cleanup()`: Clean up all containers and snapshots created by the controller instance.

### 🧩 Controller Helper
All `EnvironmentManager` subclass instance also provides a series of helper methods to assist with common tasks.

The usage of these controllers is well-documented in the `EnvironmentManager` base class, utilizing IDE-supported docstrings.
They are:
- attribute `.backend`: Get the name of the backend used by the controller instance.
- attribute `.current_snapshot`: Get the current snapshot ID of the controller instance.
- `.list_snapshots()`: List all snapshots created by the controller instance.
- `.print_snapshot_tree()`: Print a tree view of all snapshots created by the controller instance. [ Non-thread-safe ]

### 🧪 Benchmark
You can enter the benchmark interface through the `.stats` attribute of any `EnvironmentManager` subclass instance.

#### Programmatic Usage
Use the `get_all_statistics()` method to retrieve all statistics, which returns a `BenchmarkResult` object containing 
the time and size statistics for various operations. A sample output is shown below:
```python
BenchmarkResult(
    time={
        'snapshot': Statistics(
            count=6, total=0.738, mean=0.123, median=0.123, min=0.123, max=0.123, unit='seconds'
        ),
        'container': Statistics(
            count=5, total=0.615, mean=0.123, median=0.123, min=0.123, max=0.123, unit='seconds'
        ),
        'restore': Statistics(
            count=2, total=0.246, mean=0.123, median=0.123, min=0.123, max=0.123, unit='seconds'
        )
    },
    size={
        'FileSizeCalculator #1': Statistics(
            count=7, total=2048, mean=1024, median=1024, min=512, max=1536, unit='bytes'
        ),
        'ImageCalculator #1': Statistics(
            count=3, total=2048, mean=1024, median=1024, min=512, max=1536, unit='bytes'
        )
    }
)
```

#### Formatted String Usage
We also provide many helper functions to format the statistics into human-readable strings. 

For example, the methods of `print_stats()`, `print_history()`, and `print_size_details()` can be used to retrieve 
formatted strings that summarize different aspects of the statistics at different levels of granularity. 
