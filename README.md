# Lumi

A conversational AI assistant with a terminal CLI and web interface, built by **Sardor Sodiqov** (SardorchikDev).

```
  ██╗     ██╗   ██╗███╗   ███╗██╗
  ██║     ██║   ██║████╗ ████║██║
  ██║     ██║   ██║██╔████╔██║██║
  ██║     ██║   ██║██║╚██╔╝██║██║
  ███████╗╚██████╔╝██║ ╚═╝ ██║██║
  ╚══════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝

  A R T I F I C I A L   I N T E L L I G E N C E
```

---

## Features

- **Streaming responses** — token-by-token output just like ChatGPT
- **Conversation memory** — remembers the last 20 turns
- **Save & load sessions** — persist conversations to disk
- **Export chats** — export any conversation as a `.md` file
- **Web search** — auto-searches DuckDuckGo on relevant queries
- **Auto-retry on 429** — counts down and retries on rate limits
- **Model fallback** — automatically switches to a backup model if the primary fails
- **Markdown rendering** — bold, code blocks, bullet points rendered in the terminal
- **Animated spinner** — braille spinner while waiting for the first token
- **Multi-line input** — paste code or long text without it sending early
- **Web UI** — Tokyo Night Storm themed chat interface deployed on Vercel
- **`--debug` flag** — prints raw API responses for debugging

---

## Project Structure

```
Lumi/
├── main.py                        # CLI entry point
├── requirements.txt
├── .env                           # HF_TOKEN goes here
├── configs/
│   └── config.yaml
├── data/
│   ├── conversations/             # saved sessions (auto-gitignored)
│   │   └── exports/               # /export command outputs
│   └── personas/
│       └── default.json           # Lumi's personality
├── src/
│   ├── chat/
│   │   └── hf_client.py           # HuggingFace API + streaming + retry
│   ├── memory/
│   │   ├── short_term.py          # in-context memory (last N turns)
│   │   └── conversation_store.py  # save/load to disk
│   ├── prompts/
│   │   └── builder.py             # system prompt + message builder
│   ├── tools/
│   │   └── search.py              # DuckDuckGo web search
│   └── utils/
│       ├── markdown.py            # terminal markdown renderer
│       └── export.py              # export chat to .md
└── Lumi-website/                  # web interface (separate repo/folder)
    ├── index.html
    ├── config.js                  # HF token (gitignored)
    ├── vercel.json
    └── api/
        └── chat.js                # Vercel serverless proxy
```

---

## Setup

**1. Clone and enter the project**

```bash
cd ~/Lumi
```

**2. Create a virtual environment** (required on Arch Linux)

```bash
python3 -m venv venv
source venv/bin/activate.fish   # Fish shell
# or
source venv/bin/activate        # Bash/Zsh
```

**3. Install dependencies**

```bash
pip install -r requirements.txt
```

**4. Add your HuggingFace token**

Get a free token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)

```bash
# .env
HF_TOKEN=hf_xxxxxxxxxxxxxxxx
```

**5. Run**

```bash
python3 main.py

# With debug logging
python3 main.py --debug
```

---

## CLI Commands

| Command | Description |
|---|---|
| `/help` | Show all commands |
| `/clear` | Reset conversation memory |
| `/save` | Save conversation to disk |
| `/load` | Load last saved conversation |
| `/sessions` | List all saved sessions |
| `/export` | Export chat as `.md` file |
| `/retry` | Resend last message |
| `/model` | Switch model interactively |
| `/model <name>` | Set model directly by name |
| `/multi` | Toggle multi-line input mode |
| `/quit` | Save and exit |

---

## Models

Lumi tries models in this order, automatically falling back if one is rate-limited:

1. `meta-llama/Llama-3.1-8B-Instruct` ← default
2. `Qwen/Qwen2.5-7B-Instruct`
3. `microsoft/Phi-3.5-mini-instruct`

Switch model at any time with `/model` inside the chat.

---

## Dependencies

```
openai          # HuggingFace router uses OpenAI-compatible API
python-dotenv   # loads .env file
huggingface_hub # HF utilities
```

---

## Notes

- **Rate limits** — the free HF Inference API has a queue. Lumi auto-retries with a countdown. If it keeps failing, try `/model` to switch to a less busy model.
- **venv** — always activate the venv before running: `source ~/Lumi/venv/bin/activate.fish`
- **conversations are gitignored** — `data/conversations/` is excluded from git by default

---

## Author

Built by **Sardor Sodiqov** — [github.com/SardorchikDev](https://github.com/SardorchikDev)
