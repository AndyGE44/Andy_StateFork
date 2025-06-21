import requests
import time
from itertools import cycle, islice

from controller import create_env_manager

"""
Temporary benchmark script to measure HTTP response performance of local apps.
"""

# Endpoints to test
URLS = [
    "http://127.0.0.1:8000",
    "http://127.0.0.1:8000/all",
    "http://127.0.0.1:8000/get/key1",
    "http://127.0.0.1:8000/get/key2",
    "http://127.0.0.1:8000/set/key1/new_value1",
    "http://127.0.0.1:8000/set/key1/new_new_value1",
    "http://127.0.0.1:8000/set/alex/xu",
]

def request_url(url: str) -> bool:
    """
    Send a GET request to the specified URL and print the response status.
    """
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return True
        else:
            return False
    except requests.RequestException as e:
        print(f"Request failed for {url}: {e}")
        return False

def test_all_requests(iteration: int, step_everytime: bool) -> None:
    # Create a CRIU environment manager for launching the app
    env = create_env_manager("criu_launch")
    time.sleep(5)

    # Statistics
    first_10_logs: list[int] = []
    success_count = 0

    # Core logic for testing requests
    overall_start_time = time.time()
    for i, url in enumerate(islice(cycle(URLS), iteration)):
        if i < 10:
            temp_start_time = time.time()
            if request_url(url):
                temp_end_time = time.time()
                first_10_logs.append(int((temp_end_time - temp_start_time) * 1000))
                success_count += 1
            else:
                first_10_logs.append(-1)
        else:
            if request_url(url):
                success_count += 1

        if step_everytime:
            sid = env.snapshot()
            container = env.create_env_from_snapshot(sid)
            if container is None:
                env.cleanup()
                raise RuntimeError(f"Container creation failed after request {i+1}")

    overall_end_time = time.time()

    elapsed_ms = (overall_end_time - overall_start_time) * 1000
    env.cleanup()

    print(f"Successful responses: {success_count}/{iteration}")
    print(f"Total time: {elapsed_ms:.3f} ms")
    for i, log in enumerate(first_10_logs):
        if log == -1:
            print(f"[{i}] Request failed")
        else:
            print(f"[{i}] Request took {log} ms")


if __name__ == "__main__":
    print("Testing all requests with 100 iterations and NO step every time...")
    test_all_requests(iteration=100, step_everytime=False)

    print("Testing all requests with 100 iterations and STEP every time...")
    test_all_requests(iteration=100, step_everytime=True)