import sys, json
def process(payload):
    return {"status": "ok", "summary": "ROUTED VIA CUSTOM SCRIPT", "echo": payload}
if __name__ == "__main__":
    p = json.loads(sys.stdin.read() or "{}")
    print(json.dumps(process(p)))
