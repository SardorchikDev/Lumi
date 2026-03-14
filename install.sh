#!/usr/bin/env bash
# Lumi AI — One-line installer
# curl -fsSL https://raw.githubusercontent.com/SardorchikDev/lumi/main/install.sh | bash

set -e

# ── Colors ────────────────────────────────────────────────────
R="\033[0m"
B="\033[1m"
PU="\033[38;5;141m"
GN="\033[38;5;114m"
YE="\033[38;5;179m"
RE="\033[38;5;203m"
DG="\033[38;5;238m"
CY="\033[38;5;117m"

# ── Banner ────────────────────────────────────────────────────
echo ""
echo -e "${PU}    ██╗      ██╗   ██╗  ███╗   ███╗  ██╗${R}"
echo -e "${PU}    ██║      ██║   ██║  ████╗ ████║  ██║${R}"
echo -e "${PU}    ██║      ██║   ██║  ██╔████╔██║  ██║${R}"
echo -e "${PU}    ██║      ██║   ██║  ██║╚██╔╝██║  ██║${R}"
echo -e "${PU}    ███████╗ ╚██████╔╝  ██║ ╚═╝ ██║  ██║${R}"
echo -e "${PU}    ╚══════╝  ╚═════╝   ╚═╝     ╚═╝  ╚═╝${R}"
echo -e "${DG}           A I   I N S T A L L E R${R}"
echo ""

# ── Helpers ───────────────────────────────────────────────────
ok()   { echo -e "  ${GN}✓${R}  $1"; }
info() { echo -e "  ${CY}→${R}  $1"; }
warn() { echo -e "  ${YE}▲${R}  $1"; }
fail() { echo -e "  ${RE}✗${R}  $1"; exit 1; }
step() { echo -e "\n  ${B}${PU}$1${R}"; }

INSTALL_DIR="$HOME/Lumi"
BIN_DIR="$HOME/.local/bin"
REPO="https://github.com/SardorchikDev/lumi"

# ── Parse flags ──────────────────────────────────────────────
DEV_MODE=false
for arg in "$@"; do
    case "$arg" in
        --dev)  DEV_MODE=true ;;
    esac
done

if $DEV_MODE; then
    info "Dev mode enabled — will install ruff, pytest, and pre-commit hooks"
fi

# ── Check dependencies ────────────────────────────────────────
step "Checking dependencies"

command -v python3 >/dev/null 2>&1 || fail "python3 not found — install Python 3.10+ first"
command -v git     >/dev/null 2>&1 || fail "git not found — install git first"
command -v pip3    >/dev/null 2>&1 || command -v pip >/dev/null 2>&1 || fail "pip not found"

PYTHON=$(command -v python3)
PY_VER=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$($PYTHON -c "import sys; print(sys.version_info.major)")
PY_MINOR=$($PYTHON -c "import sys; print(sys.version_info.minor)")
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    fail "Python 3.10+ required (found $PY_VER)"
fi
ok "Python $PY_VER found"
ok "git found"

# ── Clone repo ────────────────────────────────────────────────
step "Cloning Lumi"

if [ -d "$INSTALL_DIR" ]; then
    warn "Directory $INSTALL_DIR already exists — pulling latest changes"
    cd "$INSTALL_DIR"
    git pull --quiet
    ok "Updated to latest"
else
    git clone --quiet "$REPO" "$INSTALL_DIR"
    ok "Cloned to $INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# ── Create virtual environment ────────────────────────────────
step "Creating virtual environment"

if [ ! -d "$INSTALL_DIR/venv" ]; then
    $PYTHON -m venv venv
    ok "venv created"
else
    ok "venv already exists — skipping"
fi

# Activate
source "$INSTALL_DIR/venv/bin/activate"
ok "venv activated"

# ── Install dependencies ─────────────────────────────────────
step "Installing dependencies"

pip install --quiet --upgrade pip

if [ -f "$INSTALL_DIR/pyproject.toml" ]; then
    if $DEV_MODE; then
        pip install --quiet -e "$INSTALL_DIR[dev]"
        ok "All packages installed (including dev tools: ruff, pytest, pre-commit)"
    else
        pip install --quiet -e "$INSTALL_DIR"
        ok "All packages installed"
    fi
else
    pip install --quiet -r "$INSTALL_DIR/requirements.txt"
    ok "All packages installed (legacy requirements.txt)"
fi

# ── Create .env if not exists ─────────────────────────────────
step "Setting up .env"

if [ ! -f "$INSTALL_DIR/.env" ]; then
    cat > "$INSTALL_DIR/.env" << 'ENVEOF'
# Lumi API Keys — add at least one to get started
# All providers are free — no credit card needed

GEMINI_API_KEY=        # https://aistudio.google.com/apikey
GROQ_API_KEY=          # https://console.groq.com
OPENROUTER_API_KEY=    # https://openrouter.ai/keys
MISTRAL_API_KEY=       # https://console.mistral.ai
HF_TOKEN=              # https://huggingface.co/settings/tokens
ENVEOF
    ok ".env created — add your API keys before running lumi"
else
    ok ".env already exists — keeping your keys"
fi

# ── Set up pre-commit hooks (dev mode) ───────────────────────
if $DEV_MODE; then
    step "Setting up pre-commit hooks"
    if command -v pre-commit >/dev/null 2>&1; then
        cd "$INSTALL_DIR"
        pre-commit install --quiet
        ok "Pre-commit hooks installed"
    else
        warn "pre-commit not found in PATH — run 'pre-commit install' manually after activating venv"
    fi
fi

# ── Create lumi launcher ──────────────────────────────────────
step "Installing lumi command"

mkdir -p "$BIN_DIR"

cat > "$BIN_DIR/lumi" << LAUNCHEREOF
#!/usr/bin/env bash
# Lumi AI launcher
cd "$INSTALL_DIR"
source "$INSTALL_DIR/venv/bin/activate"
exec python main.py "\$@"
LAUNCHEREOF

chmod +x "$BIN_DIR/lumi"
ok "lumi command created at $BIN_DIR/lumi"

# ── Add to PATH if needed ─────────────────────────────────────
step "Configuring PATH"

SHELL_NAME=$(basename "$SHELL")

add_to_path() {
    local config_file="$1"
    local export_line='export PATH="$HOME/.local/bin:$PATH"'
    if [ -f "$config_file" ] && grep -q ".local/bin" "$config_file"; then
        ok "$BIN_DIR already in PATH ($config_file)"
    else
        echo "" >> "$config_file"
        echo "# Lumi AI" >> "$config_file"
        echo "$export_line" >> "$config_file"
        ok "Added $BIN_DIR to PATH in $config_file"
    fi
}

case "$SHELL_NAME" in
    fish)
        FISH_CONFIG="$HOME/.config/fish/config.fish"
        mkdir -p "$(dirname "$FISH_CONFIG")"
        if grep -q ".local/bin" "$FISH_CONFIG" 2>/dev/null; then
            ok "$BIN_DIR already in fish PATH"
        else
            echo "" >> "$FISH_CONFIG"
            echo "# Lumi AI" >> "$FISH_CONFIG"
            echo "fish_add_path \$HOME/.local/bin" >> "$FISH_CONFIG"
            ok "Added $BIN_DIR to fish PATH"
        fi
        ;;
    zsh)
        add_to_path "$HOME/.zshrc"
        ;;
    bash)
        if [ -f "$HOME/.bashrc" ]; then
            add_to_path "$HOME/.bashrc"
        else
            add_to_path "$HOME/.bash_profile"
        fi
        ;;
    *)
        warn "Unknown shell '$SHELL_NAME' — manually add $BIN_DIR to your PATH"
        ;;
esac

# ── Done ──────────────────────────────────────────────────────
echo ""
echo -e "  ${PU}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${R}"
echo -e "  ${GN}${B}Lumi installed successfully!${R}"
echo -e "  ${PU}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${R}"
echo ""
echo -e "  ${CY}Next steps:${R}"
echo ""
echo -e "  ${DG}1.${R}  Add at least one API key to ${YE}~/Lumi/.env${R}"
echo -e "      ${DG}→  GEMINI_API_KEY=...  (recommended, free)${R}"
echo -e "      ${DG}→  get it at: aistudio.google.com/apikey${R}"
echo ""
echo -e "  ${DG}2.${R}  Reload your shell:"
case "$SHELL_NAME" in
    fish) echo -e "      ${PU}source ~/.config/fish/config.fish${R}" ;;
    zsh)  echo -e "      ${PU}source ~/.zshrc${R}" ;;
    *)    echo -e "      ${PU}source ~/.bashrc${R}" ;;
esac
echo ""
echo -e "  ${DG}3.${R}  Launch Lumi from anywhere:"
echo -e "      ${PU}lumi${R}"
echo ""
if ! $DEV_MODE; then
    echo -e "  ${DG}Tip:${R}  Re-run with ${PU}--dev${R} to install dev tools (ruff, pytest, pre-commit)"
    echo ""
fi
echo -e "  ${DG}Free API keys:${R}"
echo -e "   ${DG}Gemini  →  aistudio.google.com/apikey${R}"
echo -e "   ${DG}Groq    →  console.groq.com${R}"
echo -e "   ${DG}OpenRouter  →  openrouter.ai/keys${R}"
echo ""
