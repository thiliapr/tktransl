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

        prompt = json.loads(self.rfile.read(int(self.headers["Content-Length"])))["messages"][1]["content"]
        source = prompt.split("根据以上术语表的对应关系和备注，结合历史剧情和上下文，将下面的文本从日文翻译成简体中文：", 1)[1].strip()
        print(source)

        content = "\n".join("Fubuki「Hi Friends!」" for _ in range(source.count("\n") + int(random.random() + 0.9)))
        while content:
            number_translated = random.randint(3, 5)
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
