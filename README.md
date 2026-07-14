# Synapse ⚡

**One search query. Six engines. The best results win.**

Synapse is a lightweight search aggregator server. When you search for something, it fires your query to multiple search APIs at once, picks the best results, and returns them — all in under two seconds.

It's a drop-in replacement for [SearXNG](https://github.com/searxng/searxng). If your tool already supports SearXNG (and many do), Synapse works with zero config changes.

---

## Why Synapse?

Most search tools rely on a single API. If that API goes down, rate-limits you, or just has bad results for certain queries — too bad.

Synapse doesn't have that problem.

- **Six APIs, one query** — Brave, Google (via Serper), Tavily, Daum (Kakao), Naver, and Exa. All called in parallel.
- **Resilient by design** — One API fails? You still get results from the others. No single point of failure.
- **Korean search, actually great** — Naver + Daum (Kakao) are built in. Korean-language queries that stumped global APIs now return real results from Naver blogs, cafes, and Daum web.
- **Free tier, real limits** — 3,500+/month across Brave + Serper + Tavily + Exa, plus **55,000/day** from Naver and Daum combined.
- **Shoebox-sized** — Python + FastAPI. Six dependencies. No Docker required (but available if you want it).

---

## Quick Start

```bash
git clone https://github.com/mwl313/synapse_searcher.git
cd synapse_searcher
pip install -r requirements.txt
cp .env.example .env

# Run the setup wizard to enter API keys
python setup.py

# Start the server
python server.py
```

That's it. Your server is now listening on `http://localhost:8888`.

```bash
# Test it
curl "http://localhost:8888/search?q=hello+world&format=json"
curl "http://localhost:8888/health"
curl "http://localhost:8888/engines/status"
```

---

## Setup Wizard

Getting API keys is the most tedious part of any multi-engine setup. Synapse comes with a wizard to make it painless:

```bash
# First run — enter API keys interactively
python setup.py

# Run again anytime to add, remove, or change keys
python setup.py

# Start fresh
python setup.py --reset
```

Skip any key by pressing Enter — that engine will be automatically disabled. No config files to hand-edit.

---

## Getting API Keys (All Free)

| Engine | Free Tier | Where to Get It |
|:------:|:---------:|:----------------|
| **Brave Search** | 1,000/month ($5 credits) | https://api-dashboard.search.brave.com/ |
| **Serper (Google)** | 2,500/month | https://serper.dev |
| **Tavily (AI)** | 1,000/month | https://app.tavily.com |
| **Exa (AI Agent)** | 1,000/month | https://exa.ai |
| **Daum (Kakao)** | **30,000/day** | https://developers.kakao.com |
| **Naver Search** | **25,000/day** | https://developers.naver.com |

**Pro tip:** Brave + Serper + Daum + Naver gets you excellent coverage with Korean search being surprisingly good. Start with those.

---

## What Makes It Different

| | Single API | SearXNG (self-hosted) | **Synapse** |
|:--|:----------:|:---------------------:|:-----------:|
| **Setup time** | 5 minutes | 30+ minutes (Docker) | **3 minutes** |
| **Failure mode** | One API = single point of failure | Self-hosted engines break silently | **Degrades gracefully** |
| **Korean search** | Poor on most APIs | Depends on engine config | **Naver + Daum built-in** |
| **Free quota** | Varies | Unlimited (scraping) | **3.5K/mo + 55K/day** |
| **Resource usage** | Nothing extra | Full Docker container | **~50MB Python process** |

---

## Works With

Any tool that supports SearXNG as a search backend:

- **OpenClaw** — `SEARXNG_BASE_URL=http://localhost:8888`
- **Claude Code** — Set `"searchProvider": "searxng"` in `claude.json`
- **Cline** — Register as a SearXNG MCP server
- **Cursor, SillyTavern, and others** — Point them at `http://localhost:8888`

The API response format is identical to SearXNG JSON. No adapter, no middleware, no translation layer.

---

## Architecture (The 30-Second Version)

```
Your Tool (OpenClaw, Claude Code, etc.)
    │
    └── /search?q=... → Synapse (port 8888)
                            │
                ┌───────┬───┼───┬───────┬───────┐
                ▼       ▼   ▼   ▼       ▼       ▼
            Brave  Serper  Tavily  Daum  Naver  Exa
                │       │   │   │       │       │
                └───────┴───┴───┴───────┴───────┘
                            │
                    Deduplicate + Score
                            │
                            ▼
                  SearXNG-compatible JSON
                            │
                            ▼
                    Your Tool receives results
```

---

## Project Structure

```
synapse/
├── server.py              # FastAPI server (SearXNG-compatible endpoints)
├── orchestrator.py        # Parallel execution + dedup + scoring engine
├── models.py              # Data models
├── config.py              # Environment-based config
├── setup.py               # Interactive setup wizard
├── engines/
│   ├── base.py            # Abstract engine class
│   ├── brave.py           # Brave Search API
│   ├── serper.py          # Serper.dev (Google results)
│   ├── tavily.py          # Tavily AI Search
│   ├── daum.py            # Daum (Kakao) Search — Korean optimized
│   ├── naver.py           # Naver Search API — Korean optimized
│   ├── exa.py             # Exa AI Search — AI agent optimized
│   └── legacy_bing.py     # Bing Search API (retired Aug 2025)
├── tests/
│   ├── test_queries.json  # Sample query set for testing
│   └── test_engines.py    # Engine test runner
└── docs/
    └── ARCHITECTURE.md    # Detailed design doc
```

---

## Engine Status & Monitoring

Synapse tracks per-engine performance in real time:

```bash
# View live engine statistics
curl http://localhost:8888/engines/status

# Force dump stats to disk
curl -X POST http://localhost:8888/engines/status/dump
```

Each engine records success rate, average latency, last error, and last success time. Stats are persisted to `data/engine_stats.json` every 60 seconds.

---

## macOS LaunchAgent (Background Service)

To run Synapse as a background service on macOS (starts automatically on boot):

```bash
# Create the plist file
cat > ~/Library/LaunchAgents/io.haven.synapse.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>io.haven.synapse</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/python3</string>
        <string>/path/to/synapse/server.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/synapse</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/synapse.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/synapse.stderr.log</string>
</dict>
</plist>
EOF

# Load it
launchctl load ~/Library/LaunchAgents/io.haven.synapse.plist

# Start immediately
launchctl start io.haven.synapse
```

> **Note**: Make sure the working directory and python path are correct for your system. Adjust `/path/to/synapse` to your installation directory.

---

## License

MIT © 2026 Lim MinWoo. Free to use, modify, and distribute.

---

*Synapse — Because one search engine is a single point of failure.*
