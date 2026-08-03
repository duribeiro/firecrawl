#!/usr/bin/env python3
"""
Benchmark CEGO: Firecrawl /extract — 5 famílias DISTINTAS de LLMs open-source.
Mesmo site, mesmo schema, arquiteturas diferentes.
Modelos: kimi-k2.6, deepseek-v4-flash, qwen3-next, nemotron-3-super, glm-5.1
"""

import json, time, subprocess, os

FC_DIR = os.path.expanduser("~/firecrawl")
API_URL = "http://localhost:3002"

# 5 famílias distintas (arquiteturas diferentes)
MODELS = [
    ("kimi-k2.6",     "kimi-k2.6:cloud",         "Moonshot AI — MoE 32B"),
    ("deepseek-v4",   "deepseek-v4-flash:cloud", "DeepSeek — flash distill"),
    ("minimax-m2",    "minimax-m2:cloud",        "MiniMax — MoE chinesa"),
    ("nemotron-3",    "nemotron-3-super:cloud",  "NVIDIA — 72B dense"),
    ("glm-5.1",       "glm-5.1:cloud",           "Zhipu AI — arquitetura própria"),
]

TESTS = [
    {
        "name": "simple_title",
        "url": "https://example.com",
        "prompt": "What is the title of this page? Return only the title.",
        "schema": {
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"]
        }
    },
    {
        "name": "pricing_plans",
        "url": "https://firecrawl.dev/pricing",
        "prompt": "List all pricing plans with name, price, and features.",
        "schema": {
            "type": "object",
            "properties": {
                "pricing_plans": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "plan_name": {"type": "string"},
                            "price": {"type": "string"},
                            "features": {"type": "array", "items": {"type": "string"}}
                        },
                        "required": ["plan_name", "price", "features"]
                    }
                }
            },
            "required": ["pricing_plans"]
        }
    },
]


def shell(cmd, cwd=None, to=60):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd, timeout=to)
    return r.stdout, r.stderr, r.returncode


def wait_api(max_wait=60):
    print("     → Aguardando API subir...", end="", flush=True)
    for i in range(max_wait):
        out, _, _ = shell(f"curl -s -o /dev/null -w '%{{http_code}}' {API_URL}/v1/scrape -X POST -H 'Content-Type: application/json' -d '{{\"url\":\"https://example.com\"}}' 2>/dev/null || echo '000'")
        if out.strip() in ("200", "400", "401"):
            print(f" OK ({i}s)")
            time.sleep(2)
            return True
        print(".", end="", flush=True)
        time.sleep(1)
    print(" TIMEOUT")
    return False


def restart_api():
    print("   ↻ Restart container...")
    shell("docker compose restart api", cwd=FC_DIR, to=60)
    return wait_api()


def set_model(name):
    env_path = os.path.join(FC_DIR, ".env")
    with open(env_path) as f:
        lines = f.readlines()
    with open(env_path, "w") as f:
        for line in lines:
            if line.startswith("MODEL_NAME="):
                f.write(f"MODEL_NAME={name}\n")
            else:
                f.write(line)


def test_extract(t):
    payload = json.dumps({"urls": [t["url"]], "prompt": t["prompt"], "schema": t["schema"]})
    cmd = [
        "curl", "-s", "-w", "\\nHTTP:%{http_code}\\nTIME:%{time_total}\\n",
        "-H", "Content-Type: application/json",
        "-d", payload,
        f"{API_URL}/v1/extract"
    ]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "dur": 300, "http": 0, "data": None, "raw": ""}

    dur = round(time.time() - t0, 1)
    out = r.stdout
    http, body = 0, out
    for line in out.splitlines():
        if line.startswith("HTTP:"):
            http = int(line.split(":",1)[1])
            body = body.replace(line+"\n", "").replace(line, "")
        if line.startswith("TIME:"):
            body = body.replace(line+"\n", "").replace(line, "")

    parsed = None
    try:
        parsed = json.loads(body)
    except: pass

    status = "OK" if (http == 200 and parsed and parsed.get("success")) else "FAIL"
    return {"status": status, "dur": dur, "http": http,
            "data": parsed.get("data") if parsed else None, "raw": body[:600]}


def benchmark():
    results = []
    # Guardar modelo original
    orig = None
    with open(os.path.join(FC_DIR, ".env")) as f:
        for line in f:
            if line.startswith("MODEL_NAME="):
                orig = line.split("=",1)[1].strip()
                break

    print("=" * 60)
    print("BENCHMARK CEGO — 5 Famílias DISTINTAS no Firecrawl /extract")
    print("=" * 60)

    for label, model, desc in MODELS:
        print(f"\n▶ {label} ({model})")
        print(f"   {desc}")
        set_model(model)
        if not restart_api():
            for t in TESTS:
                results.append({"model": label, "test": t["name"], "status": "API_DOWN", "dur": 0, "data": None})
            continue

        for t in TESTS:
            print(f"   • {t['name']}...", end=" ", flush=True)
            res = test_extract(t)
            results.append({"model": label, "test": t["name"], **res})
            print(f"{res['status']} | {res['dur']}s | HTTP {res['http']}")
            if res["data"]:
                print(f"     → {str(res['data'])[:120]}")

    # Restaurar
    print(f"\n↻ Restaurando: {orig}")
    set_model(orig)
    restart_api()

    # Relatório
    print("\n" + "=" * 60)
    print("📊 RESULTADO POR TESTE")
    print("=" * 60)
    for t in TESTS:
        print(f"\n📋 {t['name']}")
        rows = [r for r in results if r["test"] == t["name"]]
        print(f"{'Modelo':<15} {'Status':<8} {'Tempo':<8} {'Preview'}")
        print("-" * 70)
        for r in rows:
            preview = str(r.get("data", "—"))[:50]
            print(f"{r['model']:<15} {r['status']:<8} {str(r['dur'])+'s':<8} {preview}")

    # Score
    print("\n🏆 SCORE FINAL (max 2 por modelo)")
    scores = {}
    for r in results:
        scores[r["model"]] = scores.get(r["model"], 0) + (1 if r["status"] == "OK" else 0)
    for m, s in sorted(scores.items(), key=lambda x: -x[1]):
        bar = "█" * s + "░" * (2 - s)
        print(f"   {m:<15} {bar} {s}/2")

    # Ranking por velocidade
    print("\n⏱️  RANKING DE VELOCIDADE (média dos testes OK)")
    avg_dur = {}
    for m in set(r["model"] for r in results):
        ok = [r["dur"] for r in results if r["model"] == m and r["status"] == "OK"]
        if ok:
            avg_dur[m] = round(sum(ok)/len(ok), 1)
    for m, d in sorted(avg_dur.items(), key=lambda x: x[1]):
        print(f"   {m:<15} {d}s")

    out = "/tmp/fc_benchmark.json"
    with open(out, "w") as f:
        json.dump({"original": orig, "results": results}, f, indent=2, default=str)
    print(f"\n💾 Detalhes: {out}")


if __name__ == "__main__":
    benchmark()
