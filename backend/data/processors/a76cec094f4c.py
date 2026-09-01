import sys, json
def process(payload):
    return {"status": "ok", "summary": "CUSTOM SCRIPT RAN", "doubled": payload.get("amount", 0) * 2, "echo": payload}
if __name__ == "__main__":
    p = json.loads(sys.stdin.read() or "{}")
    print(json.dumps(process(p)))
