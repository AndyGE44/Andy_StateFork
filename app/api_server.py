import logging
import numpy as np
import os
import time
import uvicorn

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette import status
from app.kv_store import KVStore

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global in-memory key-value store
kv = KVStore(preload=True)  # Preload with some initial data for testing

ARRAY_SIZE_MB = int(os.getenv("LARGE_ARRAY_MB", "1024"))  # default 1 GB
NUM_FLOATS = (ARRAY_SIZE_MB * 1024 * 1024) // 8  # 8 bytes for double

logger.info(f"Allocating large numpy array of size {ARRAY_SIZE_MB} MB...")
heavy_array = np.ones(NUM_FLOATS, dtype=np.float64)

def log_memory_usage(filepath="/tmp/mem_stats.txt") -> dict:
    """
    Logs current process memory usage (VmSize, VmRSS, VmPeak) to a file.
    """
    stats = {}
    with open("/proc/self/status", "r") as f:
        for line in f:
            if line.startswith("VmSize:") or line.startswith("VmRSS:") or line.startswith("VmPeak:"):
                key, val = line.strip().split(":", 1)
                stats[key] = val.strip()

    with open(filepath, "a") as out:
        out.write(f"[Memory Usage Report - {time.strftime('%Y-%m-%d %H:%M:%S')}]\n")
        for key in ("VmSize", "VmRSS", "VmPeak"):
            out.write(f"{key}: {stats.get(key, 'N/A')}\n")

    return stats


ls = log_memory_usage()
logger.info(f"Allocation complete. Memory usage: {ls}")

app = FastAPI(
    title="StateFork API service",
    description="Our testing API service for Container Stateful-branching Benchmark System",
    version="0.1.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for simplicity
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

"""
I deliberately make every endpoint use the GET method for simplicity and testability.
"""

@app.get("/")
def root():
    """
    Root endpoint to check if the API is running.
    """
    return {"message": "Welcome to the StateFork API!"}

@app.get("/get/{key}", status_code=status.HTTP_200_OK)
def get_value(key: str):
    """
    Retrieve the value for a given key from the KV store.
    """
    value = kv.get(key)
    if value is None:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"key": key, "value": value}


@app.get("/set/{key}/{value}", status_code=status.HTTP_200_OK)
def set_value(key: str, value: str):
    """
    Set a value for a given key in the KV store.
    """
    kv.set(key, value)
    return {"key": key, "value": value}

@app.get("/all", status_code=status.HTTP_200_OK)
def list_all():
    """
    List all key-value pairs in the KV store.
    """
    log_memory_usage()

    all_items = kv.all()
    count = len(all_items)
    if not all_items:
        return {"items": {}, "count": 0}
    return {"items": all_items, "count": count}


if __name__ == "__main__":
    uvicorn.run(
        "app.api_server:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info"
    )