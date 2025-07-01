# StateFork: A Lightweight Versioned Container Manager

**StateFork** is a simple, modular snapshotting and benchmarking tool for managing long-running applications in a 
version-controlled and reproducible environment. It supports both container-based (Docker, Podman) and process-based (CRIU) backends, 
enabling users to take snapshots, roll back state, and benchmark key operations across different platforms.

## 🌟 Features

- 🌱 Take and manage snapshots of running apps
- 🔁 Restore to previous snapshots instantly
- 🧪 Benchmark performance of snapshot/restore operations
- 🧩 Works with unmodified apps (FastAPI, Python/C++ scripts, etc.)
- ⚙️ CLI-based interactive interface
- 🧱 Easily extendable backend design with Docker, CRIU, or Podman support

## 🗂 Project Structure
```
StateFork/
  ├── Dockerfile
  ├── README.md
  ├── app/                    # Sample applications
  │   ├── stateful_logger.py   # Sample app 1: Stateful logger (Python)
  │   ├── api_server.py        # Sample app 2: FastAPI server
  │   ├── kv_store.py           # Key-value store for FastAPI server
  │   ├── rdb.cpp               # Sample app 3: Random-access DB (C++)
  │   └── Makefile             # For building the C++ app
  ├── controller/            # Core controller logic
  │   ├── base_env_manager.py
  │   ├── benchmark.py
  │   ├── criu_env_manager.py
  │   ├── docker_env_manager.py
  │   └── ...
  ├── interface/             # Interface entrypoints
  │   └── shell.py             # Interactive CLI interface
  ├── docs/
  ├── logs/
  ├── scripts/
  └── requirements.txt
```

## 🔧 Environment Manager Variants
StateFork implements four concrete environment managers based on different use cases:

| Class Name            | Backend     | Application Lifecycle             | Use Case                                                                                                        |
|-----------------------|-------------|-----------------------------------|-----------------------------------------------------------------------------------------------------------------|
| `DockerBuildManager`  | Docker      | Launches new container from image | Use when you want to build and run an app from scratch using a Dockerfile. Best for controlled environments.    |
| `DockerAttachManager` | Docker      | Attaches to existing container    | Use when your app is already running in Docker and you want to snapshot it without rebuilding.                  |
| `CRIULaunchManager`   | CRIU        | Launches and snapshots a process  | Use for long-running local processes (Python, C++) where the controller manages the lifecycle.                  |
| `CRIUAttachManager`   | CRIU        | Attaches to existing process      | Use when your app is already running locally, and you just want to snapshot/restore via CRIU.                   |
| `PodmanBuildManager`  | Podman+CRIU | Launches new container from image | Use when you want to run an app from a Dockerfile inside Podman with checkpoint/restore support via CRIU.       |
| `PodmanHybridManager` | Podman+CRIU | Attaches to existing container    | 	Use when your app is already running inside Podman and you just want to perform management using this package. |

### 🏭 Factory Method Support
StateFork also provides a unified **Factory Method** to simplify the instantiation of different environment managers. 
Instead of importing backend-specific classes, users can create the appropriate manager by calling a single 
`create_env_manager(method=..., **kwargs)` function. This improves usability, decouples interface logic from 
implementation, and allows easy integration with other components (e.g., CLI, RPC, or agent wrappers). Simply 
specify the backend type (e.g., `"criu_attach"`, `"docker_build"`) along with the required parameters, and the 
factory will handle the rest.
```python
from controller import create_env_manager
manager = create_env_manager(method="criu_attach", target_pid=12345)
```
See the full method table below for supported types and arguments.

| Class Name             | Factory Call Name | Required Arguments                       | Optional Arguments                                              |
|------------------------|-------------------|------------------------------------------|-----------------------------------------------------------------|
| `DockerBuildManager`   | `docker_build`    |                                          | `base_image(str)`, `dockerfile_dir(str)`                        |
| `DockerAttachManager`  | `docker_attach`   | `container_name(str)`, `base_image(str)` |                                                                 |
| `CRIULaunchManager`    | `criu_launch`     |                                          | `work_dir(str)`, `command(List[str])`                           |
| `CRIUAttachManager`    | `criu_attach`     | `target_pid(int)`                        | `work_dir(str)`                                                 |
| `PodmanBuildManager`	  | `podman_build`	   | 	                                        | `container_name(str)`, `dockerfile_dir(str)`, `export_dir(str)` |
| `PodmanHybridManager`	 | `podman_attach`	  | `container_name(str)`                    | `export_dir(str)`                                               |

> 🧠 The system is extensible: you can easily plug in new backends or integrate with agents via RPC/Web APIs.

## 🧪 Benchmarking Support
StateFork automatically logs and benchmarks the performance of:

- Snapshot creation
- Restore operations
- Tree-based version tracking
- Time-based operation history

## 🔧 Requirements
### Python Environment
- Python 3.10+
- Install Python dependencies:
```bash
pip install -r requirements.txt
```

### Docker Method
- Docker must be installed and running.
- Make sure your user has permission to run Docker commands.

### CRIU Method
- Linux kernel compiled with CRIU support.
    - You may use the provided universal AKCS helper `scripts/kconfig.sh` with the `-r` option to generate a compatible kernel config.
- Install `criu` tool from: https://launchpad.net/~criu/+archive/ubuntu/ppa or your system package manager.
- Root or `sudo` privileges are required.

### Podman Method
- CRIU must be installed as above.
- Podman must be installed and running.
- Must use Root or `sudo` privileges to run Podman commands, as [the checkpoints currently work with root containers only](https://podman.io/docs/checkpoint).
- Manually set the OCI runtime in `/usr/share/containers/containers.conf` to use **runc** instead of the default **crun**.


## 🚀 Quick Start

### 1. Run Your Target App

Ensure your application is functional, e.g., for FastAPI:

```bash
uvicorn app.api_server:app --host 127.0.0.1 --port 8000
```

### 2. Launch the Interactive Shell
```bash
(sudo) python3 -m interface.shell --method docker
```

You will enter an interactive CLI:
```
StateFork Container Manager
Commands: snapshot, restore <id>, step, tree, stats, history, exit

StateFork > _
```
See the sample run screenshot below.

### 3. Common Commands (in Interactive Shell)
| Command	      | Description                                              |
|---------------|----------------------------------------------------------|
| snapshot	     | Take a snapshot of the current state                     |
| restore {id}	 | Roll back to a given snapshot ID                         |
| step	         | Snapshot and restore immediately to simulate progression |
| tree	         | Show snapshot tree structure                             |
| stats	        | Show benchmarking results                                |
| history	      | Show operation history                                   |
| exit	         | Clean up and exit the manager                            |

### 📸 Sample Run
![Sample Run Screenshot](./docs/sample_run.png)

---
Want to contribute? File issues or PRs in the GitHub repo!
> For advanced usage (e.g., RPC agent integration), see the `interface/` and `controller/` folders.