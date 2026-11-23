import json, sys, os
from http.server import BaseHTTPRequestHandler, HTTPServer

LOGPATH = os.environ.get("MOCKLOG", "mockapi.log")
MODE = os.environ.get("MOCKMODE", "tool")  # text|tool
TOOLNAME = os.environ.get("MOCKTOOL", "Read")
TOOLARG = os.environ.get("MOCKARG", '{"file_path":"/proc/self/environ"}')

def log(obj):
    with open(LOGPATH, "a") as fh:
        fh.write(json.dumps(obj)[:200000] + "\n")

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def _read(self):
        n = int(self.headers.get("content-length") or 0)
        return self.rfile.read(n) if n else b""
    def do_GET(self):
        log({"path": self.path, "method": "GET"})
        body = json.dumps({"data": []}).encode()
        self.send_response(200); self.send_header("content-type","application/json"); self.send_header("content-length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        raw = self._read()
        try: req = json.loads(raw)
        except Exception: req = {"_raw": raw.decode("utf8","replace")[:2000]}
        log({"path": self.path, "method": "POST", "body": req})
        has_tool_result = False
        try:
            for m in req.get("messages", []):
                c = m.get("content")
                if isinstance(c, list) and any(isinstance(x,dict) and x.get("type")=="tool_result" for x in c):
                    has_tool_result = True
        except Exception: pass
        stream = bool(req.get("stream", True))
        model = req.get("model","claude-sonnet-4-5")
        usage = {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
        if has_tool_result or MODE == "text":
            blocks = [{"type":"text","text":"final"}]
            stop = "end_turn"
        else:
            blocks = [{"type":"tool_use","id":"toolu_1","name":TOOLNAME,"input":json.loads(TOOLARG)}]
            stop = "tool_use"
        if not stream:
            resp = {"id":"msg_1","type":"message","role":"assistant","model":model,"content":blocks,"stop_reason":stop,"stop_sequence":None,"usage":usage}
            body=json.dumps(resp).encode(); self.send_response(200); self.send_header("content-type","application/json"); self.send_header("content-length",str(len(body))); self.end_headers(); self.wfile.write(body); return
        self.send_response(200)
        self.send_header("content-type","text/event-stream"); self.send_header("cache-control","no-cache"); self.send_header("connection","close"); self.end_headers()
        def ev(name, data):
            self.wfile.write(f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()); self.wfile.flush()
        ev("message_start", {"type":"message_start","message":{"id":"msg_1","type":"message","role":"assistant","model":model,"content":[],"stop_reason":None,"stop_sequence":None,"usage":usage}})
        for i,b in enumerate(blocks):
            if b["type"]=="text":
                ev("content_block_start", {"type":"content_block_start","index":i,"content_block":{"type":"text","text":""}})
                ev("content_block_delta", {"type":"content_block_delta","index":i,"delta":{"type":"text_delta","text":b["text"]}})
            else:
                ev("content_block_start", {"type":"content_block_start","index":i,"content_block":{"type":"tool_use","id":b["id"],"name":b["name"],"input":{}}})
                ev("content_block_delta", {"type":"content_block_delta","index":i,"delta":{"type":"input_json_delta","partial_json":json.dumps(b["input"])}})
            ev("content_block_stop", {"type":"content_block_stop","index":i})
        ev("message_delta", {"type":"message_delta","delta":{"stop_reason":stop,"stop_sequence":None},"usage":{"output_tokens":5}})
        ev("message_stop", {"type":"message_stop"})
        self.close_connection = True
        try: self.wfile.flush()
        except Exception: pass

if __name__ == "__main__":
    port=int(sys.argv[1]) if len(sys.argv)>1 else 9311
    HTTPServer(("127.0.0.1",port),H).serve_forever()
