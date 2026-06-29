# Disaster Recovery Playbooks

## Playbook 1: LLM Server Crash

**Symptoms**: `ultrawhale generate` fails with `LLM server not reachable`. `ultrawhale status` shows warning.

**Severity**: Critical — generation stops entirely.

**Check**
```bash
# 1. Is the process alive?
pgrep -f llama-server

# 2. Check the log file for the crash reason
tail -50 llm-server.log

# 3. Check resource pressure
free -h        # Linux
vm_stat        # macOS
```

**Recover**
```bash
# 1. Force-kill any hung process
bash llm-server.sh stop
pkill -9 -f llama-server 2>/dev/null || true

# 2. Verify the model file exists and is not corrupted
ls -lh /opt/homebrew/bin/llama-server
# Expected: ~60MB executable

# 3. Restart
bash llm-server.sh start

# 4. Verify health
sleep 5
curl -sf http://localhost:8080/v1/models | head -1
```

**Root cause investigation**
- Out of memory (check `dmesg | tail` or macOS Console)
- Model file corruption (run `sha256sum -c model.sha256`)
- Port conflict (`lsof -i :8080`)

**Prevention**
- Set up `systemd` auto-restart or launchd `KeepAlive`
- Add `restart: unless-stopped` to Docker Compose
- Monitor memory: `ULTRAWHALE_MAX_WORKERS=4` on constrained hosts

---

## Playbook 2: Disk Full / No Space

**Symptoms**: Upload fails with disk errors. Worker logs show `OSError: [Errno 28] No space left on device`.

**Severity**: Critical — data loss risk if writer thread dies mid-write.

**Check**
```bash
# 1. Which partition is full?
df -h .

# 2. Find largest dogfeed files
du -sh ./*.jsonl 2>/dev/null | sort -rh | head -10
du -sh dogfeed_parallel/ 2>/dev/null

# 3. Check log sizes
du -sh /tmp/worker*.log 2>/dev/null | sort -rh | head -5
```

**Recover**
```bash
# 1. Stop generation immediately
pkill -f "ultrawhale generate" 2>/dev/null || true

# 2. Free space — compress oldest files
# Already compressed files can be safely deleted locally
# if they've been uploaded to HF
find . -name '*_kompressed.jsonl' -mtime +7 -delete
find . -name '*.jsonl' -mtime +30 -delete

# 3. Truncate oversized logs
truncate -s 0 /tmp/worker1.log /tmp/worker2.log

# 4. If still tight, move output to a larger volume
mv dogfeed_parallel /mnt/bigdisk/
ln -s /mnt/bigdisk/dogfeed_parallel .

# 5. Resume generation
bash run.sh
```

**Root cause investigation**
- Log files growing unbounded (add log rotation)
- Generated JSONL not being uploaded/cleaned up
- Telemetry/upload loop falling behind

**Prevention**
- Add `logrotate` config for `/tmp/worker*.log`
- Set `MAX_LOCAL_FILES` in upload config
- Monitor disk via `ULTRAWHALE status` or cron

---

## Playbook 3: HF Upload Failure / Auth Error

**Symptoms**: `ultrawhale upload` prints `401 Unauthorized` or `HF_TOKEN not set`. Dataset not updating.

**Severity**: High — data generated but not published.

**Check**
```bash
# 1. Verify token is set and valid
echo "HF_TOKEN=${HF_TOKEN:0:6}..."
curl -sI "https://huggingface.co/api/datasets/PeetPedro/ultrawhale-dogfood" \
  -H "Authorization: Bearer $HF_TOKEN" | head -5

# 2. Check local file backlog
uv run ultrawhale upload --dry-run
```

**Recover**
```bash
# 1. Re-export valid token
export HF_TOKEN=hf_your_token_here

# 2. Upload missed files (low-priority, non-destructive)
uv run ultrawhale upload --active-grace 0

# 3. If rate-limited, upload in batches
find . -name 'dogfeed_*.jsonl' -not -name '*kompressed*' | head -20 | \
  while read f; do
    cp "$f" /tmp/$(basename "$f")
    uv run ultrawhale upload --dir /tmp --active-grace 0
    sleep 2
  done
```

**Root cause investigation**
- Token expired or revoked
- Rate limit exceeded (check `X-RateLimit-Remaining` header)
- Dataset is gated and token lacks access

**Prevention**
- Validate token on startup (`ultrawhale status` does this)
- Keep token in `.env` file alongside env var
- Monitor upload success rate

---

## Playbook 4: Worker Hang / Zombie Process

**Symptoms**: `ultrawhale status` shows no progress. Worker PIDs exist but CPU is idle. Disk not growing.

**Severity**: Medium — generation stalls silently.

**Check**
```bash
# 1. List all worker processes
ps aux | grep -E 'ultrawhale.*generate|python3.*generate' | grep -v grep

# 2. Check individual worker logs
tail -20 /tmp/worker1.log
tail -20 /tmp/worker2.log

# 3. Is the LLM server still responsive?
curl -sf http://localhost:8080/v1/models > /dev/null && echo "server OK" || echo "server DEAD"
```

**Recover**
```bash
# 1. Kill the hung workers
pkill -f "ultrawhale.*generate" 2>/dev/null || true
sleep 2

# 2. If still alive, force kill
pkill -9 -f "ultrawhale.*generate" 2>/dev/null || true

# 3. Check for partial JSONL corruption
tail -1 dogfeed_cs_*.jsonl 2>/dev/null | python3 -m json.tool > /dev/null && echo "last line OK" || echo "corrupt last line — repair needed"

# 4. Repair: remove incomplete last line if needed
for f in dogfeed_*.jsonl; do
  if ! python3 -c "import json; json.loads(open('$f').read().strip().split()[-1])" 2>/dev/null; then
    head -n -1 "$f" > "${f}.tmp" && mv "${f}.tmp" "$f"
    echo "Repaired: $f"
  fi
done

# 5. Restart
bash run.sh
```

**Root cause investigation**
- Deadlock in HTTP request to LLM server (check timeout)
- Generator model produced infinite output
- HF inference endpoint timeout (set `ROUND_TIMEOUT`)

**Prevention**
- Set `ROUND_TIMEOUT=120` in environment
- Add worker watchdog via cron:
  ```bash
  * * * * * if ! pgrep -f "ultrawhale.*generate" > /dev/null; then echo "Workers dead, restarting" | logger; bash /path/to/run.sh; fi
  ```
