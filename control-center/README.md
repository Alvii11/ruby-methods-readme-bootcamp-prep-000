# 🛰️ Control Center

A local web dashboard to **supervise the bots, trading scripts, and monitoring
jobs you already run on your Mac** — start/stop/restart them, watch live status
(PID, uptime, CPU, memory, restart count), tail their logs, and keep an eye on
overall system health, all from one browser tab at `http://127.0.0.1:8765`.

It is **config-driven**: you list your existing scripts in `config.yaml`, and
the Control Center runs and watches them as child processes.

> **Important — what this is and isn't.**
> This tool does **not** place trades, connect to brokers/exchanges, or contain
> any trading logic. It is a *process supervisor + dashboard*. Your strategies
> stay in your own scripts; the Control Center just launches and monitors them.
> Keep your own kill-switch / risk limits inside your trading bots. Run live
> trading only when you understand the risk — start with paper/test modes.

## Features

- **Process control** — start, stop (graceful `SIGTERM` → `SIGKILL`), restart.
- **Groups** — organize bots into `trading`, `monitoring`, `other`, … with
  one-click *Start all / Stop all* per group.
- **Live status** — running/stopped/exited/crashed, PID, uptime, CPU %, memory.
- **Auto-restart** — opt-in per bot; crashed processes come back automatically.
- **Log tailing** — per-bot stdout/stderr captured to `logs/<id>.log`, viewable
  live in the UI.
- **System monitoring** — CPU, load average, memory, disk, host uptime.

Each bot runs in its own process group (`start_new_session`), so stopping a bot
also stops any child processes it spawned.

## Quick start

```bash
cd control-center
cp config.example.yaml config.yaml   # then edit to point at YOUR scripts
./run.sh                             # creates a venv, installs deps, serves UI
```

Open <http://127.0.0.1:8765>.

> Requires Python 3.10+. `run.sh` builds a local `.venv` on first run. To run
> manually: `pip install -r requirements.txt && uvicorn app.main:app --port 8765`.

## Configuring your bots

Edit `config.yaml`. Each entry describes one process:

```yaml
log_dir: ./logs
host: 127.0.0.1
port: 8765

bots:
  - id: momentum-trader          # unique id (used for logs + API)
    name: Momentum Trader        # display name
    group: trading               # trading | monitoring | other | anything
    description: My live strategy
    command: ["python3", "bot.py"]   # list = run directly (safer, no shell)
    cwd: /Users/you/bots/momentum    # working directory
    autorestart: true                # restart automatically if it dies
    env:                             # extra environment variables
      MODE: paper

  - id: backup
    command: "bash backup.sh && echo done"   # string + shell:true for pipes/&&
    shell: true
    cwd: /Users/you/scripts
```

| Key           | Required | Meaning                                                        |
|---------------|----------|----------------------------------------------------------------|
| `id`          | ✅       | Unique identifier; names the log file `logs/<id>.log`.         |
| `name`        | ✅       | Friendly label in the UI.                                      |
| `command`     | ✅       | List (run directly) or string (set `shell: true` for shell).  |
| `cwd`         |          | Working directory for the process.                            |
| `group`       |          | Section in the dashboard. Default `other`.                    |
| `autorestart` |          | Restart automatically when the process exits. Default `false`.|
| `shell`       |          | Run `command` through a shell (pipes, `&&`, globs).           |
| `env`         |          | Extra environment variables (merged over the parent env).     |

Point `CC_CONFIG=/some/path.yaml ./run.sh` to use a config elsewhere.

## HTTP API

The UI is a thin client over a small JSON API — handy for scripting or your own
tooling:

| Method | Path                          | Description                  |
|--------|-------------------------------|------------------------------|
| GET    | `/api/bots`                   | All bots + their status.     |
| GET    | `/api/bots/{id}`              | One bot's status.            |
| POST   | `/api/bots/{id}/start`       | Start a bot.                 |
| POST   | `/api/bots/{id}/stop`        | Stop a bot.                  |
| POST   | `/api/bots/{id}/restart`     | Restart a bot.               |
| GET    | `/api/bots/{id}/logs?lines=` | Tail a bot's log.            |
| POST   | `/api/groups/{group}/start`  | Start every bot in a group.  |
| POST   | `/api/groups/{group}/stop`   | Stop every bot in a group.   |
| GET    | `/api/system`                 | System health metrics.       |

## Security notes

- Binds to `127.0.0.1` by default — reachable only from your machine. **Do not**
  expose it on `0.0.0.0` / the internet; it can start arbitrary processes and
  has no authentication. If you need remote access, front it with something that
  adds auth + TLS (e.g. an SSH tunnel or a reverse proxy).
- `config.yaml` may reference scripts that hold secrets/credentials — it's
  gitignored by default. Keep API keys in your bots' own env, not in the repo.

## Layout

```
control-center/
├── app/
│   ├── main.py          # FastAPI app + routes
│   ├── config.py        # config loading/validation
│   ├── manager.py       # process supervisor (start/stop/monitor/logs)
│   ├── monitoring.py    # system health metrics
│   └── static/          # dashboard UI (HTML/CSS/JS)
├── config.example.yaml
├── requirements.txt
└── run.sh
```
