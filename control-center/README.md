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
- **Remote access** — optional password login (signed session cookies) + TLS, so
  you can safely reach it from your phone over an SSH tunnel or private network.
- **Crash alerts** — get notified (macOS desktop, Slack, or email) the moment a
  bot dies, so you don't have to watch the dashboard.

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
| GET    | `/api/alerts`                 | Alert config + active channels.|
| POST   | `/api/alerts/test`            | Send a test alert.           |

## Remote access (control it from your phone / anywhere)

The dashboard can start arbitrary processes, so **any time it's reachable beyond
localhost it must require a password and use TLS.** Built-in support for both:

### 1. Turn on password login

```bash
export CC_PASSWORD='something-strong'     # the dashboard password
```

In `config.yaml`:

```yaml
auth:
  enabled: true
  password_env: CC_PASSWORD     # reads the env var above
  session_hours: 12
```

Prefer not to use an env var? Store a hash instead (plaintext never touches the
file):

```bash
./hash-password.sh 'something-strong'     # prints a sha256 digest
```
```yaml
auth:
  enabled: true
  password_sha256: "<paste digest>"
```

With auth on, every request needs a signed session cookie; unauthenticated
browsers are bounced to a login page and API calls get `401`. Cookies are
HMAC-signed (set `auth.secret` or `$CC_SECRET` to keep sessions valid across
restarts).

### 2. Turn on TLS (HTTPS)

```bash
./gen-cert.sh                 # writes certs/cert.pem + certs/key.pem (self-signed)
```
```yaml
tls:
  certfile: ./certs/cert.pem
  keyfile:  ./certs/key.pem
```

`run.sh` picks these up automatically and serves over `https://`. (Browsers warn
on self-signed certs — expected; use a real cert if you have a domain.)

### 3. Choose how to reach it

| Method | How | Notes |
|--------|-----|-------|
| **SSH tunnel** (recommended) | `ssh -L 8765:127.0.0.1:8765 you@your-mac` then open `localhost:8765` | Keep `host: 127.0.0.1`. Nothing exposed; encrypted by SSH. Simplest + safest. |
| **Tailscale / WireGuard** | Install on Mac + phone; reach the Mac's private IP | Set `host: 0.0.0.0`. Keep **auth on**. Private network, no public exposure. |
| **LAN** | Set `host: 0.0.0.0`, hit the Mac's LAN IP | Auth + TLS **required**. Only as safe as your network. |

> ⚠️ **Do not port-forward this to the public internet.** Even with auth, a
> process-spawning dashboard is a big target. Use the SSH tunnel or a private
> mesh (Tailscale) instead.

## Crash alerts

Get pinged when a bot dies instead of discovering it later. Enable in
`config.yaml`:

```yaml
alerts:
  enabled: true
  on_crash: true       # non-zero exit you didn't trigger
  on_exit: false       # clean exit (code 0) on its own
  on_restart: false    # auto-restart fired after a death
  desktop: true        # macOS notification (Linux: notify-send)
  slack_webhook_env: CC_SLACK_WEBHOOK   # export the webhook URL
  # email:             # optional SMTP (creds from env, not the file)
  #   smtp_host: smtp.gmail.com
  #   username_env: CC_SMTP_USER
  #   password_env: CC_SMTP_PASS
  #   recipients: [you@example.com]
```

How the events map:
- A bot that **crashes** (non-zero exit) you didn't stop → `crash` alert.
- A bot that **exits cleanly** on its own → `exit` alert (off by default).
- An `autorestart` bot that dies → `restart` alert (it recovers; no `crash`).
- Stopping a bot yourself → **no** alert.

Each channel is best-effort and runs off-thread, so a flaky webhook never stalls
the supervisor. Hit **🔔 Test alert** in the UI (or `POST /api/alerts/test`) to
verify delivery. Slack uses an [incoming webhook][slack]; email uses SMTP with
credentials pulled from env vars.

[slack]: https://api.slack.com/messaging/webhooks

## Security notes

- Defaults to `127.0.0.1` with no auth — fine for local-only use. Exposing it
  beyond localhost without `auth.enabled: true` is unsafe; the app refuses to
  start if auth is enabled but no password is configured.
- `config.yaml` and `certs/` may hold secrets — both are gitignored. Keep broker
  API keys in your bots' own env, not in the repo.
- Sessions are cookie-based (`HttpOnly`, `SameSite=Strict`, `Secure` when TLS is
  on). There's no rate-limiting on login — another reason to stay off the public
  internet.

## Layout

```
control-center/
├── app/
│   ├── main.py          # FastAPI app + routes + auth middleware
│   ├── config.py        # config loading/validation
│   ├── manager.py       # process supervisor (start/stop/monitor/logs)
│   ├── monitoring.py    # system health metrics
│   ├── auth.py          # password login + signed session cookies
│   ├── notifier.py      # crash alerts (desktop / Slack / email)
│   └── static/          # dashboard UI + login page (HTML/CSS/JS)
├── config.example.yaml
├── requirements.txt
├── run.sh               # launch (venv + TLS aware)
├── gen-cert.sh          # generate a self-signed TLS cert
└── hash-password.sh     # hash a password for config
```
