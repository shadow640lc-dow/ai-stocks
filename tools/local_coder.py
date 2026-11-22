#!/usr/bin/env python3 
 
from __future__ import annotations 
 
import os 
import re 
import sys 
from pathlib import Path 
 
from langchain_ollama import ChatOllama 
 
 
# ================================================================ 
# CONFIGURATION 
# ================================================================ 
 
ROOT = Path(__file__).resolve().parents[1] 
 
MODEL = os.environ.get( 
    "LOCAL_CODER_MODEL", 
    "qwen2.5-coder:7b", 
) 
 
MAX_FILE_SIZE = 200_000 
MAX_MATCHES = 80 
MAX_EVIDENCE_FILES = 20 
MAX_EVIDENCE_LINES_PER_FILE = 80 
CONTEXT_LINES = 3 
 
 
# Directories that must never be searched. 
IGNORED_DIRS = { 
    ".git", 
    ".venv", 
    "venv", 
    "__pycache__", 
    "node_modules", 
    ".pytest_cache", 
    ".mypy_cache", 
} 
 
 
# Local Coder backup/version files must never become 
# source evidence. They are historical copies, not 
# current project implementation. 
IGNORED_FILE_NAMES = { 
    "local_coder.py.backup", 
    "local_coder.py.before_verify", 
    "local_coder.py.before_symbol_upgrade", 
    "local_coder.py.before_evidence_fix", 
    "local_coder.py.pre_asset_fix", 
} 
 
 
# ================================================================ 
# TERMINAL STYLE 
# ================================================================ 
 
RESET = "\033[0m" 
 
BLUE = "\033[38;5;39m" 
CYAN = "\033[38;5;51m" 
GREEN = "\033[38;5;46m" 
YELLOW = "\033[38;5;220m" 
RED = "\033[38;5;203m" 
WHITE = "\033[97m" 
DIM = "\033[2m" 
BOLD = "\033[1m" 
 
 
def style(text: str, color: str) -> str: 
    return f"{color}{text}{RESET}" 
 
 
def blue(text: str) -> str: 
    return style(text, BLUE) 
 
 
def cyan(text: str) -> str: 
    return style(text, CYAN) 
 
 
def green(text: str) -> str: 
    return style(text, GREEN) 
 
 
def yellow(text: str) -> str: 
    return style(text, YELLOW) 
 
 
def red(text: str) -> str: 
    return style(text, RED) 
 
 
def bold(text: str) -> str: 
    return style(text, BOLD + WHITE) 
 
 
# ================================================================ 
# TERMINAL PANELS 
# ================================================================ 
 
WIDTH = 76 
 
 
def line(char: str = "═") -> str: 
    return char * WIDTH 
 
 
def header(title: str, subtitle: str = "") -> None: 
    print() 
    print(blue("╔" + "═" * WIDTH + "╗")) 
    print( 
        blue("║") 
        + bold(title.center(WIDTH)) 
        + blue("║") 
    ) 
 
    if subtitle: 
        print( 
            blue("║") 
            + cyan(subtitle.center(WIDTH)) 
            + blue("║") 
        ) 
 
    print(blue("╚" + "═" * WIDTH + "╝")) 
 
 
def section(title: str) -> None: 
    print() 
    print(blue("┌─ ") + bold(title)) 
    print(blue("│")) 
 
 
def footer() -> None: 
    print() 
    print(blue("╔" + "═" * WIDTH + "╗")) 
    print( 
        blue("║") 
        + green( 
            "🛡 READ-ONLY RESEARCH MODE · NO FILES MODIFIED".center(WIDTH) 
        ) 
        + blue("║") 
    ) 
    print(blue("╚" + "═" * WIDTH + "╝")) 
    print() 
 
 
# ================================================================ 
# OLLAMA 
# ================================================================ 
 
def get_model() -> ChatOllama: 
    return ChatOllama( 
        model=MODEL, 
        temperature=0, 
    ) 
 
 
def ask_qwen(prompt: str) -> str: 
    model = get_model() 
    response = model.invoke(prompt) 
    return response.content 
 
 
# ================================================================ 
# FILE SAFETY 
# ================================================================ 
 
def is_safe_path(path: Path) -> bool: 
    try: 
        path.resolve().relative_to(ROOT.resolve()) 
        return True 
    except ValueError: 
        return False 
 
 
def is_ignored_path(path: Path) -> bool: 
    """ 
    Return True when a path belongs to an ignored directory 
    or is one of Local Coder's historical backup files. 
    """ 
 
    if any(part in IGNORED_DIRS for part in path.parts): 
        return True 
 
    if path.name in IGNORED_FILE_NAMES: 
        return True 
 
    return False 
 
 
def find_file(user_path: str) -> Path | None: 
    requested = user_path.strip() 
 
    if not requested: 
        return None 
 
    path = Path(requested).expanduser() 
 
    if not path.is_absolute(): 
        path = ROOT / path 
 
    try: 
        path = path.resolve() 
    except OSError: 
        return None 
 
    if not is_safe_path(path): 
        return None 
 
    if is_ignored_path(path): 
        return None 
 
    if not path.exists(): 
        return None 
 
    if not path.is_file(): 
        return None 
 
    return path 
 
 
def read_file(path: Path) -> str: 
    size = path.stat().st_size 
 
    if size > MAX_FILE_SIZE: 
        raise ValueError( 
            f"File is too large to safely analyze " 
            f"({size:,} bytes > {MAX_FILE_SIZE:,} bytes)." 
        ) 
 
    return path.read_text( 
        encoding="utf-8", 
        errors="replace", 
    ) 
 
 
def is_probably_binary(path: Path) -> bool: 
    try: 
        with path.open("rb") as handle: 
            sample = handle.read(4096) 
 
        if b"\x00" in sample: 
            return True 
 
        return False 
 
    except OSError: 
        return True 
 
 
# ================================================================ 
# PROJECT OVERVIEW 
# ================================================================ 
 
def list_project_files() -> list[Path]: 
    files: list[Path] = [] 
 
    try: 
        for path in ROOT.rglob("*"): 
            if not path.is_file(): 
                continue 
 
            if is_ignored_path(path): 
                continue 
 
            try: 
                if not is_safe_path(path): 
                    continue 
            except OSError: 
                continue 
 
            files.append(path) 
 
    except OSError as exc: 
        print( 
            red( 
                f"✗ Could not enumerate project files: {exc}" 
            ) 
        ) 
 
    return sorted(files) 
 
 
def show_project() -> None: 
    header( 
        "🧠 LOCAL CODER", 
        "QWEN 2.5 CODER · AI-STOCKS PROJECT MAP", 
    ) 
 
    print( 
        f"  Root: {cyan(str(ROOT))}" 
    ) 
 
    print( 
        f"  Model: {green(MODEL)}" 
    ) 
 
    print( 
        yellow( 
            "  READ-ONLY — project files are never modified." 
        ) 
    ) 
 
    section("FILES") 
 
    files = list_project_files() 
 
    if not files: 
        print( 
            yellow( 
                "  No project files found." 
            ) 
        ) 
 
    for path in files[:200]: 
        try: 
            relative = path.relative_to(ROOT) 
        except ValueError: 
            continue 
 
        print( 
            f"  {green('•')} {relative}" 
        ) 
 
    if len(files) > 200: 
        print( 
            yellow( 
                f"\n  ... {len(files) - 200:,} additional files omitted" 
            ) 
        ) 
 
    footer() 
 
 
# ================================================================ 
# SOURCE SEARCH 
# ================================================================ 
 
def search_repository(term: str) -> None: 
    term = term.strip() 
 
    if not term: 
        print( 
            yellow( 
                "Usage: search <term>" 
            ) 
        ) 
        return 
 
    header( 
        "🔎 LOCAL CODER", 
        "SOURCE SEARCH · READ-ONLY", 
    ) 
 
    print( 
        f"  Repository: {cyan(str(ROOT))}" 
    ) 
 
    print( 
        f"  Search term: {cyan(term)}" 
    ) 
 
    print() 
 
    print( 
        green( 
            "  READ-ONLY — source files are searched but never modified." 
        ) 
    ) 
 
    section("🔎 SOURCE MATCHES") 
 
    matches = 0 
 
    lowered_term = term.lower() 
 
    for path in list_project_files(): 
        if matches >= MAX_MATCHES: 
            break 
 
        try: 
            if path.stat().st_size > MAX_FILE_SIZE: 
                continue 
 
            if is_probably_binary(path): 
                continue 
 
            source = read_file(path) 
 
        except (OSError, UnicodeError, ValueError): 
            continue 
 
        lines = source.splitlines() 
 
        for line_number, source_line in enumerate(lines, start=1): 
            if lowered_term in source_line.lower(): 
                try: 
                    relative = path.relative_to(ROOT) 
                except ValueError: 
                    continue 
 
                print( 
                    f"  {green('•')} " 
                    f"{relative}:{line_number}" 
                ) 
 
                print( 
                    f"    {DIM}{source_line.strip()}{RESET}" 
                ) 
 
                matches += 1 
 
                if matches >= MAX_MATCHES: 
                    break 
 
    if matches == 0: 
        print( 
            yellow( 
                "  No source matches found." 
            ) 
        ) 
 
    elif matches >= MAX_MATCHES: 
        print( 
            yellow( 
                f"\n  Output limited to {MAX_MATCHES} matches." 
            ) 
        ) 
 
    print() 
    print( 
        green( 
            "  ✓ Search complete — NO FILES MODIFIED." 
        ) 
    ) 
 
    footer() 
 
 
# ================================================================ 
# SOURCE EVIDENCE 
# ================================================================ 
 
def normalize_words(text: str) -> list[str]: 
    return [ 
        word.lower() 
        for word in re.findall( 
            r"[A-Za-z0-9_./:-]+", 
            text, 
        ) 
        if len(word) >= 3 
    ] 
 
 
def extract_explicit_symbols(question: str) -> list[str]: 
    """ 
    Extract likely market symbols from the user's question. 
 
    This does not determine whether a symbol is supported. 
    It only gives exact symbols higher evidence priority. 
    """ 
 
    known_symbols = { 
        "SPX", 
        "NDQ", 
        "DJI", 
        "VIX", 
        "DXY", 
        "AAPL", 
        "TSLA", 
        "NFLX", 
        "USOIL", 
        "GOLD", 
        "SILVER", 
        "EURUSD", 
        "GBPUSD", 
        "USDJPY", 
        "BTCUSD", 
        "BTCUSDT", 
        "ETHUSD", 
    } 
 
    words = re.findall( 
        r"\b[A-Za-z][A-Za-z0-9._-]*\b", 
        question.upper(), 
    ) 
 
    return [ 
        word 
        for word in words 
        if word in known_symbols 
    ] 
 
 
def rank_terms(question: str) -> list[str]: 
    stop_words = { 
        "the", 
        "and", 
        "are", 
        "this", 
        "that", 
        "with", 
        "from", 
        "which", 
        "what", 
        "where", 
        "does", 
        "actually", 
        "used", 
        "use", 
        "using", 
        "project", 
        "source", 
        "code", 
        "actual", 
        "supported", 
        "support", 
        "files", 
        "file", 
        "function", 
        "functions", 
        "class", 
        "classes", 
        "into", 
        "have", 
        "has", 
        "been", 
        "for", 
        "by", 
        "of", 
        "to", 
        "in", 
        "on", 
        "a", 
        "an", 
        "is", 
        "it", 
    } 
 
    terms: list[str] = [] 
 
    explicit_symbols = extract_explicit_symbols(question) 
 
    for symbol in explicit_symbols: 
        lowered = symbol.lower() 
 
        if lowered not in terms: 
            terms.append(lowered) 
 
    for word in normalize_words(question): 
        if word in stop_words: 
            continue 
 
        if word not in terms: 
            terms.append(word) 
 
    return terms 
 
 
def extract_evidence( 
    path: Path, 
    terms: list[str], 
) -> list[tuple[int, str]]: 
 
    try: 
        if path.stat().st_size > MAX_FILE_SIZE: 
            return [] 
 
        if is_probably_binary(path): 
            return [] 
 
        source = read_file(path) 
 
    except (OSError, UnicodeError, ValueError): 
        return [] 
 
    lines = source.splitlines() 
 
    matched_lines: set[int] = set() 
 
    for index, source_line in enumerate(lines): 
        lowered = source_line.lower() 
 
        if any( 
            term.lower() in lowered 
            for term in terms 
        ): 
            start = max( 
                0, 
                index - CONTEXT_LINES, 
            ) 
 
            end = min( 
                len(lines), 
                index + CONTEXT_LINES + 1, 
            ) 
 
            for line_index in range( 
                start, 
                end, 
            ): 
                matched_lines.add(line_index) 
 
    if not matched_lines: 
        return [] 
 
    ordered = sorted(matched_lines) 
 
    if len(ordered) > MAX_EVIDENCE_LINES_PER_FILE: 
        ordered = ordered[ 
            :MAX_EVIDENCE_LINES_PER_FILE 
        ] 
 
    return [ 
        ( 
            index + 1, 
            lines[index], 
        ) 
        for index in ordered 
    ] 
 
 
def collect_source_evidence( 
    question: str, 
) -> tuple[list[dict], list[str]]: 
 
    terms = rank_terms(question) 
 
    evidence: list[dict] = [] 
    inspected_files: list[str] = [] 
 
    files = list_project_files() 
 
    priority_terms = set(terms) 
 
    for extra in ( 
        "yfinance", 
        "yf.Ticker", 
        "yf.download", 
        "Ticker(", 
        "download(", 
        "market_data", 
        "market-data", 
        "data_source", 
        "data source", 
        "provider", 
        "price", 
        "quote", 
        "ticker", 
        "symbol", 
        "exchange", 
        "index", 
        "crypto", 
        "forex", 
    ): 
        priority_terms.add( 
            extra.lower() 
        ) 
 
    def evidence_score(path: Path) -> int: 
        try: 
            if path.stat().st_size > MAX_FILE_SIZE: 
                return -1 
 
            if is_probably_binary(path): 
                return -1 
 
            source = read_file(path).lower() 
 
        except (OSError, UnicodeError, ValueError): 
            return -1 
 
        score = 0 
 
        for term in terms: 
            if term.lower() in source: 
                score += 10 
 
        for term in priority_terms: 
            if term in source: 
                score += 1 
 
        suffix = path.suffix.lower() 
 
        if suffix == ".py": 
            score += 8 
 
        elif suffix in { 
            ".ts", 
            ".tsx", 
            ".js", 
            ".jsx", 
        }: 
            score += 4 
 
        return score 
 
    ranked_files = sorted( 
        files, 
        key=lambda path: ( 
            evidence_score(path), 
            str(path), 
        ), 
        reverse=True, 
    ) 
 
    for path in ranked_files: 
 
        if len(evidence) >= MAX_EVIDENCE_FILES: 
            break 
 
        try: 
            relative = str( 
                path.relative_to(ROOT) 
            ) 
 
        except ValueError: 
            continue 
 
        snippets = extract_evidence( 
            path, 
            terms, 
        ) 
 
        if not snippets: 
            continue 
 
        inspected_files.append( 
            relative 
        ) 
 
        evidence.append( 
            { 
                "path": relative, 
                "lines": snippets, 
            } 
        ) 
 
    return ( 
        evidence, 
        inspected_files, 
    ) 
 
 
def format_evidence( 
    evidence: list[dict], 
) -> str: 
 
    chunks: list[str] = [] 
 
    for item in evidence: 
 
        chunks.append( 
            f"FILE: {item['path']}" 
        ) 
 
        chunks.append( 
            "SOURCE EVIDENCE:" 
        ) 
 
        for ( 
            line_number, 
            source_line, 
        ) in item["lines"]: 
 
            chunks.append( 
                f"{line_number}: {source_line}" 
            ) 
 
        chunks.append("") 
 
    return "\n".join(chunks) 
 
 
# ================================================================ 
# SOURCE-VERIFIED INSPECTION 
# ================================================================ 
 
def inspect_question(question: str) -> None: 
    question = question.strip() 
 
    if not question: 
        print( 
            yellow( 
                "Usage: inspect <question>" 
            ) 
        ) 
        return 
 
    header( 
        "🔬 LOCAL CODER", 
        "SOURCE-VERIFIED PROJECT ANALYSIS", 
    ) 
 
    print( 
        f"  Repository: {cyan(str(ROOT))}" 
    ) 
 
    print() 
 
    print( 
        green( 
            "  READ-ONLY — source files are inspected but never modified." 
        ) 
    ) 
 
    section("🔎 COLLECTING SOURCE EVIDENCE") 
 
    try: 
        ( 
            evidence, 
            inspected_files, 
        ) = collect_source_evidence( 
            question 
        ) 
 
    except Exception as exc: 
        print( 
            red( 
                f"✗ Source inspection failed: {exc}" 
            ) 
        ) 
 
        footer() 
        return 
 
    print( 
        f"  Actual evidence files found: " 
        f"{green(str(len(evidence)))}" 
    ) 
 
    if not evidence: 
 
        print( 
            yellow( 
                "  No relevant source evidence was found." 
            ) 
        ) 
 
        print( 
            yellow( 
                "  Result should be treated as UNKNOWN." 
            ) 
        ) 
 
        footer() 
        return 
 
    section("📁 SOURCE EVIDENCE") 
 
    for item in evidence: 
        path = item["path"] 
 
        line_numbers = [ 
            str(line_number) 
            for line_number, _ in item["lines"] 
        ] 
 
        print( 
            f"  {green('•')} {path}" 
        ) 
 
        print( 
            f"    Lines: {', '.join(line_numbers)}" 
        ) 
 
    source_evidence = format_evidence( 
        evidence 
    ) 
 
    prompt = f""" 
You are a senior software engineer performing 
STRICT SOURCE-VERIFIED analysis of the AI Stocks 
project. 
 
Repository root: 
{ROOT} 
 
The user asked: 
 
{question} 
 
IMPORTANT SAFETY AND ACCURACY RULES: 
 
1. This is READ-ONLY analysis. 
2. Do not modify files. 
3. Do not invent files. 
4. Do not invent functions. 
5. Do not invent classes. 
6. Do not invent APIs. 
7. Do not invent endpoints. 
8. Do not invent directories. 
9. Do not invent capabilities. 
10. Use ONLY the supplied source evidence. 
11. Never treat documentation alone as proof of 
    implementation. 
12. Never infer support merely because a function 
    accepts a string, ticker, symbol, or parameter. 
13. Do not assume a market, ticker, asset, provider, 
    endpoint, or feature is supported unless the 
    supplied implementation evidence proves it. 
14. Distinguish implementation from tests, 
    fixtures, documentation, examples, comments, 
    backups, and generated files. 
15. If the evidence cannot prove something, 
    classify it as UNKNOWN. 
 
CLASSIFICATION: 
 
Use exactly these categories when appropriate: 
 
VERIFIED SUPPORTED 
- The supplied implementation source directly 
  proves the capability exists. 
 
VERIFIED NOT SUPPORTED 
- The supplied implementation source directly 
  proves the requested capability is explicitly 
  rejected, excluded, unavailable, or unsupported. 
 
UNKNOWN 
- The supplied evidence cannot prove support or 
  non-support. 
 
For every VERIFIED result: 
 
- Give the exact existing relative file path. 
- Give the exact function or class when identifiable. 
- Give the exact source line number(s). 
- Explain why the source proves the result. 
 
For UNKNOWN: 
 
- Explain what evidence is missing. 
- Do not invent what the missing implementation 
  contains. 
 
If multiple symbols/assets/features are asked about, 
evaluate them independently. 
 
Do not turn a test fixture into proof of production 
support. 
 
Do not turn documentation into proof of production 
implementation. 
 
At the end, provide: 
 
EXACT FILES INSPECTED 
 
List every actual source file supplied below. 
 
SUPPLIED SOURCE EVIDENCE: 
 
{source_evidence} 
""" 
 
    section( 
        "🧠 QWEN · SOURCE-GROUNDED ANALYSIS" 
    ) 
 
    try: 
        answer = ask_qwen(prompt) 
 
        print(answer) 
 
    except Exception as exc: 
        print( 
            red( 
                f"✗ Ollama request failed: {exc}" 
            ) 
        ) 
 
        print( 
            yellow( 
                "  Source collection completed, but " 
                "Qwen could not be reached." 
            ) 
        ) 
 
    section("📁 ACTUAL FILES INSPECTED") 
 
    for path in inspected_files: 
        print( 
            f"  • {path}" 
        ) 
 
    footer() 
 
 
# ================================================================ 
# FILE ANALYSIS 
# ================================================================ 
 
def analyze_file(user_path: str) -> None: 
    path = find_file(user_path) 
 
    if path is None: 
        print( 
            red( 
                f"\n✗ File not found or not allowed: " 
                f"{user_path}" 
            ) 
        ) 
 
        return 
 
    try: 
        source = read_file(path) 
 
    except PermissionError: 
        print( 
            red( 
                "\n✗ Permission denied while reading file." 
            ) 
        ) 
 
        return 
 
    except ValueError as exc: 
        print( 
            red( 
                f"\n✗ {exc}" 
            ) 
        ) 
 
        return 
 
    except (OSError, UnicodeError) as exc: 
        print( 
            red( 
                f"\n✗ Could not read file: {exc}" 
            ) 
        ) 
 
        return 
 
    if is_probably_binary(path): 
        print( 
            red( 
                "\n✗ Binary files cannot be analyzed." 
            ) 
        ) 
 
        return 
 
    try: 
        relative = path.relative_to(ROOT) 
 
    except ValueError: 
        print( 
            red( 
                "\n✗ File is outside the project root." 
            ) 
        ) 
 
        return 
 
    header( 
        f"🔍 ANALYZING {relative}", 
        f"LOCAL MODEL · {MODEL}", 
    ) 
 
    print( 
        green( 
            "  READ-ONLY — this file will not be modified." 
        ) 
    ) 
 
    prompt = ( 
        "You are a senior Python software engineer " 
        "reviewing an existing software project.\n\n" 
 
        "IMPORTANT:\n" 
        "- This is READ-ONLY analysis.\n" 
        "- Do not modify files.\n" 
        "- Do not invent code that is not present.\n" 
        "- Do not assume missing functionality exists.\n" 
        "- Preserve existing business logic.\n" 
        "- Identify uncertainty explicitly.\n" 
        "- Use the supplied source as the authority.\n\n" 
 
        f"Repository root:\n{ROOT}\n\n" 
 
        f"File being reviewed:\n{relative}\n\n" 
 
        "Source:\n" 
        "```text\n" 
        f"{source}\n" 
        "```\n\n" 
 
        "Analyze the file using these sections:\n\n" 
 
        "1. PURPOSE\n" 
        "2. HOW IT WORKS\n" 
        "3. IMPORTANT FUNCTIONS / CLASSES\n" 
        "4. DEPENDENCIES\n" 
        "5. INPUTS AND OUTPUTS\n" 
        "6. CONNECTIONS TO OTHER PROJECT COMPONENTS\n" 
        "7. POTENTIAL BUGS OR RISKS\n" 
        "8. SAFE IMPROVEMENT IDEAS\n" 
        "9. TESTING RECOMMENDATIONS\n\n" 
 
        "Do not make changes." 
    ) 
 
    section( 
        "🧠 QWEN CODE REVIEW" 
    ) 
 
    try: 
        answer = ask_qwen(prompt) 
 
        print(answer) 
 
    except Exception as exc: 
        print( 
            red( 
                f"✗ Ollama request failed: {exc}" 
            ) 
        ) 
 
    footer() 
 
 
# ================================================================ 
# GENERAL PROJECT QUESTIONS 
# ================================================================ 
 
def ask_general(question: str) -> None: 
    question = question.strip() 
 
    if not question: 
        print( 
            yellow( 
                "Enter a question." 
            ) 
        ) 
 
        return 
 
    header( 
        "🧠 LOCAL CODER", 
        "QWEN 2.5 CODER · PROJECT ASSISTANT", 
    ) 
 
    print( 
        yellow( 
            "  GENERAL QUESTION — NOT AUTOMATICALLY SOURCE-VERIFIED." 
        ) 
    ) 
 
    print( 
        cyan( 
            "  For source verification, use: inspect <question>" 
        ) 
    ) 
 
    prompt = ( 
        "You are a senior software engineer helping " 
        "with the AI Stocks project.\n\n" 
 
        f"Project root: {ROOT}\n\n" 
 
        "The user is asking a general project question.\n" 
 
        "This is NOT automatically source-verified.\n\n" 
 
        "Rules:\n" 
        "- Answer clearly and technically.\n" 
        "- Do not modify files.\n" 
        "- Do not invent project functionality.\n" 
        "- Do not claim source verification unless " 
        "source evidence was supplied.\n" 
        "- If the question requires checking actual " 
        "implementation, recommend the inspect command.\n\n" 
 
        f"USER QUESTION:\n{question}\n" 
    ) 
 
    section("🧠 QWEN") 
 
    try: 
        answer = ask_qwen(prompt) 
 
        print(answer) 
 
    except Exception as exc: 
        print( 
            red( 
                f"✗ Ollama request failed: {exc}" 
            ) 
        ) 
 
    footer() 
 
 
# ================================================================ 
# HELP 
# ================================================================ 
 
def show_help() -> None: 
    header( 
        "🧠 LOCAL CODER", 
        "QWEN 2.5 CODER · AI-STOCKS DEVELOPMENT ASSISTANT", 
    ) 
 
    section("COMMANDS") 
 
    print( 
        f"  {cyan('inspect'):<25}" 
        "Show project files" 
    ) 
 
    print( 
        f"  {cyan('inspect <question>'):<25}" 
        "Verify a question against actual source" 
    ) 
 
    print( 
        f"  {cyan('search <term>'):<25}" 
        "Search actual project source" 
    ) 
 
    print( 
        f"  {cyan('file <path>'):<25}" 
        "Analyze one project file" 
    ) 
 
    print( 
        f"  {cyan('ask <question>'):<25}" 
        "Ask a general project question" 
    ) 
 
    print( 
        f"  {cyan('help'):<25}" 
        "Show this help" 
    ) 
 
    print( 
        f"  {cyan('quit / exit'):<25}" 
        "Close Local Coder" 
    ) 
 
    section("EXAMPLES") 
 
    print( 
        "  inspect" 
    ) 
 
    print( 
        "  inspect which files handle market data?" 
    ) 
 
    print( 
        "  inspect which market data sources are actually used?" 
    ) 
 
    print( 
        "  inspect which of AAPL TSLA BTCUSD are supported?" 
    ) 
 
    print( 
        "  search yfinance" 
    ) 
 
    print( 
        "  search yf.Ticker" 
    ) 
 
    print( 
        "  search covered_call" 
    ) 
 
    print( 
        "  file app/backend/services/decision_engine.py" 
    ) 
 
    print( 
        "  file app/backend/services/covered_call_scanner.py" 
    ) 
 
    print( 
        "  file src/utils/display.py" 
    ) 
 
    print( 
        "  ask how does the Decision Engine connect to the scanner?" 
    ) 
 
    print( 
        "  ask where is the portfolio decision generated?" 
    ) 
 
    footer() 
 
 
# ================================================================ 
# COMMAND LOOP 
# ================================================================ 
 
def command_loop() -> None: 
    header( 
        "🧠 LOCAL CODER", 
        "QWEN 2.5 CODER · AI-STOCKS DEVELOPMENT ASSISTANT", 
    ) 
 
    print( 
        f"  Model: {green(MODEL)}" 
    ) 
 
    print( 
        f"  Root:  {cyan(str(ROOT))}" 
    ) 
 
    print() 
 
    print( 
        yellow( 
            "  READ-ONLY MODE — Local Coder will not modify your files." 
        ) 
    ) 
 
    print() 
 
    print( 
        "  Type " 
        + cyan("help") 
        + " for commands." 
    ) 
 
    while True: 
 
        try: 
            command = input( 
                f"\n{blue('LOCAL-CODER')} " 
                f"{cyan('›')} " 
            ).strip() 
 
        except (EOFError, KeyboardInterrupt): 
            print() 
            print( 
                green( 
                    "Goodbye bro. 👊" 
                ) 
            ) 
            break 
 
        if not command: 
            continue 
 
        lowered = command.lower() 
 
        # -------------------------------------------------------- 
        # QUIT 
        # -------------------------------------------------------- 
 
        if lowered in { 
            "quit", 
            "exit", 
            "q", 
        }: 
            print( 
                green( 
                    "\nGoodbye bro. 👊" 
                ) 
            ) 
 
            break 
 
        # -------------------------------------------------------- 
        # HELP 
        # -------------------------------------------------------- 
 
        if lowered in { 
            "help", 
            "?", 
        }: 
            show_help() 
            continue 
 
        # -------------------------------------------------------- 
        # INSPECT 
        # -------------------------------------------------------- 
 
        if lowered == "inspect": 
            show_project() 
            continue 
 
        if lowered.startswith("inspect "): 
            question = command[ 
                len("inspect "): 
            ].strip() 
 
            inspect_question(question) 
            continue 
 
        # -------------------------------------------------------- 
        # SEARCH 
        # -------------------------------------------------------- 
 
        if lowered.startswith("search "): 
            term = command[ 
                len("search "): 
            ].strip() 
 
            search_repository(term) 
            continue 
 
        # -------------------------------------------------------- 
        # FILE 
        # -------------------------------------------------------- 
 
        if lowered.startswith("file "): 
            target = command[ 
                len("file "): 
            ].strip() 
 
            analyze_file(target) 
            continue 
 
        # -------------------------------------------------------- 
        # ASK 
        # -------------------------------------------------------- 
 
        if lowered.startswith("ask "): 
            question = command[ 
                len("ask "): 
            ].strip() 
 
            ask_general(question) 
            continue 
 
        # -------------------------------------------------------- 
        # UNKNOWN 
        # -------------------------------------------------------- 
 
        print( 
            yellow( 
                "Unknown command. Type 'help'." 
            ) 
        ) 
 
 
# ================================================================ 
# MAIN 
# ================================================================ 
 
def main() -> None: 
    command_loop() 
 
 
if __name__ == "__main__": 
    main() 
