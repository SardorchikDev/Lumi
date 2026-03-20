#!/usr/bin/env bash
# Lumi AI installer
# curl -fsSL https://raw.githubusercontent.com/SardorchikDev/lumi/main/install.sh | bash

set -euo pipefail

R="\033[0m"
B="\033[1m"
PU="\033[38;5;141m"
GN="\033[38;5;114m"
YE="\033[38;5;179m"
RE="\033[38;5;203m"
DG="\033[38;5;238m"
CY="\033[38;5;117m"

ok()   { echo -e "  ${GN}✓${R}  $1"; }
info() { echo -e "  ${CY}→${R}  $1"; }
warn() { echo -e "  ${YE}▲${R}  $1"; }
fail() { echo -e "  ${RE}✗${R}  $1" >&2; exit 1; }
step() { echo -e "\n  ${B}${PU}$1${R}"; }

usage() {
    cat <<'EOF'
Lumi installer

Usage:
  ./install.sh [options]

Options:
  --dev                 install dev extras and pre-commit hooks
  --dir <path>          install checkout into this directory (default: ~/Lumi)
  --bin-dir <path>      install launcher into this directory (default: ~/.local/bin)
  --repo <url>          clone from a different git remote
  --branch <name>       clone a specific branch on fresh installs (default: main)
  --profile <path>      write PATH update to this shell profile
  --no-path             skip PATH modification
  -h, --help            show this help and exit
EOF
}

expand_home() {
    case "$1" in
        "~") printf '%s\n' "$HOME" ;;
        "~/"*) printf '%s/%s\n' "$HOME" "${1#~/}" ;;
        *) printf '%s\n' "$1" ;;
    esac
}

path_export_value() {
    case "$1" in
        "$HOME") printf '%s\n' '$HOME' ;;
        "$HOME"/*) printf '$HOME/%s\n' "${1#$HOME/}" ;;
        *) printf '%s\n' "$1" ;;
    esac
}

banner() {
    echo ""
    echo -e "${PU}    ██╗      ██╗   ██╗  ███╗   ███╗  ██╗${R}"
    echo -e "${PU}    ██║      ██║   ██║  ████╗ ████║  ██║${R}"
    echo -e "${PU}    ██║      ██║   ██║  ██╔████╔██║  ██║${R}"
    echo -e "${PU}    ██║      ██║   ██║  ██║╚██╔╝██║  ██║${R}"
    echo -e "${PU}    ███████╗ ╚██████╔╝  ██║ ╚═╝ ██║  ██║${R}"
    echo -e "${PU}    ╚══════╝  ╚═════╝   ╚═╝     ╚═╝  ╚═╝${R}"
    echo -e "${DG}           A I   I N S T A L L E R${R}"
    echo ""
}

INSTALL_DIR="$HOME/Lumi"
BIN_DIR="$HOME/.local/bin"
REPO="https://github.com/SardorchikDev/lumi"
BRANCH="main"
PROFILE_FILE=""
DEV_MODE=false
NO_PATH=false

while [ $# -gt 0 ]; do
    case "$1" in
        --dev)
            DEV_MODE=true
            ;;
        --dir)
            shift
            [ $# -gt 0 ] || fail "Missing value for --dir"
            INSTALL_DIR="$1"
            ;;
        --bin-dir)
            shift
            [ $# -gt 0 ] || fail "Missing value for --bin-dir"
            BIN_DIR="$1"
            ;;
        --repo)
            shift
            [ $# -gt 0 ] || fail "Missing value for --repo"
            REPO="$1"
            ;;
        --branch)
            shift
            [ $# -gt 0 ] || fail "Missing value for --branch"
            BRANCH="$1"
            ;;
        --profile)
            shift
            [ $# -gt 0 ] || fail "Missing value for --profile"
            PROFILE_FILE="$1"
            ;;
        --no-path)
            NO_PATH=true
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            fail "Unknown option: $1 (use --help)"
            ;;
    esac
    shift
done

INSTALL_DIR="$(expand_home "$INSTALL_DIR")"
BIN_DIR="$(expand_home "$BIN_DIR")"
PROFILE_FILE="$(expand_home "$PROFILE_FILE")"
BIN_DIR_EXPORT="$(path_export_value "$BIN_DIR")"
RUNTIME_ROOT="${LUMI_RUNTIME_ROOT:-$HOME/.codex/memories/lumi}"
STATE_DIR_DEFAULT="${LUMI_STATE_DIR:-$RUNTIME_ROOT/state}"
CACHE_DIR_DEFAULT="${LUMI_CACHE_DIR:-$RUNTIME_ROOT/cache}"

banner

if $DEV_MODE; then
    info "Dev mode enabled — will install pytest, ruff, and pre-commit"
fi

if [ -n "$PROFILE_FILE" ] && $NO_PATH; then
    warn "--profile is ignored when --no-path is set"
fi

step "Checking dependencies"

command -v python3 >/dev/null 2>&1 || fail "python3 not found — install Python 3.10+ first"
command -v git >/dev/null 2>&1 || fail "git not found — install git first"

PYTHON="$(command -v python3)"
PY_VER="$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")"
PY_MAJOR="$("$PYTHON" -c "import sys; print(sys.version_info.major)")"
PY_MINOR="$("$PYTHON" -c "import sys; print(sys.version_info.minor)")"

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    fail "Python 3.10+ required (found $PY_VER)"
fi

if ! "$PYTHON" -m venv --help >/dev/null 2>&1; then
    fail "python3 venv support is missing — install the python3-venv package first"
fi

ok "Python $PY_VER found"
ok "git found"

step "Preparing checkout"

mkdir -p "$(dirname "$INSTALL_DIR")"

if [ -d "$INSTALL_DIR" ]; then
    if [ -d "$INSTALL_DIR/.git" ]; then
        REMOTE_URL="$(git -C "$INSTALL_DIR" remote get-url origin 2>/dev/null || printf '')"
        if [ -n "$REMOTE_URL" ] && [ "$REMOTE_URL" != "$REPO" ]; then
            warn "Existing repo remote is $REMOTE_URL (expected $REPO)"
        fi

        if ! git -C "$INSTALL_DIR" diff --quiet --ignore-submodules -- || \
           ! git -C "$INSTALL_DIR" diff --cached --quiet --ignore-submodules --; then
            warn "Local changes detected in $INSTALL_DIR — skipping git update"
        else
            CURRENT_BRANCH="$(git -C "$INSTALL_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || printf '')"
            if [ -n "$CURRENT_BRANCH" ] && [ "$CURRENT_BRANCH" != "$BRANCH" ]; then
                warn "Existing checkout is on branch $CURRENT_BRANCH — keeping it"
            fi
            git -C "$INSTALL_DIR" pull --ff-only --quiet || fail "Failed to update existing checkout"
            ok "Updated existing checkout"
        fi
    elif [ -z "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]; then
        git clone --quiet --branch "$BRANCH" "$REPO" "$INSTALL_DIR" || fail "Failed to clone $REPO"
        ok "Cloned to $INSTALL_DIR"
    else
        fail "Directory $INSTALL_DIR already exists and is not a Lumi git checkout"
    fi
else
    git clone --quiet --branch "$BRANCH" "$REPO" "$INSTALL_DIR" || fail "Failed to clone $REPO"
    ok "Cloned to $INSTALL_DIR"
fi

cd "$INSTALL_DIR"

step "Creating virtual environment"

if [ ! -d "$INSTALL_DIR/venv" ]; then
    "$PYTHON" -m venv "$INSTALL_DIR/venv"
    ok "venv created"
else
    ok "venv already exists — reusing it"
fi

VENV_PYTHON="$INSTALL_DIR/venv/bin/python"
VENV_PIP=("$VENV_PYTHON" -m pip)
export PIP_DISABLE_PIP_VERSION_CHECK=1

step "Installing dependencies"

"${VENV_PIP[@]}" install --quiet --upgrade pip setuptools wheel

if [ -f "$INSTALL_DIR/pyproject.toml" ]; then
    INSTALL_SPEC="$INSTALL_DIR"
    if $DEV_MODE; then
        INSTALL_SPEC="$INSTALL_DIR[dev]"
    fi
    "${VENV_PIP[@]}" install --quiet -e "$INSTALL_SPEC"
else
    [ -f "$INSTALL_DIR/requirements.txt" ] || fail "No pyproject.toml or requirements.txt found"
    "${VENV_PIP[@]}" install --quiet -r "$INSTALL_DIR/requirements.txt"
fi
ok "Dependencies installed"

step "Initializing Lumi runtime"

LUMI_HOME="$INSTALL_DIR" \
LUMI_STATE_DIR="$STATE_DIR_DEFAULT" \
LUMI_CACHE_DIR="$CACHE_DIR_DEFAULT" \
"$VENV_PYTHON" -c "from src.config import ensure_dirs; ensure_dirs()" \
    || fail "Installed package but failed to initialize Lumi runtime directories"

ok "Runtime directories ready"

step "Setting up .env"

if [ ! -f "$INSTALL_DIR/.env" ]; then
    cat > "$INSTALL_DIR/.env" <<ENVEOF
# Lumi API keys and optional runtime overrides

# Optional runtime overrides
# LUMI_HOME=$INSTALL_DIR
# LUMI_STATE_DIR=$STATE_DIR_DEFAULT
# LUMI_CACHE_DIR=$CACHE_DIR_DEFAULT

# Hosted model providers
GEMINI_API_KEY=        # https://aistudio.google.com/apikey
GROQ_API_KEY=          # https://console.groq.com
OPENROUTER_API_KEY=    # https://openrouter.ai/keys
MISTRAL_API_KEY=       # https://console.mistral.ai
HF_TOKEN=              # https://huggingface.co/settings/tokens
GITHUB_API_KEY=        # https://github.com/settings/tokens
COHERE_API_KEY=        # https://dashboard.cohere.com/api-keys
BYTEZ_API_KEY=         # https://bytez.com/api
AIRFORCE_API_KEY=      # https://api.airforce
VERCEL_API_KEY=        # https://vercel.com/dashboard -> AI -> API Keys
POLLINATIONS_API_KEY=  # https://gen.pollinations.ai

# Cloudflare Workers AI
CLOUDFLARE_API_KEY=
CLOUDFLARE_ACCOUNT_ID=

# Vertex AI
GOOGLE_APPLICATION_CREDENTIALS=
VERTEX_PROJECT_ID=
VERTEX_LOCATION=us-central1
ENVEOF
    ok ".env created — add at least one API key before running lumi"
else
    ok ".env already exists — keeping your keys"
fi

if $DEV_MODE; then
    step "Setting up pre-commit hooks"
    if [ -x "$INSTALL_DIR/venv/bin/pre-commit" ]; then
        "$INSTALL_DIR/venv/bin/pre-commit" install --quiet
        ok "Pre-commit hooks installed"
    else
        warn "pre-commit is unavailable in the venv — skipping hooks"
    fi
fi

step "Installing lumi command"

mkdir -p "$BIN_DIR"

cat > "$BIN_DIR/lumi" <<EOF
#!/usr/bin/env bash
set -e
export LUMI_HOME="$INSTALL_DIR"
export LUMI_STATE_DIR="\${LUMI_STATE_DIR:-$STATE_DIR_DEFAULT}"
export LUMI_CACHE_DIR="\${LUMI_CACHE_DIR:-$CACHE_DIR_DEFAULT}"

if [ -x "$INSTALL_DIR/venv/bin/lumi" ]; then
    exec "$INSTALL_DIR/venv/bin/lumi" "\$@"
fi

cd "$INSTALL_DIR"
exec "$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/main.py" "\$@"
EOF

chmod +x "$BIN_DIR/lumi"
ok "Launcher created at $BIN_DIR/lumi"

step "Configuring PATH"

add_path_line() {
    local config_file="$1"
    local export_line="export PATH=\"$BIN_DIR_EXPORT:\$PATH\""
    mkdir -p "$(dirname "$config_file")"
    touch "$config_file"
    if grep -Fq "$export_line" "$config_file"; then
        ok "$BIN_DIR already in PATH ($config_file)"
        return
    fi
    {
        echo ""
        echo "# Lumi AI"
        echo "$export_line"
    } >> "$config_file"
    ok "Added $BIN_DIR to PATH in $config_file"
}

add_path_fish() {
    local config_file="$1"
    local export_line="fish_add_path $BIN_DIR_EXPORT"
    mkdir -p "$(dirname "$config_file")"
    touch "$config_file"
    if grep -Fq "$export_line" "$config_file"; then
        ok "$BIN_DIR already in fish PATH ($config_file)"
        return
    fi
    {
        echo ""
        echo "# Lumi AI"
        echo "$export_line"
    } >> "$config_file"
    ok "Added $BIN_DIR to fish PATH in $config_file"
}

if $NO_PATH; then
    warn "Skipping PATH modification (--no-path)"
else
    SHELL_NAME="$(basename "${SHELL:-}")"
    if [ -n "$PROFILE_FILE" ]; then
        case "$PROFILE_FILE" in
            *.fish) add_path_fish "$PROFILE_FILE" ;;
            *) add_path_line "$PROFILE_FILE" ;;
        esac
    else
        case "$SHELL_NAME" in
            fish)
                add_path_fish "$HOME/.config/fish/config.fish"
                ;;
            zsh)
                add_path_line "$HOME/.zshrc"
                ;;
            bash)
                if [ -f "$HOME/.bashrc" ]; then
                    add_path_line "$HOME/.bashrc"
                elif [ -f "$HOME/.bash_profile" ]; then
                    add_path_line "$HOME/.bash_profile"
                else
                    add_path_line "$HOME/.profile"
                fi
                ;;
            *)
                if [ -f "$HOME/.profile" ]; then
                    add_path_line "$HOME/.profile"
                else
                    warn "Unknown shell '${SHELL_NAME:-unknown}' — manually add $BIN_DIR to your PATH"
                fi
                ;;
        esac
    fi
fi

echo ""
echo -e "  ${PU}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${R}"
echo -e "  ${GN}${B}Lumi installed successfully!${R}"
echo -e "  ${PU}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${R}"
echo ""
echo -e "  ${CY}Install summary:${R}"
echo -e "  ${DG}checkout:${R}     ${YE}$INSTALL_DIR${R}"
echo -e "  ${DG}launcher:${R}     ${YE}$BIN_DIR/lumi${R}"
echo -e "  ${DG}state:${R}        ${YE}$STATE_DIR_DEFAULT${R}"
echo -e "  ${DG}cache:${R}        ${YE}$CACHE_DIR_DEFAULT${R}"
echo ""
echo -e "  ${CY}Next steps:${R}"
echo -e "  ${DG}1.${R} add at least one API key to ${YE}$INSTALL_DIR/.env${R}"
echo -e "  ${DG}2.${R} reload your shell config or open a new terminal"
echo -e "  ${DG}3.${R} run ${PU}lumi${R}"
echo -e "  ${DG}4.${R} inside Lumi, run ${PU}/doctor${R} and ${PU}/model${R}"
echo ""
if ! $DEV_MODE; then
    echo -e "  ${DG}Tip:${R} re-run with ${PU}--dev${R} to install pytest, ruff, and pre-commit"
    echo ""
fi
