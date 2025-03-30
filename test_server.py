import json
import random
import time
from http.server import HTTPServer, BaseHTTPRequestHandler


class LLMHandler(BaseHTTPRequestHandler):
    def __init__(self, a, b, c):
        super().__init__(a, b, c)

    def do_POST(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

        self.rfile.read(int(self.headers["Content-Length"]))

        content = "Fubuki「Hi Friends!」"
        while content:
            number_translated = random.randint(3, 5)
            print(content[:number_translated], end="", flush=True)
            self.wfile.write(("data: " + json.dumps({
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "content": content[:number_translated],
                            "type": "text"
                        }
                    }
                ]
            }) + "\n\n").encode())
            content = content[number_translated:]
            time.sleep(0.1)

        print()
        self.wfile.write(b'data: {"choices": [{"index": 0, "finish_reason": "stop", "delta": {"content": "", "type": "text"}}]}\n\n')
        self.wfile.write(b'data: [DONE]')


def main():
    HTTPServer(("127.0.0.1", 1234), LLMHandler).serve_forever()


if __name__ == '__main__':
    main()
