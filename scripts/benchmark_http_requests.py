import requests
import time
from itertools import cycle, islice

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

NUM_REQUESTS = 100

def main():
    success_count = 0
    start_time = time.time()

    # Cycle through URLs until NUM_REQUESTS
    for i, url in enumerate(islice(cycle(URLS), NUM_REQUESTS)):
        try:
            response = requests.get(url)
            if response.status_code == 200:
                success_count += 1
            else:
                print(f"[{i}] {url} -> Unexpected status: {response.status_code}")
        except requests.RequestException as e:
            print(f"[{i}] {url} -> Request failed: {e}")

    end_time = time.time()
    elapsed_ms = (end_time - start_time) * 1000

    print(f"Successful responses: {success_count}/{NUM_REQUESTS}")
    print(f"Total time: {elapsed_ms:.3f} ms")

if __name__ == "__main__":
    main()
