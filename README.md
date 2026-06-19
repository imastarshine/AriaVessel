# AriaVessel

A Telegram bot that manages aria2 downloads and optionally uploads completed files to Yandex.Disk. Send it torrents, magnet links, or HTTP links. It talks to aria2 over JSON-RPC.

## Commands

| Command | What it does |
|---------|-------------|
| `/status` | Show all active downloads with progress |
| `/status exclude-completed` | Same but hides finished ones |
| `/pause <id>` | Pause by index, GID, range (0,3), or list [0,2,4] |
| `/resume <id>` | Resume paused downloads |
| `/rm <id>` | Remove download but keep files |
| `/del <id>` | Remove download and delete its files |
| `/restart <id>` | Re-add an HTTP download from scratch |
| `/inspect <idx>` | Show details about a specific download |
| `/after <link>` | Queue a link to start after all active downloads finish |
| `/after <id> <link>` | Queue a link after a specific download |
| `/upload <id>` | Upload completed files to Yandex.Disk |
| `/upload_status` | Check upload progress |
| `/upload_cancel` | Stop the current upload |
| `/settings` | Change bot configuration |
| `/start` | List all commands |

You can send `.torrent` files, `.zip` archives (the bot extracts `.torrent` files from them), `.txt` files (the bot extracts magnet and HTTP links, or `/after` commands), or paste `magnet:` links directly.

## How it works

The bot talks to aria2 over JSON-RPC. When you add a download, it pauses, asks for confirmation, and resumes once you confirm. You can check what you are adding before it starts.

The `/after` command chains downloads. Without an explicit parent, it waits for all active downloads then starts. If nothing is running, it starts right away. Specify a download by index or GID, or chain multiple `/after` calls sequentially.

The bot supports filename renaming, transliteration, and slugification for HTTP downloads. Toggle them from `/settings`.

## File formats

### .txt

The bot reads a .txt file and decides what to do based on content:

- All lines start with `/after` — queued via `/after` (each link waits for the previous one)
- Otherwise — URLs (`magnet:`, `https://`, `http://`) are extracted and added directly

```
magnet:?xt=urn:btih:...
https://example.com/file.iso
```

```
/after magnet:?xt=urn:btih:...
/after https://example.com/file.iso
```

You can mix `/after` with plain URLs in the same file — only the URLs will be extracted and added directly, `/after` lines are ignored in mixed mode.

### .zip

The bot extracts `.torrent` files from the archive and adds each one to aria2. Pack your torrent files into a zip and send it as a document.

### .torrent

Sent directly to aria2 as a paused download.

## Prerequisites

- Python 3.12+
- aria2 with JSON-RPC enabled
- Poetry (for dependency management)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- (Optional) Yandex.Disk token for the upload feature

## Setup

### 1. Clone and install

```bash
git clone <repo-url> && cd AriaVessel
poetry install
```

### 2. Configure environment

Copy the example and fill in your values:

```bash
cp .env-example .env
```

| Variable | What it is |
|----------|-----------|
| `BOT_TOKEN` | Your Telegram bot token from BotFather |
| `ADMIN_ID` | Your Telegram user ID (the bot only responds to you) |
| `ARIA2_SECRET` | The RPC secret set in your aria2 config |
| `YADISK_TOKEN` | Yandex.Disk OAuth token (optional, only needed for upload) |
| `TORRENT_DIRECTORY` | Path where aria2 saves downloads (used by upload) |

### 3. Start aria2

A minimal working setup:

```bash
aria2c --enable-rpc --rpc-listen-all --rpc-secret=<your-secret> \
       --dir=/path/to/downloads --continue=true \
       --max-connection-per-server=16 --split=16 \
       --bt-max-peers=0 --seed-time=0
```

Key flags:

- `--enable-rpc` — required, the bot communicates over RPC
- `--rpc-secret=<secret>` — must match `ARIA2_SECRET` in `.env`
- `--dir=<path>` — download directory, should match `TORRENT_DIRECTORY`
- `--seed-time=0` — stop seeding immediately after download completes

### 4. Run the bot

```bash
poetry run python main.py
```

or activate the virtual environment first:

```bash
poetry shell
python main.py
```

The bot prints basic logs to stdout. Log files are stored in the `logs/` directory and rotate automatically.

## Optional: Yandex.Disk upload

If you configure `YADISK_TOKEN`, `/upload` copies completed files to your Yandex.Disk. The bot creates an isolated folder under "Applications" on your Yandex.Disk and places files inside an `ariavessel` subfolder. Without a token, the bot still manages aria2 downloads normally.

You can get a Yandex.Disk OAuth token here:
```
https://oauth.yandex.ru/authorize?response_type=token&client_id=6f4cad7c59b7485088f400fe2ffeea84
```
