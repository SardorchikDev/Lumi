"""
◆ Lumi TUI — wired 1:1 to CLI logic
   Pure Python, zero UI libs, Tokyo Night.
   Every command backed by the same modules as main.py.
"""
from __future__ import annotations

import io, os, sys, tty, termios, threading, signal, textwrap, re, time
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(dotenv_path=ROOT / ".env")

# ── CLI modules (same as main.py) ────────────────────────────────────────────
from src.chat.hf_client import (
    get_client, get_models, get_provider, set_provider, get_available_providers,
)
from src.memory.short_term import ShortTermMemory
from src.memory.longterm import (
    get_facts, add_fact, remove_fact, clear_facts, build_memory_block,
    get_persona_override, set_persona_override, clear_persona_override,
)
from src.memory.conversation_store import (
    save as session_save, load_latest, load_by_name, list_sessions, delete_session,
)
from src.prompts.builder import (
    load_persona, build_system_prompt, build_messages,
    is_coding_task, is_file_generation_task,
)
from src.agents.council import council_ask, _get_available_agents, LEAD_AGENTS, classify_task
from src.tools.search import search, search_display
from src.utils.web import fetch_url
from src.utils.plugins import load_plugins, get_commands, dispatch as plugin_dispatch
from src.utils.intelligence import (
    detect_emotion, emotion_hint, detect_topic,
    should_search, is_complex_coding_task, needs_plan_first,
)
from src.utils.autoremember import auto_extract_facts
from src.utils.export import export_md
from src.utils.filesystem import is_create_request, generate_file_plan, write_file_plan, format_creation_summary
try:
    from src.utils.tools import clipboard_get, clipboard_set
except Exception:
    clipboard_get = clipboard_set = None

# ══════════════════════════════════════════════════════════════════════════════
#  ANSI / Tokyo Night  (unchanged from your build)
# ══════════════════════════════════════════════════════════════════════════════

ESC = "\033";  CSI = ESC + "["

def _fg(h):
    h=h.lstrip("#"); return f"{CSI}38;2;{int(h[0:2],16)};{int(h[2:4],16)};{int(h[4:6],16)}m"
def _bg(h):
    h=h.lstrip("#"); return f"{CSI}48;2;{int(h[0:2],16)};{int(h[2:4],16)};{int(h[4:6],16)}m"
def _bold():      return f"{CSI}1m"
def _italic():    return f"{CSI}3m"
def _reset():     return f"{CSI}0m"
def _hide_cur():  return f"{ESC}[?25l"
def _show_cur():  return f"{ESC}[?25h"
def _alt_on():    return f"{ESC}[?1049h"
def _alt_off():   return f"{ESC}[?1049l"
def _move(r,c):   return f"{CSI}{r};{c}H"
def _erase_line():return f"{CSI}2K"
def _clr_down():  return f"{CSI}J"

BG="#1a1b26"; BG_DARK="#16161e"; BG_HL="#1f2335"; BG_POP="#24283b"
BORDER="#29294a"; MUTED="#3b3f5e"; COMMENT="#565f89"; FG_DIM="#737aa2"
FG="#a9b1d6"; FG_HI="#c0caf5"; BLUE="#7aa2f7"; CYAN="#7dcfff"
GREEN="#9ece6a"; YELLOW="#e0af68"; ORANGE="#ff9e64"; RED="#f7768e"
PURPLE="#bb9af7"; TEAL="#2ac3de"

def P(h): return _fg(h)
def B(h): return _fg(h)+_bold()
R = _reset

SPINNER_FRAMES = list("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")

AGENT_COL = {
    "gemini":CYAN,"groq":ORANGE,"openrouter":PURPLE,"mistral":RED,
    "hf":YELLOW,"github":FG_HI,"cohere":GREEN,"cloudflare":ORANGE,
}
PROV_NAME = {
    "gemini":"Gemini","groq":"Groq","openrouter":"OpenRouter",
    "mistral":"Mistral","huggingface":"HuggingFace","github":"GitHub Models",
    "cohere":"Cohere","cloudflare":"Cloudflare AI","ollama":"Ollama","council":"⚡ Council",
}
PROV_COL = {
    "gemini":CYAN,"groq":ORANGE,"openrouter":PURPLE,"mistral":RED,
    "huggingface":YELLOW,"github":FG_HI,"cohere":GREEN,
    "cloudflare":ORANGE,"ollama":FG_DIM,"council":PURPLE,
}

SLASH_CMDS = [
    ("/council",   "run all agents in parallel"),
    ("/model",     "switch model / provider"),
    ("/clear",     "clear conversation"),
    ("/retry",     "retry last message"),
    ("/undo",      "remove last exchange"),
    ("/more",      "expand last response"),
    ("/rewrite",   "rewrite last response differently"),
    ("/tl;dr",     "one-sentence summary of last reply"),
    ("/summarize", "summarize conversation so far"),
    ("/fix",       "/fix <error>  diagnose and fix"),
    ("/explain",   "/explain [file]  explain code"),
    ("/review",    "/review [file]  code review"),
    ("/web",       "/web <url> [question]  fetch and ask"),
    ("/search",    "/search <query>  web search"),
    ("/image",     "/image <path> [question]  vision"),
    ("/run",       "run code from last reply"),
    ("/edit",      "/edit <file>  edit a file with AI"),
    ("/file",      "/file <path>  load file into context"),
    ("/diff",      "diff current vs previous reply"),
    ("/agent",     "/agent <task>  autonomous mode"),
    ("/git",       "/git <subcmd>  git helper"),
    ("/save",      "/save [name]  save session"),
    ("/load",      "/load [name]  load session"),
    ("/sessions",  "list saved sessions"),
    ("/export",    "export chat as markdown"),
    ("/remember",  "/remember <fact>  save to memory"),
    ("/memory",    "show long-term memory"),
    ("/forget",    "remove a memory fact"),
    ("/persona",   "change Lumi's persona"),
    ("/todo",      "/todo add|done|list|rm  task list"),
    ("/note",      "/note add|list|search  notes"),
    ("/weather",   "/weather [location]"),
    ("/copy",      "copy last reply to clipboard"),
    ("/paste",     "paste clipboard as message"),
    ("/project",   "/project <path>  load project context"),
    ("/pdf",       "/pdf <path>  load PDF into context"),
    ("/draft",     "/draft email|message <details>"),
    ("/comment",   "/comment [file]  add code comments"),
    ("/translate", "/translate <lang>  translate last reply"),
    ("/short",     "next reply: concise"),
    ("/detailed",  "next reply: detailed"),
    ("/bullets",   "next reply: bullet points"),
    ("/tokens",    "show token usage"),
    ("/context",   "show context window info"),
    ("/plugins",   "list loaded plugins"),
    ("/help",      "show all commands"),
    ("/exit",      "quit lumi"),
]

def _hm():  return datetime.now().strftime("%H:%M")
def _ts():  return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
def _tok(t): return max(1, int(len(t.split()) * 1.35))

def _term_size():
    import shutil
    s = shutil.get_terminal_size((120, 36))
    return s.lines, s.columns

def _strip_ansi(s):
    return re.sub(r'\033\[[^a-zA-Z]*[a-zA-Z]|\033\].*?\007|\033.', '', s)

def _visible_len(s): return len(_strip_ansi(s))

_KW = {
    "def","class","return","import","from","if","elif","else","for","while",
    "in","not","and","or","True","False","None","try","except","with","as",
    "pass","break","continue","raise","yield","lambda","async","await",
    "const","let","var","function","new","self","super","type",
}

def _syntax_hi(line):
    out = []
    for tok in re.split(r'(\s+|[(){}\[\],.:;=+\-*/<>!&|#"\'`@])', line):
        if not tok: continue
        if tok.strip() in _KW:
            out.append(_fg(PURPLE)+_bold()+tok+R()+_fg(GREEN))
        elif re.match(r'^\d+(\.\d+)?$', tok):
            out.append(_fg(ORANGE)+tok+_fg(GREEN))
        elif tok.startswith('"') or tok.startswith("'"):
            out.append(_fg(YELLOW)+tok+_fg(GREEN))
        elif tok.startswith("#") or tok.startswith("//"):
            out.append(_fg(COMMENT)+_italic()+tok+R()); break
        else:
            out.append(tok)
    return "".join(out)


# ══════════════════════════════════════════════════════════════════════════════
#  Terminal input
# ══════════════════════════════════════════════════════════════════════════════

def _read_key():
    fd  = sys.stdin.fileno()
    ch  = os.read(fd, 1)
    if ch == b"\x1b":
        import select
        r, _, _ = select.select([fd], [], [], 0.05)
        if r:
            seq = os.read(fd, 16)
            full = ch + seq
            if full == b"\x1b[A":    return "UP"
            if full == b"\x1b[B":    return "DOWN"
            if full == b"\x1b[C":    return "RIGHT"
            if full == b"\x1b[D":    return "LEFT"
            if full == b"\x1b[H":    return "HOME"
            if full == b"\x1b[F":    return "END"
            if full == b"\x1b[3~":   return "DELETE"
            if full == b"\x1b[5~":   return "PGUP"
            if full == b"\x1b[6~":   return "PGDN"
            if full == b"\x1b[1;5C": return "CTRL_RIGHT"
            if full == b"\x1b[1;5D": return "CTRL_LEFT"
        return "ESC"
    if ch in (b"\r", b"\n"):  return "ENTER"
    if ch == b"\x7f":         return "BACKSPACE"
    if ch == b"\x08":         return "BACKSPACE"
    if ch == b"\x09":         return "TAB"
    if ch == b"\x0c":         return "CTRL_L"
    if ch == b"\x11":         return "CTRL_Q"
    if ch == b"\x03":         return "CTRL_C"
    if ch == b"\x0e":         return "CTRL_N"
    if ch == b"\x17":         return "CTRL_W"
    if ch == b"\x01":         return "HOME"
    if ch == b"\x05":         return "END"
    if ch == b"\x15":         return "CTRL_U"
    if ch == b"\x12":         return "CTRL_R"
    try:    return ch.decode("utf-8")
    except: return ""


# ══════════════════════════════════════════════════════════════════════════════
#  Message store
# ══════════════════════════════════════════════════════════════════════════════

class Msg:
    __slots__ = ("role","text","ts","label")
    def __init__(self, role, text, label=""):
        self.role=role; self.text=text; self.ts=_hm(); self.label=label

class Store:
    def __init__(self):
        self._lock=threading.Lock(); self._data:list[Msg]=[]
    def add(self, m):
        with self._lock: self._data.append(m); return len(self._data)-1
    def append(self, idx, chunk):
        with self._lock: self._data[idx].text += chunk
    def set_text(self, idx, text):
        with self._lock: self._data[idx].text = text
    def finalize(self, idx):
        with self._lock: self._data[idx].role = "assistant"
    def clear(self):
        with self._lock: self._data.clear()
    def snapshot(self):
        with self._lock: return list(self._data)
    def last_assistant(self):
        with self._lock:
            for m in reversed(self._data):
                if m.role == "assistant": return m.text
        return ""


# ══════════════════════════════════════════════════════════════════════════════
#  Renderer  (unchanged visuals from your build)
# ══════════════════════════════════════════════════════════════════════════════

class Renderer:
    def __init__(self, tui): self.tui=tui; self._lock=threading.Lock()
    def draw(self):
        with self._lock: self._draw()

    def _draw(self):
        rows,cols = _term_size()
        chat_w    = cols
        buf       = []; w = buf.append

        w(_hide_cur())
        w(_move(1,1))
        w(self._title_bar(cols))

        show_sb = cols >= 100 and (self.tui.agents or self.tui.current_model == "council")
        if show_sb:
            sb_w   = 28
            chat_w = cols - sb_w - 1
            self._draw_sidebar(buf, rows, cols, chat_w, sb_w)

        chat_rows  = rows - 4
        chat_lines = self._build_chat_lines(chat_w)
        total      = len(chat_lines)
        offset     = max(0, min(self.tui.scroll_offset, max(0, total - chat_rows)))
        end        = total - offset
        start      = max(0, end - chat_rows)
        chat_lines = chat_lines[start:end]
        while len(chat_lines) < chat_rows:
            chat_lines.insert(0, "")

        for i in range(chat_rows):
            w(_move(i+2, 1))
            cl  = chat_lines[i] if i < len(chat_lines) else ""
            vis = _visible_len(cl)
            pad = max(0, chat_w - vis)
            w(_bg(BG) + cl + _bg(BG) + " "*pad)

        w(self._input_area(rows, cols, chat_w))

        if self.tui.slash_visible and self.tui.slash_hits:
            w(self._slash_popup(rows, cols, chat_w))
        if self.tui.picker_visible and self.tui.picker_items:
            w(self._picker_popup(rows, cols))
        if self.tui.notification:
            w(self._notification_bar(rows, cols))

        disp_w  = chat_w - 6
        scroll  = max(0, self.tui.cur_pos - disp_w + 1)
        cur_col = 5 + (self.tui.cur_pos - scroll)
        w(_move(rows-1, min(cur_col, cols-1)))
        w(_show_cur())
        sys.stdout.write("".join(buf)); sys.stdout.flush()

    def _title_bar(self, cols):
        tui   = self.tui
        pcol  = PROV_COL.get(tui.current_model if tui.current_model=="council" else get_provider(), PURPLE)
        pname = PROV_NAME.get(tui.current_model if tui.current_model=="council" else get_provider(), get_provider())
        model = tui.current_model.split("/")[-1][:28]
        toks  = sum(_tok(m["content"]) for m in tui.memory.get())
        mode  = ""
        if tui.response_mode: mode = f" {_fg(YELLOW)}[{tui.response_mode}]{R()}"

        left = (
            _bg(BG_DARK)+B(PURPLE)+" ◆ "+R()+
            _bg(BG_DARK)+_bold()+_fg(FG_HI)+"Lumi AI"+R()+
            _bg(BG_DARK)+_fg(BORDER)+"  ─  "+R()+
            _bg(BG_DARK)+_fg(COMMENT)+"terminal assistant"+R()
        )
        right = (
            _bg(BG_DARK)+_fg(MUTED)+f"~{toks:,}tk "+R()+
            _bg(BG_DARK)+_fg(pcol)+pname+R()+
            _bg(BG_DARK)+_fg(BORDER)+" / "+R()+
            _bg(BG_DARK)+_fg(FG_DIM)+model+R()+mode+
            _bg(BG_DARK)+" "
        )
        lv   = _visible_len(left); rv = _visible_len(right)
        si   = ""
        if tui.scroll_offset > 0:
            si = _bg(BG_DARK)+_fg(YELLOW)+f" ↑{tui.scroll_offset} "+R()
        gap  = max(1, cols - lv - rv - _visible_len(si))
        return _move(1,1)+left+_bg(BG_DARK)+" "*gap+si+right+_bg(BG)+R()

    def _draw_sidebar(self, buf, rows, cols, chat_w, sb_w):
        x = chat_w+2
        def sb(row, content=""):
            buf.append(_move(row,x)+_bg(BG_DARK)+_erase_line()+content+R())
        for r in range(2, rows-3):
            buf.append(_move(r, chat_w+1)+_bg(BG_DARK)+_fg(BORDER)+"│"+R())
        r=2
        sb(r, _bg(BG_HL)+B(COMMENT)+" ◆ Council"+R()); r+=1
        sb(r); r+=1
        for ag in self.tui.agents:
            if r >= rows-4: break
            icon = (_fg(YELLOW)+SPINNER_FRAMES[ag.frame] if ag.st=="spin"
                    else _fg(GREEN)+"✓" if ag.st=="ok" else _fg(RED)+"✗")
            acol = _fg(AGENT_COL.get(ag.aid, FG))
            star = _fg(YELLOW)+" ★" if ag.lead else ""
            meta = (_fg(COMMENT)+f" {ag.conf}/10·{ag.t}s" if ag.st=="ok" and ag.conf
                    else _fg(MUTED)+" …" if ag.st=="spin" else "")
            sb(r, f" {R()}{icon} {acol}{ag.name}{R()}{star}{meta}"); r+=1
        if not self.tui.agents:
            sb(r, f"  {_fg(FG_DIM)}—{R()}"); r+=1
        sb(r); r+=1
        sb(r, _bg(BG_HL)+B(COMMENT)+" ◆ Keys"+R()); r+=1
        for kc,key,vc,val in [
            (BLUE,"Ctrl+N",FG_DIM,"model picker"),
            (BLUE,"Ctrl+L",FG_DIM,"clear chat"),
            (BLUE,"Ctrl+R",FG_DIM,"retry"),
            (BLUE,"Ctrl+W",FG_DIM,"delete word"),
            (BLUE,"/",FG_DIM,"commands"),
        ]:
            if r>=rows-3: break
            sb(r, f" {_fg(kc)}{key:<8}{_fg(vc)}{val}"); r+=1
        while r < rows-3: sb(r); r+=1

    def _build_chat_lines(self, width):
        msgs  = self.tui.store.snapshot()
        lines = []; inner = max(20, width-4)

        if not msgs:
            lines += [""]*3
            lines.append("  "+B(PURPLE)+"◆  Lumi AI"+R())
            lines.append("")
            lines.append("  "+_fg(MUTED)+"Type anything to start.  "+_fg(BLUE)+"/"+_fg(MUTED)+" for commands."+R())
            return lines

        for msg in msgs:
            lines.append("")
            if msg.role == "user":
                lines.append("  "+B(BLUE)+"you"+"  "+_fg(COMMENT)+msg.ts+R())
                for ln in textwrap.wrap(msg.text, inner) or [msg.text]:
                    lines.append("  "+_fg(FG_HI)+ln+R())
                lines.append("")

            elif msg.role in ("assistant","streaming"):
                label  = msg.label or "◆ lumi"
                cursor = (" "+_fg(CYAN)+"▊"+R()) if msg.role=="streaming" else ""
                lines.append("  "+B(PURPLE)+label+"  "+_fg(COMMENT)+msg.ts+R())
                raw_lines = msg.text.split("\n") if msg.text else [""]
                in_code=False; code_lang=""; code_w=min(inner,88)
                for ln in raw_lines:
                    if ln.startswith("```"):
                        if not in_code:
                            in_code=True; code_lang=ln[3:].strip()
                            lt = _fg(BLUE)+_bold()+code_lang+R() if code_lang else ""
                            bf = "─"*max(0, code_w-4-len(code_lang))
                            lines.append("  "+_bg(BG_DARK)+_fg(MUTED)+"┌─ "+lt+_bg(BG_DARK)+_fg(MUTED)+bf+"┐"+R())
                        else:
                            in_code=False
                            lines.append("  "+_bg(BG_DARK)+_fg(MUTED)+"└"+"─"*(code_w-2)+"┘"+R())
                        continue
                    if in_code:
                        mcc=code_w-4
                        for sl in (textwrap.wrap(ln,mcc) if len(ln)>mcc else [ln]) or [""]:
                            hi=_syntax_hi(sl); pad=max(0,mcc-len(sl))
                            lines.append("  "+_bg(BG_DARK)+_fg(MUTED)+"│ "+_fg(GREEN)+hi+R()+_bg(BG_DARK)+" "*pad+_fg(MUTED)+" │"+R())
                    elif re.match(r"^#{1,6} ", ln):
                        lvl=len(ln)-len(ln.lstrip("#")); txt=ln.lstrip("# ")
                        col=[BLUE,CYAN,TEAL,FG_HI,FG,FG_DIM][min(lvl-1,5)]
                        lines.append("  "+_fg(col)+_bold()+txt+R())
                    elif ln.startswith("> "):
                        lines.append("  "+_fg(MUTED)+"▎"+_italic()+_fg(FG_DIM)+ln[2:]+R())
                    elif re.match(r"^[-*•] ", ln):
                        lines.append("  "+_fg(PURPLE)+" •"+_fg(FG)+" "+ln[2:]+R())
                    elif re.match(r"^\d+\. ", ln):
                        m2=re.match(r"^(\d+\.\s)",ln); num=m2.group(1) if m2 else ""; rest=ln[len(num):]
                        lines.append("  "+_fg(PURPLE)+" "+num+_fg(FG)+rest+R())
                    elif re.match(r"^---+$", ln.strip()):
                        lines.append("  "+_fg(MUTED)+"─"*min(inner,60)+R())
                    elif ln.strip()=="":
                        lines.append("")
                    else:
                        rendered=self._inline(ln)
                        if len(_strip_ansi(ln))<=inner:
                            lines.append("  "+rendered+R())
                        else:
                            for wl in (textwrap.wrap(_strip_ansi(ln),inner) or [ln]):
                                lines.append("  "+_fg(FG)+wl+R())
                if cursor: lines.append("  "+cursor+R())
                lines.append("")

            elif msg.role == "system":
                for sln in msg.text.split("\n"):
                    for wl in (textwrap.wrap(sln,inner) if sln.strip() else [""]):
                        lines.append("  "+_fg(TEAL)+wl+R())
                lines.append("")

            elif msg.role == "error":
                lines.append("  "+_fg(RED)+_bold()+"⚠  "+R()+_fg(RED)+msg.text+R())
                lines.append("")

        return lines

    def _inline(self, text):
        out=""; i=0
        while i<len(text):
            if text[i:i+2]=="**" and "**" in text[i+2:]:
                end=text.index("**",i+2); out+=_bold()+_fg(FG_HI)+text[i+2:end]+R()+_fg(FG); i=end+2
            elif text[i]=="*" and i+1<len(text) and text[i+1]!="*" and "*" in text[i+1:]:
                end=text.index("*",i+1); out+=_italic()+_fg(FG_DIM)+text[i+1:end]+R()+_fg(FG); i=end+1
            elif text[i]=="`" and "`" in text[i+1:]:
                end=text.index("`",i+1); out+=_bg(BG_DARK)+_fg(CYAN)+" "+text[i+1:end]+" "+R()+_fg(FG); i=end+1
            else:
                out+=_fg(FG)+text[i]; i+=1
        return out

    def _input_area(self, rows, cols, chat_w):
        tui=self.tui
        sep=_move(rows-2,1)+_bg(BG)+_fg(MUTED)+" "+"─"*(chat_w-2)+" "+R()
        if tui.busy:
            sym=_fg(YELLOW)+"⠿"+R(); hint=_fg(MUTED)+"  generating…"+R()
        else:
            sym=_fg(COMMENT)+"›"+R(); hint=""
        txt=tui.buf; disp_w=chat_w-6
        scroll=max(0,tui.cur_pos-disp_w+1); shown=txt[scroll:scroll+disp_w]
        inp=(
            _move(rows-1,1)+_bg(BG)+"  "+sym+" "+
            _bg(BG)+_fg(FG_HI)+shown+
            _bg(BG)+" "*max(0,disp_w-len(shown))+hint+R()
        )
        empty=_move(rows,1)+_bg(BG)+" "*cols+R()
        return sep+inp+empty

    def _slash_popup(self, rows, cols, chat_w):
        hits=self.tui.slash_hits; sel=self.tui.slash_sel
        pop_w=min(66,chat_w-4); n=min(len(hits),10)
        top=rows-2-n-3; left=max(1,(cols-pop_w)//2)
        out=[]
        out.append(_move(top,left)+_bg(BG_DARK)+_fg(MUTED)+"┌"+"─"*(pop_w-2)+"┐"+R())
        hdr="  / commands   Tab=complete  Enter=run  Esc=close"
        out.append(_move(top+1,left)+_bg(BG_DARK)+_fg(MUTED)+"│"+_bg(BG_DARK)+_fg(COMMENT)+hdr+" "*max(0,pop_w-2-len(hdr))+R()+_bg(BG_DARK)+_fg(MUTED)+"│"+R())
        for i,(cmd,desc) in enumerate(hits[:10]):
            bg_=_bg(BG_HL) if i==sel else _bg(BG_DARK)
            cc=_fg(CYAN)+_bold() if i==sel else _fg(BLUE)
            dc=_fg(FG) if i==sel else _fg(MUTED)
            pad2=max(0,pop_w-2-1-18-len(desc))
            out.append(_move(top+2+i,left)+_bg(BG_DARK)+_fg(MUTED)+"│"+bg_+cc+f" {cmd:<18}"+R()+bg_+dc+desc+" "*pad2+R()+_bg(BG_DARK)+_fg(MUTED)+"│"+R())
        out.append(_move(top+2+n,left)+_bg(BG_DARK)+_fg(MUTED)+"└"+"─"*(pop_w-2)+"┘"+R())
        return "".join(out)

    def _picker_popup(self, rows, cols):
        items=self.tui.picker_items; sel=self.tui.picker_sel
        pop_w=66; left=max(3,(cols-pop_w)//2); out=[]; top=3
        out.append(_move(top,left)+_bg(BG_POP)+_fg(PURPLE)+"┌"+"─"*(pop_w-2)+"┐"+R())
        title="  ◆  LUMI  —  Model & Provider"; tp=max(0,pop_w-2-len(title))
        out.append(_move(top+1,left)+_bg(BG_POP)+_fg(PURPLE)+"│"+B(PURPLE)+title+" "*tp+R()+_bg(BG_POP)+_fg(PURPLE)+"│"+R())
        row=top+2
        for i,(kind,value,label) in enumerate(items):
            if kind=="header":
                sp=max(0,pop_w-2-len(label)-2)
                out.append(_move(row,left)+_bg(BG_POP)+_fg(PURPLE)+"│"+_bg(BG_HL)+B(COMMENT)+"  "+label+" "*sp+R()+_bg(BG_POP)+_fg(PURPLE)+"│"+R())
            else:
                is_sel=i==sel; dot="●" if is_sel else "○"
                bg_=_bg(BG_HL) if is_sel else _bg(BG_POP); lc=B(CYAN)+" " if is_sel else _fg(FG_DIM)
                vcol=PROV_COL.get(value,FG) if kind=="provider" else FG
                vs=_fg(vcol) if is_sel else _fg(FG_DIM)
                pp=max(0,pop_w-2-len(f"  {dot}  {label}"))
                out.append(_move(row,left)+_bg(BG_POP)+_fg(PURPLE)+"│"+bg_+lc+_fg(MUTED)+f"  {dot}  "+vs+label+" "*pp+R()+_bg(BG_POP)+_fg(PURPLE)+"│"+R())
            row+=1
        hint="  Esc close   ·   ↑↓ navigate   ·   Enter select"
        hp=max(0,pop_w-2-len(hint))
        out.append(_move(row,left)+_bg(BG_POP)+_fg(PURPLE)+"│"+_bg(BG_POP)+_fg(COMMENT)+hint+" "*hp+R()+_bg(BG_POP)+_fg(PURPLE)+"│"+R()); row+=1
        out.append(_move(row,left)+_bg(BG_POP)+_fg(PURPLE)+"└"+"─"*(pop_w-2)+"┘"+R())
        return "".join(out)

    def _notification_bar(self, rows, cols):
        msg=self.tui.notification; pop_w=min(len(msg)+6,cols-4)
        left=max(1,cols-pop_w-2)
        return _move(rows-5,left)+_bg(BG_POP)+_fg(CYAN)+" ◆ "+_fg(FG_HI)+msg+" "+R()


# ══════════════════════════════════════════════════════════════════════════════
#  Agent state
# ══════════════════════════════════════════════════════════════════════════════

class AgentState:
    def __init__(self,aid,name,lead=False):
        self.aid=aid; self.name=name; self.lead=lead
        self.st="spin"; self.conf=""; self.t=""; self.frame=0
    def done(self,ok,conf,t): self.st=("ok" if ok else "fail"); self.conf=conf; self.t=t


# ══════════════════════════════════════════════════════════════════════════════
#  LumiTUI  —  same state as CLI main()
# ══════════════════════════════════════════════════════════════════════════════

class LumiTUI:
    def __init__(self):
        # ── display ──────────────────────────────────────────────────────────
        self.store         = Store()
        self.agents:list[AgentState] = []
        self.buf           = ""
        self.cur_pos       = 0
        self.scroll_offset = 0
        self.slash_hits    = []
        self.slash_sel     = 0
        self.slash_visible = False
        self.picker_items  = []
        self.picker_sel    = 0
        self.picker_visible= False
        self.notification  = ""
        self._notif_timer  = None
        self._running      = False
        self._input_hist:list[str] = []
        self._hist_idx     = -1
        self._hist_draft   = ""

        # ── same state as CLI interactive loop ───────────────────────────────
        self.memory        = ShortTermMemory(max_turns=20)
        self.persona       = {}
        self.persona_override = {}
        self.system_prompt = ""
        self.client        = None
        self.current_model = "unknown"
        self.name          = "Lumi"
        self.turns         = 0
        self.last_msg      = None
        self.last_reply    = None
        self.prev_reply    = None
        self.response_mode = None   # short | detailed | bullets
        self.multiline     = False
        self.busy          = False
        self._loaded_plugins = []

        self.renderer = Renderer(self)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _make_system_prompt(self, coding_mode=False, file_mode=False):
        mem = build_memory_block()
        sp  = build_system_prompt(
            {**self.persona, **self.persona_override},
            mem, coding_mode, file_mode,
        )
        return sp

    def _sys(self, text):
        self.store.add(Msg("system", text))

    def _err(self, text):
        self.store.add(Msg("error", str(text)))

    def _notify(self, msg, duration=2.5):
        self.notification = msg
        self.redraw()
        if self._notif_timer: self._notif_timer.cancel()
        def _clear(): self.notification=""; self.redraw()
        t=threading.Timer(duration, _clear); t.daemon=True; t.start()
        self._notif_timer=t

    def redraw(self): self.renderer.draw()

    def _capture(self, fn, *args, **kwargs):
        """Run a CLI print-based function, capture its stdout, show as system msg."""
        buf=io.StringIO()
        result=None
        try:
            with redirect_stdout(buf):
                result=fn(*args, **kwargs)
        except Exception as e:
            self._err(str(e))
        out=buf.getvalue().strip()
        if out:
            clean=_strip_ansi(out)
            if clean: self._sys(clean)
        return result

    # ── TUI streaming — replaces stream_and_render ────────────────────────────

    def _tui_stream(self, messages, model, label="◆ lumi"):
        """Stream into TUI store. Handles council + normal. Returns final text."""
        idx = self.store.add(Msg("streaming","",label))

        if model == "council":
            avail   = _get_available_agents()
            user_q  = next((m["content"] for m in reversed(messages) if m["role"]=="user"),"")
            task    = classify_task(user_q)
            lead_id = LEAD_AGENTS.get(task,"gemini")
            self.agents = [AgentState(a["id"],a["name"],a["id"]==lead_id) for a in avail]

            def _cb(aid,ok,conf,t):
                for ag in self.agents:
                    if ag.aid==aid: ag.done(ok,conf,t)
                self.redraw()

            def _spin():
                frame=0
                while self.busy:
                    for ag in self.agents: ag.frame=frame
                    self.redraw()
                    frame=(frame+1)%len(SPINNER_FRAMES)
                    time.sleep(0.08)
            threading.Thread(target=_spin,daemon=True).start()

            full=refined=""
            try:
                for chunk in council_ask(messages,user_q,stream=True,debate=True,
                                         refine=True,silent=True,agent_callback=_cb):
                    if chunk.startswith("\n\n__STATS__\n"): continue
                    if chunk.startswith("\n\n__REFINED__\n\n"):
                        refined=chunk[len("\n\n__REFINED__\n\n"):]; continue
                    full+=chunk
                    self.store.append(idx,chunk)
                    self.redraw()
            except Exception as ex:
                self.store.set_text(idx,f"⚠  {ex}")
                self.store.finalize(idx)
                return f"⚠  {ex}"

            final=refined or full
            if refined: self.store.set_text(idx,final)
            self.store.finalize(idx)
            return final

        # ── normal streaming ──────────────────────────────────────────────────
        full=""
        try:
            for chunk in self.client.chat.completions.create(
                model=model, messages=messages,
                max_tokens=2048, temperature=0.7, stream=True,
            ):
                if not chunk.choices: continue
                d=chunk.choices[0].delta.content
                if d:
                    full+=d; self.store.append(idx,d); self.redraw()
        except Exception as ex:
            # quota fallback
            msg=str(ex)
            if any(x in msg for x in ("429","RESOURCE_EXHAUSTED","quota","limit: 0")):
                remaining=[p for p in get_available_providers() if p!=get_provider()]
                if remaining:
                    self._sys(f"Quota hit — switching to {remaining[0]}")
                    try:
                        set_provider(remaining[0])
                        self.client=get_client()
                        self.current_model=get_models(remaining[0])[0]
                        self.store.set_text(idx,"")
                        for chunk in self.client.chat.completions.create(
                            model=self.current_model,messages=messages,
                            max_tokens=2048,temperature=0.7,stream=True,
                        ):
                            if not chunk.choices: continue
                            d=chunk.choices[0].delta.content
                            if d:
                                full+=d; self.store.append(idx,d); self.redraw()
                    except Exception as ex2:
                        self.store.set_text(idx,f"⚠  {ex2}"); self.store.finalize(idx); return f"⚠  {ex2}"
                else:
                    self.store.set_text(idx,f"⚠  {ex}"); self.store.finalize(idx); return f"⚠  {ex}"
            else:
                self.store.set_text(idx,f"⚠  {ex}"); self.store.finalize(idx); return f"⚠  {ex}"

        self.store.finalize(idx)
        return full

    # ══════════════════════════════════════════════════════════════════════════
    #  Run — init same as CLI main()
    # ══════════════════════════════════════════════════════════════════════════

    def run(self):
        # ── init same as CLI ──────────────────────────────────────────────────
        self.persona          = load_persona()
        self.persona_override = get_persona_override()
        self.system_prompt    = self._make_system_prompt()
        self.name             = self.persona_override.get("name") or self.persona.get("name","Lumi")

        try:
            p=get_provider()
            self.current_model=get_models(p)[0]
            self.client=get_client()
        except Exception:
            self.current_model="unknown"; self.client=None

        self._loaded_plugins=load_plugins()

        # LUMI.md project context
        for md_path in [Path("LUMI.md"), Path("lumi.md")]:
            if md_path.exists():
                lumi_md=md_path.read_text().strip()
                self.system_prompt+=f"\n\n--- Project context (LUMI.md) ---\n{lumi_md}"
                break

        fd=sys.stdin.fileno(); old=termios.tcgetattr(fd)

        def _cleanup(*_):
            try: termios.tcsetattr(fd,termios.TCSADRAIN,old)
            except: pass
            sys.stdout.write(_show_cur()+_alt_off()); sys.stdout.flush()

        try: signal.signal(signal.SIGWINCH, lambda *_: self.redraw())
        except: pass
        signal.signal(signal.SIGTERM, lambda *_: (_cleanup(), sys.exit(0)))

        try:
            sys.stdout.write(_alt_on()); sys.stdout.flush()
            tty.setraw(fd)
            self._running=True
            self.redraw()
            while self._running:
                key=_read_key()
                self._handle_key(key)
                self.redraw()
        except KeyboardInterrupt:
            pass
        finally:
            # auto-save on exit
            try:
                session_save(self.memory.get())
            except: pass
            _cleanup()

    # ══════════════════════════════════════════════════════════════════════════
    #  Key handler
    # ══════════════════════════════════════════════════════════════════════════

    def _handle_key(self, key):
        if key=="ESC":
            if self.slash_visible: self.slash_visible=False
            elif self.picker_visible: self.picker_visible=False
            return
        if key in ("CTRL_Q","CTRL_C"):
            self._running=False; return
        if key in ("CTRL_N",):
            if not self.slash_visible: self._open_picker(); return
        if key=="CTRL_L":
            self.memory.clear(); self.store.clear(); self.agents.clear()
            self.last_msg=self.last_reply=self.prev_reply=None
            self.turns=0; self.busy=False; self.buf=""; self.cur_pos=0
            self.scroll_offset=0; self.slash_visible=False; self.picker_visible=False
            self._sys("Chat cleared."); return
        if key=="CTRL_R":
            threading.Thread(target=self._do_retry, daemon=True).start(); return
        if key=="CTRL_U":
            self.buf=""; self.cur_pos=0; self.slash_visible=False; return

        if key=="UP":
            if self.slash_visible:   self.slash_sel=max(0,self.slash_sel-1)
            elif self.picker_visible:
                new=self.picker_sel-1
                while new>=0 and self.picker_items[new][0]=="header": new-=1
                if new>=0: self.picker_sel=new
            elif not self.buf:       self.scroll_offset+=3
            else:                    self._hist_nav(-1)
            return
        if key=="DOWN":
            if self.slash_visible:   self.slash_sel=min(len(self.slash_hits)-1,self.slash_sel+1)
            elif self.picker_visible:
                new=self.picker_sel+1
                while new<len(self.picker_items) and self.picker_items[new][0]=="header": new+=1
                if new<len(self.picker_items): self.picker_sel=new
            elif not self.buf:       self.scroll_offset=max(0,self.scroll_offset-3)
            else:                    self._hist_nav(1)
            return
        if key=="PGUP":
            rows,_=_term_size(); self.scroll_offset+=max(1,rows-6); return
        if key=="PGDN":
            rows,_=_term_size(); self.scroll_offset=max(0,self.scroll_offset-max(1,rows-6)); return

        if key=="TAB":
            if self.slash_visible and self.slash_hits:
                cmd=self.slash_hits[self.slash_sel][0]
                self.buf=cmd+" "; self.cur_pos=len(self.buf); self.slash_visible=False
            return

        if key=="ENTER":
            if self.picker_visible: self._confirm_picker(); return
            if self.slash_visible and self.slash_hits:
                cmd=self.slash_hits[self.slash_sel][0]
                self.slash_visible=False; self.buf=""; self.cur_pos=0
                self._slash(cmd,""); return
            text=self.buf.strip()
            self.buf=""; self.cur_pos=0; self.slash_visible=False; self._hist_idx=-1
            if text and not self.busy:
                if text not in (self._input_hist[-1:] or [""]):
                    self._input_hist.append(text)
                if text.startswith("/"):
                    parts=text.split(None,1)
                    self._slash(parts[0].lower(), parts[1] if len(parts)>1 else "")
                else:
                    threading.Thread(target=self._run_message, args=(text,), daemon=True).start()
            return

        if key=="BACKSPACE":
            if self.cur_pos>0:
                self.buf=self.buf[:self.cur_pos-1]+self.buf[self.cur_pos:]; self.cur_pos-=1
            self._update_slash(); return
        if key=="DELETE":
            if self.cur_pos<len(self.buf):
                self.buf=self.buf[:self.cur_pos]+self.buf[self.cur_pos+1:]; return
        if key=="CTRL_W":
            if self.cur_pos>0:
                t=self.buf[:self.cur_pos].rstrip(); idx=t.rfind(" ")
                keep=t[:idx+1] if idx>=0 else ""
                self.buf=keep+self.buf[self.cur_pos:]; self.cur_pos=len(keep)
            self._update_slash(); return
        if key=="CTRL_RIGHT":
            i=self.cur_pos
            while i<len(self.buf) and self.buf[i]==" ": i+=1
            while i<len(self.buf) and self.buf[i]!=" ": i+=1
            self.cur_pos=i; return
        if key=="CTRL_LEFT":
            i=self.cur_pos
            while i>0 and self.buf[i-1]==" ": i-=1
            while i>0 and self.buf[i-1]!=" ": i-=1
            self.cur_pos=i; return
        if key=="LEFT":  self.cur_pos=max(0,self.cur_pos-1); return
        if key=="RIGHT": self.cur_pos=min(len(self.buf),self.cur_pos+1); return
        if key=="HOME":  self.cur_pos=0; return
        if key=="END":   self.cur_pos=len(self.buf); return

        if len(key)==1 and (key.isprintable() or ord(key)>127):
            self.buf=self.buf[:self.cur_pos]+key+self.buf[self.cur_pos:]
            self.cur_pos+=1; self._update_slash()

    def _update_slash(self):
        if self.buf.startswith("/"):
            q=self.buf.lower()
            self.slash_hits=[(c,d) for c,d in SLASH_CMDS if q in c]
            self.slash_sel=0; self.slash_visible=bool(self.slash_hits)
        else:
            self.slash_visible=False

    def _hist_nav(self, direction):
        hist=self._input_hist
        if not hist: return
        if self._hist_idx==-1: self._hist_draft=self.buf
        new=self._hist_idx+direction
        if new<-1 or new>=len(hist): return
        self._hist_idx=new
        self.buf=(self._hist_draft if new==-1 else hist[-(new+1)])
        self.cur_pos=len(self.buf)

    # ══════════════════════════════════════════════════════════════════════════
    #  Full message pipeline — mirrors CLI main loop body exactly
    # ══════════════════════════════════════════════════════════════════════════

    def _run_message(self, user_input):
        self.busy=True; self.scroll_offset=0

        # ── rebuild system prompt for this turn ───────────────────────────────
        _is_code  = is_complex_coding_task(user_input) or is_coding_task(user_input)
        _is_files = is_file_generation_task(user_input)
        if _is_code or _is_files:
            sp=self._make_system_prompt(coding_mode=_is_code, file_mode=_is_files)
        else:
            sp=self.system_prompt

        if needs_plan_first(user_input) and _is_files:
            sp+=("\n\n[INSTRUCTION: Before writing any code, output a brief one-paragraph plan: "
                 "what files you will create, what each does, and how they connect. "
                 "Then write each file completely with no placeholders.]")

        # ── file system agent ─────────────────────────────────────────────────
        if is_create_request(user_input):
            self._run_file_agent(user_input, sp); return

        # ── emotion hint ──────────────────────────────────────────────────────
        emotion=detect_emotion(user_input)
        augmented=user_input
        if emotion:
            hint=emotion_hint(emotion)
            if hint: augmented=hint+augmented

        # ── response mode prefix ──────────────────────────────────────────────
        if self.response_mode=="short":
            augmented+="\n\n[Reply concisely — 2-3 sentences max.]"
        elif self.response_mode=="detailed":
            augmented+="\n\n[Reply in detail — be thorough and comprehensive.]"
        elif self.response_mode=="bullets":
            augmented+="\n\n[Reply using bullet points only.]"
        self.response_mode=None

        # ── auto web search ───────────────────────────────────────────────────
        if should_search(user_input):
            self._sys("◆  searching the web…")
            self.redraw()
            try:
                results_text=search(user_input, fetch_top=True)
                if results_text and not results_text.startswith("[No"):
                    augmented=(
                        f"{augmented}\n\n[Web search results:]\n{results_text}\n"
                        "[Use the above to inform your answer. Cite sources where relevant.]"
                    )
                    self._sys("◆  found web results")
            except Exception: pass

        # ── plugin dispatch ───────────────────────────────────────────────────
        cmd=user_input.split()[0] if user_input.startswith("/") else None
        if cmd:
            handled,plug_result=plugin_dispatch(
                cmd,
                user_input.split(None,1)[1] if len(user_input.split(None,1))>1 else "",
                client=self.client, model=self.current_model,
                memory=self.memory, system_prompt=sp, name=self.name,
            )
            if handled:
                if plug_result: self._sys(plug_result)
                self.busy=False; self.redraw(); return

        # ── context compression ────────────────────────────────────────────────
        if len(self.memory.get())>15 and self.turns%10==0 and self.turns>0:
            def _compress():
                try:
                    old=self.memory.get()[:-4]
                    if not old: return
                    m=self.current_model if self.current_model!="council" else get_models(get_provider())[0]
                    summary_text=self._silent_call(
                        "Summarize this conversation in 3-5 sentences, keeping all key technical details:\n\n"+
                        "\n".join(f"{x['role']}: {x['content'][:200]}" for x in old),
                        m, 200,
                    )
                    if summary_text:
                        self.memory._history=(
                            [{"role":"system","content":f"[Conversation summary]: {summary_text}"}]
                            +self.memory._history[-4:]
                        )
                except: pass
            threading.Thread(target=_compress,daemon=True).start()

        # ── send ──────────────────────────────────────────────────────────────
        self.last_msg=user_input
        self.store.add(Msg("user",user_input))
        self.memory.add("user",augmented)
        messages=build_messages(sp, self.memory.get())
        self.redraw()

        raw_reply=self._tui_stream(messages, self.current_model)

        self.memory._history[-1]={"role":"user","content":user_input}
        self.memory.add("assistant",raw_reply)
        self.prev_reply=self.last_reply; self.last_reply=raw_reply
        self.turns+=1; self.busy=False; self.redraw()

        # ── auto-save every 5 turns ────────────────────────────────────────────
        if self.turns%5==0:
            threading.Thread(target=lambda: session_save(self.memory.get()), daemon=True).start()

        # ── auto-remember every 8 turns ────────────────────────────────────────
        if self.turns%8==0:
            def _bg_remember():
                try:
                    new_facts=auto_extract_facts(self.client,self.current_model,self.memory.get())
                    if new_facts:
                        self.system_prompt=self._make_system_prompt()
                except: pass
            threading.Thread(target=_bg_remember,daemon=True).start()

    def _run_file_agent(self, user_input, sp):
        """File system agent — mirrors CLI file creation flow."""
        self._sys("◆  generating file plan…"); self.redraw()
        try:
            _fs_model=self.current_model
            if _fs_model=="council": _fs_model=get_models(get_provider())[0]
            plan=generate_file_plan(user_input,self.client,_fs_model)
        except Exception as e:
            self._err(f"File plan failed: {e}"); self.busy=False; return

        if not plan:
            self._err("Couldn't generate a file plan. Try being more specific."); self.busy=False; return

        root=plan.get("root","."); files=plan.get("files",[])
        home=os.path.expanduser("~")
        lines=[f"File plan → {home}"]
        if root and root!=".": lines.append(f"  📁 {root}/")
        for f in files: lines.append(f"  📄 {f.get('path','')}")
        lines.append(""); lines.append("Type 'yes' to create, anything else to cancel.")
        self._sys("\n".join(lines)); self.busy=False; self.redraw()

        # Store pending plan for next input
        self._pending_file_plan=(plan, home)

    def _silent_call(self, prompt, model, max_tokens=300):
        try:
            r=self.client.chat.completions.create(
                model=model,messages=[{"role":"user","content":prompt}],
                max_tokens=max_tokens,temperature=0.3,stream=False,
            )
            return r.choices[0].message.content.strip()
        except: return ""

    # ══════════════════════════════════════════════════════════════════════════
    #  Slash commands — all wired to real CLI modules
    # ══════════════════════════════════════════════════════════════════════════

    def _slash(self, cmd, arg):
        # commands that need AI run in a thread
        def _bg(fn): threading.Thread(target=fn, daemon=True).start()

        match cmd:
            # ── conversation control ──────────────────────────────────────────
            case "/council":
                self.current_model="council"
                self._sys("⚡ Council mode — all agents in parallel")

            case "/clear"|"/c":
                self.memory.clear(); self.store.clear(); self.agents.clear()
                self.last_msg=self.last_reply=self.prev_reply=None
                self.turns=0; self.busy=False
                self._sys("Chat cleared.")

            case "/exit"|"/quit"|"/q":
                self._running=False

            case "/save":
                try:
                    p=session_save(self.memory.get(), arg.strip() if arg else "")
                    self._notify(f"Saved → {Path(p).name}" if p else "Saved")
                except Exception as e: self._err(str(e))

            case "/load":
                try:
                    h=(load_by_name(arg.strip()) if arg.strip() else load_latest())
                    if h:
                        self.memory._history=h; self.turns=len(h)//2
                        self._sys(f"Loaded {len(h)} messages" + (f" — {arg.strip()}" if arg.strip() else ""))
                    else: self._err("No saved session found.")
                except Exception as e: self._err(str(e))

            case "/sessions":
                s=list_sessions()
                if s:
                    lines=[f"{'#':<4}  {'Name':<28}  Date"]
                    for i,x in enumerate(s,1):
                        lines.append(f"{i:<4}  {x.get('name','?'):<28}  {x.get('date','?')}")
                    self._sys("\n".join(lines))
                else: self._sys("No saved sessions.")

            case "/export":
                if not self.memory.get(): self._err("Nothing to export.")
                else:
                    try: self._notify(f"Exported → {export_md(self.memory.get(), self.name)}")
                    except Exception as e: self._err(str(e))

            case "/undo":
                if len(self.memory._history)>=2:
                    self.memory._history=self.memory._history[:-2]
                    self.turns=max(0,self.turns-1)
                    self._sys("Last exchange removed.")
                else: self._err("Nothing to undo.")

            # ── retry / rephrase ──────────────────────────────────────────────
            case "/retry"|"/r":
                _bg(self._do_retry)

            case "/more":
                if not self.last_reply: self._err("Nothing to expand on yet."); return
                def _go():
                    self.busy=True
                    self.memory.add("user","[User wants more detail on the last response.]")
                    msgs=build_messages(self.system_prompt,self.memory.get())
                    raw=self._tui_stream(msgs,self.current_model)
                    self.memory._history[-1]={"role":"user","content":"Tell me more."}
                    self.memory.add("assistant",raw)
                    self.prev_reply=self.last_reply; self.last_reply=raw; self.turns+=1; self.busy=False; self.redraw()
                _bg(_go)

            case "/rewrite":
                if not self.last_reply: self._err("Nothing to rewrite yet."); return
                def _go():
                    self.busy=True
                    self.memory.add("user","[User wants the last response rewritten differently.]")
                    msgs=build_messages(self.system_prompt,self.memory.get())
                    raw=self._tui_stream(msgs,self.current_model)
                    self.memory._history[-1]={"role":"user","content":"Rewrite that differently."}
                    self.memory.add("assistant",raw)
                    self.prev_reply=self.last_reply; self.last_reply=raw; self.turns+=1; self.busy=False; self.redraw()
                _bg(_go)

            case "/tl;dr":
                if not self.last_reply: self._err("No reply to summarize yet."); return
                def _go():
                    self.busy=True
                    m=self.current_model if self.current_model!="council" else get_models(get_provider())[0]
                    s=self._silent_call(f"Summarize this in ONE sentence (max 20 words):\n\n{self.last_reply}",m,60)
                    if s: self._sys(f"tl;dr: {s}")
                    else: self._err("Couldn't summarize.")
                    self.busy=False; self.redraw()
                _bg(_go)

            case "/summarize":
                def _go():
                    self.busy=True
                    q="Summarize our conversation so far in a few bullet points."
                    self.memory.add("user",q)
                    msgs=build_messages(self.system_prompt,self.memory.get())
                    raw=self._tui_stream(msgs,self.current_model)
                    self.memory._history[-1]={"role":"user","content":q}
                    self.memory.add("assistant",raw)
                    self.last_reply=raw; self.turns+=1; self.busy=False; self.redraw()
                _bg(_go)

            # ── code helpers ──────────────────────────────────────────────────
            case "/fix":
                if not arg: self._err("Usage: /fix <error message>"); return
                if not self.last_reply: self._err("Nothing to fix yet."); return
                def _go():
                    self.busy=True
                    ctx=f"\n\nContext from our last exchange:\n{self.last_reply}"
                    msg=(f"I'm getting this error:\n\n```\n{arg}\n```{ctx}\n\n"
                         "Please:\n1. Explain what's causing it\n2. Show me the fix\n3. How to avoid it next time")
                    self.memory.add("user",msg)
                    msgs=build_messages(self.system_prompt,self.memory.get())
                    raw=self._tui_stream(msgs,self.current_model,f"◆ {self.name}  [fix]")
                    self.memory._history[-1]={"role":"user","content":f"/fix: {arg[:200]}"}
                    self.memory.add("assistant",raw)
                    self.last_reply=raw; self.turns+=1; self.busy=False; self.redraw()
                _bg(_go)

            case "/explain":
                def _go():
                    self.busy=True
                    if arg:
                        try:
                            code=Path(arg.strip()).expanduser().read_text(errors="replace")
                            fname=Path(arg.strip()).name
                            content=f"```\n{code}\n```"; subject=f"the file `{fname}`"
                        except Exception as e: self._err(str(e)); self.busy=False; return
                    elif self.last_reply:
                        subject="your last response"; content=self.last_reply
                    else: self._err("Nothing to explain yet."); self.busy=False; return
                    msg=(f"Please explain {subject} in detail:\n\n{content}\n\n"
                         "Walk through it step by step. Explain what each part does, why it's written that way.")
                    self.memory.add("user",msg)
                    msgs=build_messages(self.system_prompt,self.memory.get())
                    raw=self._tui_stream(msgs,self.current_model,f"◆ {self.name}  [explain]")
                    self.memory._history[-1]={"role":"user","content":f"/explain: {arg or 'last reply'}"}
                    self.memory.add("assistant",raw)
                    self.last_reply=raw; self.turns+=1; self.busy=False; self.redraw()
                _bg(_go)

            case "/review":
                def _go():
                    self.busy=True
                    if arg:
                        try:
                            code=Path(arg.strip()).expanduser().read_text(errors="replace")
                            fname=Path(arg.strip()).name
                            content=f"File: `{fname}`\n\n```\n{code}\n```"
                        except Exception as e: self._err(str(e)); self.busy=False; return
                    elif self.last_reply:
                        content=self.last_reply
                    else: self._err("Nothing to review yet."); self.busy=False; return
                    msg=(f"Review this code thoroughly:\n\n{content}\n\n"
                         "Cover: correctness, edge cases, performance, security, readability. "
                         "Be specific with line numbers / variable names where possible.")
                    self.memory.add("user",msg)
                    msgs=build_messages(self.system_prompt,self.memory.get())
                    raw=self._tui_stream(msgs,self.current_model,f"◆ {self.name}  [review]")
                    self.memory._history[-1]={"role":"user","content":f"/review: {arg or 'last reply'}"}
                    self.memory.add("assistant",raw)
                    self.last_reply=raw; self.turns+=1; self.busy=False; self.redraw()
                _bg(_go)

            case "/run":
                if not self.last_reply: self._err("No reply to run code from."); return
                import subprocess, re as _re
                code_blocks=_re.findall(r"```(?:\w+)?\n(.*?)```",self.last_reply,_re.DOTALL)
                if not code_blocks: self._err("No code blocks found in last reply."); return
                code=code_blocks[0]
                try:
                    result=subprocess.run(["python3","-c",code],capture_output=True,text=True,timeout=15)
                    out=(result.stdout+result.stderr).strip()
                    self._sys(f"$ python3 -c ...\n{out[:1000]}" if out else "$ (no output)")
                    if out:
                        self.memory.add("user",f"[Code output]: {out[:500]}")
                        self.memory.add("assistant","[Output received]")
                except subprocess.TimeoutExpired: self._err("Code timed out after 15s.")
                except Exception as e: self._err(str(e))

            case "/edit":
                if not arg: self._err("Usage: /edit <file path>"); return
                def _go():
                    self.busy=True
                    try:
                        code=Path(arg.strip()).expanduser().read_text(errors="replace")
                        fname=Path(arg.strip()).name
                    except Exception as e: self._err(str(e)); self.busy=False; return
                    msg=(f"Here is the file `{fname}`:\n\n```\n{code}\n```\n\n"
                         f"Please improve this code. Fix bugs, improve clarity, add type hints and docstrings where missing. "
                         f"Output the complete rewritten file.")
                    self.memory.add("user",msg)
                    msgs=build_messages(self.system_prompt,self.memory.get())
                    raw=self._tui_stream(msgs,self.current_model,f"◆ {self.name}  [edit {fname}]")
                    self.memory._history[-1]={"role":"user","content":f"/edit: {fname}"}
                    self.memory.add("assistant",raw); self.last_reply=raw; self.turns+=1; self.busy=False; self.redraw()
                _bg(_go)

            case "/file":
                if not arg: self._err("Usage: /file <path>"); return
                try:
                    content=Path(arg.strip()).expanduser().read_text(errors="replace")
                    fname=Path(arg.strip()).name
                    self.memory.add("user",f"Here is the file `{fname}`:\n\n```\n{content[:8000]}\n```")
                    self.memory.add("assistant",f"I've loaded `{fname}` ({len(content)} chars) into context.")
                    self._sys(f"Loaded `{fname}` into context ({len(content)} chars)")
                except Exception as e: self._err(str(e))

            case "/diff":
                if not self.last_reply or not self.prev_reply:
                    self._err("Need two replies to diff."); return
                import difflib
                a=self.prev_reply.splitlines(keepends=True)
                b=self.last_reply.splitlines(keepends=True)
                diff=list(difflib.unified_diff(a,b,fromfile="previous",tofile="current"))
                self._sys("".join(diff)[:2000] if diff else "No differences.")

            case "/comment":
                def _go():
                    self.busy=True
                    target=arg.strip()
                    if target:
                        try: code=Path(target).expanduser().read_text(errors="replace")
                        except Exception as e: self._err(str(e)); self.busy=False; return
                    elif self.last_reply:
                        code=self.last_reply
                    else: self._err("Nothing to comment."); self.busy=False; return
                    msg=f"Add clear, concise docstrings and inline comments to this code. Output the complete commented version:\n\n```\n{code}\n```"
                    self.memory.add("user",msg)
                    msgs=build_messages(self.system_prompt,self.memory.get())
                    raw=self._tui_stream(msgs,self.current_model,f"◆ {self.name}  [comment]")
                    self.memory._history[-1]={"role":"user","content":"/comment"}
                    self.memory.add("assistant",raw); self.last_reply=raw; self.turns+=1; self.busy=False; self.redraw()
                _bg(_go)

            # ── web / search ──────────────────────────────────────────────────
            case "/web":
                if not arg: self._err("Usage: /web <url> [question]"); return
                def _go():
                    self.busy=True
                    parts=arg.split(None,1); url=parts[0]; q=parts[1] if len(parts)>1 else "Summarize this page."
                    self._sys(f"◆  fetching {url}…"); self.redraw()
                    content=fetch_url(url)
                    if content.startswith(("HTTP error","Could not reach","Fetch failed")):
                        self._err(content); self.busy=False; return
                    msg=f"URL: {url}\n\nPage content:\n{content}\n\n{q}"
                    self.memory.add("user",msg)
                    msgs=build_messages(self.system_prompt,self.memory.get())
                    raw=self._tui_stream(msgs,self.current_model,f"◆ {self.name}  [web]")
                    self.memory._history[-1]={"role":"user","content":f"[web: {url}] {q}"}
                    self.memory.add("assistant",raw); self.last_reply=raw; self.turns+=1; self.busy=False; self.redraw()
                _bg(_go)

            case "/search":
                if not arg: self._err("Usage: /search <query>"); return
                def _go():
                    self.busy=True
                    self._sys(f"◆  searching: {arg}…"); self.redraw()
                    try:
                        results,_=search_display(arg)
                        lines=[f"Results for: {arg}",""]
                        for i,r in enumerate(results,1):
                            lines.append(f"{i}. {r['title']}")
                            lines.append(f"   {r['url']}")
                            if r.get("snippet"): lines.append(f"   {r['snippet'][:120]}")
                            lines.append("")
                        self._sys("\n".join(lines))
                        ctx=search(arg,fetch_top=True)
                        self.memory.add("user",f"I searched for: {arg}\n\n{ctx}\n\nSummarize the key findings briefly.")
                        msgs=build_messages(self.system_prompt,self.memory.get())
                        raw=self._tui_stream(msgs,self.current_model,f"◆ {self.name}  [search]")
                        self.memory._history[-1]={"role":"user","content":f"Search: {arg}"}
                        self.memory.add("assistant",raw); self.last_reply=raw; self.turns+=1
                    except Exception as e: self._err(str(e))
                    self.busy=False; self.redraw()
                _bg(_go)

            case "/image":
                if not arg: self._err("Usage: /image <path> [question]"); return
                def _go():
                    self.busy=True
                    parts=arg.split(None,1); path=parts[0]; q=parts[1] if len(parts)>1 else "Describe this image in detail."
                    path=os.path.expanduser(path)
                    if not os.path.exists(path): self._err(f"File not found: {path}"); self.busy=False; return
                    try:
                        import base64, mimetypes
                        mime=mimetypes.guess_type(path)[0] or "image/jpeg"
                        b64=base64.b64encode(open(path,"rb").read()).decode()
                    except Exception as e: self._err(str(e)); self.busy=False; return
                    vmsg={"role":"user","content":[{"type":"image_url","image_url":{"url":f"data:{mime};base64,{b64}"}},{"type":"text","text":q}]}
                    msgs=build_messages(self.system_prompt,self.memory.get())+[vmsg]
                    try:
                        resp=self.client.chat.completions.create(model=self.current_model,messages=msgs,max_tokens=1024,temperature=0.7,stream=False)
                        raw=resp.choices[0].message.content.strip() if resp.choices else ""
                        if raw:
                            idx=self.store.add(Msg("assistant",raw,f"◆ {self.name}  [image]"))
                            self.memory.add("user",f"[image: {os.path.basename(path)}] {q}")
                            self.memory.add("assistant",raw); self.last_reply=raw; self.turns+=1
                    except Exception as e: self._err(str(e))
                    self.busy=False; self.redraw()
                _bg(_go)

            # ── memory / persona ──────────────────────────────────────────────
            case "/remember":
                if not arg: self._err("Usage: /remember <fact>"); return
                n=add_fact(arg.strip())
                self.system_prompt=self._make_system_prompt()
                self._notify(f"Remembered — {n} fact{'s' if n!=1 else ''} stored")

            case "/memory":
                facts=get_facts()
                if facts:
                    lines=["Long-term memory:",""]
                    for i,f in enumerate(facts,1): lines.append(f"  {i}. {f}")
                    self._sys("\n".join(lines))
                else: self._sys("No facts stored yet. Use /remember <fact>")

            case "/forget":
                facts=get_facts()
                if not facts: self._err("No facts to remove."); return
                lines=["Facts (type number to remove):",""]
                for i,f in enumerate(facts,1): lines.append(f"  {i}. {f}")
                self._sys("\n".join(lines)+"\n\nType: /forget <number>")

            case "/persona":
                overrides=get_persona_override()
                lines=["Current persona:",""]
                for k,v in ({**self.persona,**overrides}).items():
                    if isinstance(v,str) and v: lines.append(f"  {k}: {v}")
                lines+= ["","Use /persona name=<name> or /persona reset to clear"]
                if "=" in arg:
                    k,v=arg.split("=",1)
                    k,v=k.strip(),v.strip()
                    overrides[k]=v; set_persona_override(overrides)
                    self.persona_override=overrides
                    self.name=overrides.get("name") or self.persona.get("name","Lumi")
                    self.system_prompt=self._make_system_prompt()
                    self._notify(f"Persona updated: {k}={v}")
                elif arg.strip()=="reset":
                    clear_persona_override()
                    self.persona_override={}
                    self.system_prompt=self._make_system_prompt()
                    self._notify("Persona reset to default")
                else:
                    self._sys("\n".join(lines))

            # ── response mode ─────────────────────────────────────────────────
            case "/short":    self.response_mode="short";    self._notify("Next reply: concise")
            case "/detailed": self.response_mode="detailed"; self._notify("Next reply: detailed")
            case "/bullets":  self.response_mode="bullets";  self._notify("Next reply: bullets")

            # ── translate ─────────────────────────────────────────────────────
            case "/translate":
                if not arg: self._err("Usage: /translate <language>"); return
                if not self.last_reply: self._err("No reply to translate yet."); return
                def _go():
                    self.busy=True
                    q=f"Translate your last response into {arg}. Output only the translation."
                    self.memory.add("user",q)
                    msgs=build_messages(self.system_prompt,self.memory.get())
                    raw=self._tui_stream(msgs,self.current_model,f"◆ {self.name}  [translate → {arg}]")
                    self.memory._history[-1]={"role":"user","content":f"Translate to {arg}"}
                    self.memory.add("assistant",raw); self.last_reply=raw; self.turns+=1; self.busy=False; self.redraw()
                _bg(_go)

            # ── info ──────────────────────────────────────────────────────────
            case "/tokens":
                toks=sum(_tok(m["content"]) for m in self.memory.get())
                turns=sum(1 for m in self.memory.get() if m["role"]=="user")
                self._sys(f"Tokens ≈ {toks:,}   ·   Turns: {turns}   ·   Messages: {len(self.memory.get())}")

            case "/context":
                sp_toks=_tok(self.system_prompt)
                hist_toks=sum(_tok(m["content"]) for m in self.memory.get())
                self._sys(f"Context window estimate:\n  System prompt: ~{sp_toks:,} tokens\n  History: ~{hist_toks:,} tokens\n  Total: ~{sp_toks+hist_toks:,} tokens\n  History turns: {len(self.memory.get())}")

            case "/plugins":
                cmds=get_commands()
                if cmds:
                    lines=["Loaded plugins:",""]
                    for c,d in cmds.items(): lines.append(f"  {c:<22} {d}")
                    self._sys("\n".join(lines))
                else: self._sys("No plugins loaded.  Drop .py files in ~/Lumi/plugins/")

            # ── todo / note ───────────────────────────────────────────────────
            case "/todo":
                from src.utils.todo import todo_add,todo_list,todo_done,todo_remove,todo_clear_done
                parts=(arg or "list").split(None,1)
                sub=parts[0]; rest=parts[1] if len(parts)>1 else ""
                if sub=="add":   self._capture(todo_add,rest)
                elif sub=="done":self._capture(todo_done,rest)
                elif sub=="rm":  self._capture(todo_remove,rest)
                elif sub=="clear":self._capture(todo_clear_done)
                else:
                    buf=io.StringIO()
                    with redirect_stdout(buf): todo_list()
                    self._sys(_strip_ansi(buf.getvalue().strip()) or "No todos yet.")

            case "/note":
                from src.utils.notes import note_add,note_list,note_search,note_remove
                parts=(arg or "list").split(None,1)
                sub=parts[0]; rest=parts[1] if len(parts)>1 else ""
                if sub=="add":    self._capture(note_add,rest)
                elif sub=="search":self._capture(note_search,rest)
                elif sub=="rm":   self._capture(note_remove,rest)
                else:
                    buf=io.StringIO()
                    with redirect_stdout(buf): note_list()
                    self._sys(_strip_ansi(buf.getvalue().strip()) or "No notes yet.")

            case "/weather":
                from src.utils.tools import get_weather
                def _go():
                    self.busy=True
                    try:
                        result=get_weather(arg.strip() if arg else "")
                        self._sys(result or "Could not fetch weather.")
                    except Exception as e: self._err(str(e))
                    self.busy=False; self.redraw()
                _bg(_go)

            # ── clipboard ─────────────────────────────────────────────────────
            case "/copy":
                text=self.last_reply or ""
                if not text: self._err("No reply to copy."); return
                try:
                    if clipboard_set: clipboard_set(text)
                    else:
                        import subprocess
                        for cmd2 in [["xclip","-selection","clipboard"],["xsel","--clipboard","--input"],["wl-copy"],["pbcopy"]]:
                            try:
                                p=subprocess.Popen(cmd2,stdin=subprocess.PIPE)
                                p.communicate(text.encode())
                                if p.returncode==0: break
                            except FileNotFoundError: continue
                    self._notify("Copied to clipboard ✓")
                except Exception as e: self._err(str(e))

            case "/paste":
                try:
                    text=clipboard_get() if clipboard_get else None
                    if not text:
                        import subprocess
                        for cmd2 in [["xclip","-selection","clipboard","-o"],["xsel","--clipboard","--output"],["wl-paste"],["pbpaste"]]:
                            try:
                                result=subprocess.run(cmd2,capture_output=True,text=True)
                                if result.returncode==0: text=result.stdout.strip(); break
                            except FileNotFoundError: continue
                    if text:
                        threading.Thread(target=self._run_message,args=(text,),daemon=True).start()
                    else: self._err("Clipboard is empty or clipboard tool not found.")
                except Exception as e: self._err(str(e))

            # ── project / PDF ─────────────────────────────────────────────────
            case "/project":
                if not arg: self._err("Usage: /project <path>"); return
                try:
                    from src.utils.tools import load_project
                    summary=load_project(arg.strip(),self.memory)
                    self._sys(summary or f"Loaded project: {arg.strip()}")
                except Exception as e: self._err(str(e))

            case "/pdf":
                if not arg: self._err("Usage: /pdf <path>"); return
                try:
                    from src.utils.tools import read_pdf
                    content=read_pdf(arg.strip())
                    self.memory.add("user",f"PDF content:\n{content[:8000]}")
                    self.memory.add("assistant","[PDF loaded into context]")
                    self._sys(f"Loaded PDF: {Path(arg.strip()).name} ({len(content)} chars)")
                except Exception as e: self._err(str(e))

            # ── draft ─────────────────────────────────────────────────────────
            case "/draft":
                if not arg: self._err("Usage: /draft email|message <details>"); return
                def _go():
                    self.busy=True
                    msg=f"Write a professional {arg}. Be concise and clear."
                    self.memory.add("user",msg)
                    msgs=build_messages(self.system_prompt,self.memory.get())
                    raw=self._tui_stream(msgs,self.current_model,f"◆ {self.name}  [draft]")
                    self.memory._history[-1]={"role":"user","content":f"/draft: {arg[:100]}"}
                    self.memory.add("assistant",raw); self.last_reply=raw; self.turns+=1; self.busy=False; self.redraw()
                _bg(_go)

            # ── git ───────────────────────────────────────────────────────────
            case "/git":
                import subprocess as _sp
                subcmd=arg.strip() or "status"
                def _go():
                    self.busy=True
                    if subcmd in ("status","log","diff","branch"):
                        try:
                            result=_sp.run(["git"]+subcmd.split(),capture_output=True,text=True)
                            out=(result.stdout+result.stderr).strip()
                            self._sys(f"$ git {subcmd}\n{out[:2000]}" if out else f"$ git {subcmd}\n(no output)")
                        except Exception as e: self._err(str(e))
                        self.busy=False; self.redraw(); return
                    # AI git helper
                    try:
                        st=_sp.run(["git","status"],capture_output=True,text=True).stdout
                        lg=_sp.run(["git","log","--oneline","-10"],capture_output=True,text=True).stdout
                    except: st=lg=""
                    msg=f"Git {subcmd}\n\nStatus:\n{st}\n\nLog:\n{lg}\n\nHelp me with: {subcmd}"
                    self.memory.add("user",msg)
                    msgs=build_messages(self.system_prompt,self.memory.get())
                    raw=self._tui_stream(msgs,self.current_model,f"◆ {self.name}  [git]")
                    self.memory._history[-1]={"role":"user","content":f"/git: {subcmd}"}
                    self.memory.add("assistant",raw); self.last_reply=raw; self.turns+=1; self.busy=False; self.redraw()
                _bg(_go)

            # ── agent ─────────────────────────────────────────────────────────
            case "/agent":
                if not arg: self._err("Usage: /agent <task>"); return
                def _go():
                    self.busy=True
                    from src.agents.agent import run_agent
                    try:
                        result=run_agent(arg,self.client,self.current_model,self.memory,self.system_prompt,self.name)
                        if result:
                            idx=self.store.add(Msg("assistant",result,f"◆ {self.name}  [agent]"))
                            self.memory.add("user",f"[agent task]: {arg}")
                            self.memory.add("assistant",result); self.last_reply=result; self.turns+=1
                    except Exception as e: self._err(str(e))
                    self.busy=False; self.redraw()
                _bg(_go)

            # ── model / provider ──────────────────────────────────────────────
            case "/model"|"/m":
                self._open_picker()

            # ── help ──────────────────────────────────────────────────────────
            case "/help":
                lines=["Commands:",""]
                for c,d in SLASH_CMDS: lines.append(f"  {c:<18} {d}")
                lines+=["","Keybinds:","",
                    "  Ctrl+N        model picker",
                    "  Ctrl+L        clear chat",
                    "  Ctrl+R        retry last message",
                    "  Ctrl+W        delete word",
                    "  Ctrl+U        clear input",
                    "  ↑↓            scroll (empty) or input history",
                    "  PgUp/PgDn     scroll pages",
                    "  Ctrl+←/→      jump word",
                    "  Tab           complete slash command",
                    "  Ctrl+Q        quit",
                ]
                self._sys("\n".join(lines))

            case _:
                # Try plugin dispatch for unknown /commands
                handled,plug_result=plugin_dispatch(
                    cmd, arg,
                    client=self.client, model=self.current_model,
                    memory=self.memory, system_prompt=self.system_prompt, name=self.name,
                )
                if handled:
                    if plug_result: self._sys(plug_result)
                else:
                    self._err(f"Unknown command: {cmd}  (try /help)")

    # ── retry ─────────────────────────────────────────────────────────────────

    def _do_retry(self):
        if self.busy: return
        for m in reversed(self.memory.get()):
            if m["role"]=="user":
                text=m["content"]
                self.memory._history=self.memory._history[:-2] if len(self.memory._history)>=2 else []
                self.turns=max(0,self.turns-1)
                self.busy=True
                self.store.add(Msg("user",text))
                self.memory.add("user",text)
                msgs=build_messages(self.system_prompt,self.memory.get())
                raw=self._tui_stream(msgs,self.current_model)
                self.memory._history[-1]={"role":"user","content":text}
                self.memory.add("assistant",raw)
                self.prev_reply=self.last_reply; self.last_reply=raw; self.turns+=1; self.busy=False; self.redraw()
                return
        self._err("Nothing to retry.")

    # ── model picker ──────────────────────────────────────────────────────────

    def _open_picker(self):
        items=[]
        try:
            avail=get_available_providers()
            models=get_models(get_provider()) if self.current_model not in ("council","unknown") else []
            items.append(("header","","── Provider ──────────────────"))
            for p in avail: items.append(("provider",p,PROV_NAME.get(p,p)))
            if len(avail)>=2: items.append(("provider","council","⚡ Council  (all agents in parallel)"))
            if models:
                items.append(("header","",f"── Models  ({PROV_NAME.get(get_provider(),get_provider())}) ──"))
                for m in models[:16]: items.append(("model",m,m.split("/")[-1]))
        except Exception: pass
        self.picker_items=items; self.picker_sel=0; self.picker_visible=True

    def _confirm_picker(self):
        if not self.picker_items: self.picker_visible=False; return
        kind,value,label=self.picker_items[self.picker_sel]
        if kind=="header": return
        if kind=="provider":
            if value=="council":
                self.current_model="council"
            else:
                try:
                    set_provider(value); self.client=get_client()
                    ms=get_models(value); self.current_model=ms[0] if ms else ""
                    self._open_picker(); return
                except Exception: pass
            self._sys(f"Provider → {PROV_NAME.get(self.current_model, self.current_model)}")
        elif kind=="model":
            self.current_model=value
            self._notify(f"Model → {value.split('/')[-1]}")
        self.picker_visible=False


# ── entry ─────────────────────────────────────────────────────────────────────

def launch():
    LumiTUI().run()

if __name__ == "__main__":
    launch()
