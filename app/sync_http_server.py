from http.server import HTTPServer, BaseHTTPRequestHandler
import json

"""
A temporary synchronous HTTP server that responds to GET requests to test the CRIU functionalities.
"""

IN_MEMORY_COUNTER = 0

class MyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            global IN_MEMORY_COUNTER
            response = {"message": "Hello from sync HTTP server!", "counter": IN_MEMORY_COUNTER}
            IN_MEMORY_COUNTER += 1
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

def run(host="127.0.0.1", port=8000):
    server = HTTPServer((host, port), MyHandler)
    print(f"Running sync HTTP server on http://{host}:{port}")
    server.serve_forever()

if __name__ == "__main__":
    run()
