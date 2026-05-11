#!/usr/bin/env python3
"""
╔═══════════════════════════════════════╗
║         OMNI-DECODER  v2.0            ║
║   Multi-format encoding detective     ║
╚═══════════════════════════════════════╝
"""
import base64
import string
import argparse
import re
import sys
import os
import urllib.parse
import html
from collections import Counter

# ─── ANSI COLOR PALETTE ───────────────────────────────────────────────────────
RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"

CYAN    = "\033[96m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
RED     = "\033[91m"
MAGENTA = "\033[95m"
BLUE    = "\033[94m"
WHITE   = "\033[97m"
GRAY    = "\033[90m"

def c(text, *codes):
    return "".join(codes) + str(text) + RESET

def box(title, width=72):
    bar = "═" * (width - 2)
    title_padded = f"  {title}  "
    side = (width - len(title_padded) - 2) // 2
    top = f"╔{'═' * side}{title_padded}{'═' * (width - side - len(title_padded) - 2)}╗"
    return f"{c(top, CYAN, BOLD)}"

def box_bottom(width=72):
    return c("╚" + "═" * (width - 2) + "╝", CYAN, BOLD)

def divider(width=72, char="─"):
    return c(char * width, GRAY)

def tag(label, color=GREEN):
    return c(f"[{label}]", color, BOLD)

def confidence_bar(score, width=20):
    """Visual bar: score is 0.0–1.0"""
    filled = int(score * width)
    bar = "█" * filled + "░" * (width - filled)
    color = GREEN if score > 0.7 else YELLOW if score > 0.4 else RED
    return c(f"[{bar}]", color) + f" {int(score * 100)}%"

# ─── ENGLISH LETTER FREQUENCY SCORING ────────────────────────────────────────
ENGLISH_FREQ = {
    'e': 12.70, 't': 9.06, 'a': 8.17, 'o': 7.51, 'i': 6.97,
    'n': 6.75, 's': 6.33, 'h': 6.09, 'r': 5.99, 'd': 4.25,
    'l': 4.03, 'c': 2.78, 'u': 2.76, 'm': 2.41, 'w': 2.36,
    'f': 2.23, 'g': 2.02, 'y': 1.97, 'p': 1.93, 'b': 1.29,
    'v': 0.98, 'k': 0.77, 'j': 0.15, 'x': 0.15, 'q': 0.10, 'z': 0.07,
}

def english_score(text):
    """Returns a 0–1 confidence that the text is English."""
    letters = [c.lower() for c in text if c.isalpha()]
    if not letters:
        return 0.0
    freq = Counter(letters)
    total = sum(freq.values())
    score = sum(
        (freq[ch] / total) * ENGLISH_FREQ.get(ch, 0)
        for ch in freq
    )
    return min(score / 6.5, 1.0)   # ~6.5 is typical English corpus score

def is_printable(data):
    return all(ch in string.printable for ch in data)

# ─── MORSE CODE ───────────────────────────────────────────────────────────────
MORSE_TABLE = {
    '.-': 'A', '-...': 'B', '-.-.': 'C', '-..': 'D', '.': 'E',
    '..-.': 'F', '--.': 'G', '....': 'H', '..': 'I', '.---': 'J',
    '-.-': 'K', '.-..': 'L', '--': 'M', '-.': 'N', '---': 'O',
    '.--.': 'P', '--.-': 'Q', '.-.': 'R', '...': 'S', '-': 'T',
    '..-': 'U', '...-': 'V', '.--': 'W', '-..-': 'X', '-.--': 'Y',
    '--..': 'Z', '.----': '1', '..---': '2', '...--': '3',
    '....-': '4', '.....': '5', '-....': '6', '--...': '7',
    '---..': '8', '----.': '9', '-----': '0',
}

def decode_morse(data):
    words = data.strip().split('   ')
    decoded_words = []
    for word in words:
        chars = word.split()
        decoded = ''.join(MORSE_TABLE.get(c, '?') for c in chars)
        decoded_words.append(decoded)
    return ' '.join(decoded_words)

def looks_like_morse(data):
    return bool(re.match(r'^[.\- /]+$', data)) and ('.' in data or '-' in data)

# ─── ROT47 ────────────────────────────────────────────────────────────────────
def rot47(text):
    result = []
    for ch in text:
        o = ord(ch)
        if 33 <= o <= 126:
            result.append(chr(33 + (o - 33 + 47) % 94))
        else:
            result.append(ch)
    return ''.join(result)

# ─── BINARY STRING ────────────────────────────────────────────────────────────
def decode_binary(data):
    clean = data.replace(' ', '')
    if len(clean) % 8 != 0:
        return None
    chars = [clean[i:i+8] for i in range(0, len(clean), 8)]
    try:
        return ''.join(chr(int(b, 2)) for b in chars)
    except ValueError:
        return None

def looks_like_binary(data):
    return bool(re.match(r'^[01 ]+$', data)) and len(data.replace(' ', '')) % 8 == 0

# ─── XOR KEYED DECODE ────────────────────────────────────────────────────────
def parse_xor_key(key_str):
    """
    Parse a user-supplied XOR key into bytes. Accepts:
      - Hex with prefix:  0x1f  or  0x1f2a3b
      - Bare hex string:  1f  or  1f2a3b   (even-length, all hex digits)
      - Decimal integer:  31
      - Plaintext string: secret
    Returns (key_bytes, label_str) or raises ValueError.
    """
    s = key_str.strip()

    # 0x… prefix → hex bytes
    if s.lower().startswith('0x'):
        hex_part = s[2:]
        if len(hex_part) % 2 != 0:
            hex_part = '0' + hex_part          # pad single nibble: 0x1f → ok; 0xf → 0x0f
        key_bytes = bytes.fromhex(hex_part)
        label = f"0x{hex_part.upper()}"
        return key_bytes, label

    # Bare hex string (even length, all hex digits, not purely decimal)
    if re.match(r'^[0-9a-fA-F]+$', s) and len(s) % 2 == 0 and not s.isdigit():
        key_bytes = bytes.fromhex(s)
        label = f"0x{s.upper()}"
        return key_bytes, label

    # Pure integer (decimal)
    try:
        val = int(s)
        if 0 <= val <= 255:
            key_bytes = bytes([val])
            label = f"{val} (0x{val:02X})"
            return key_bytes, label
        else:
            raise ValueError(f"Decimal key {val} out of single-byte range; use a hex string for multi-byte keys.")
    except ValueError:
        pass

    # Plaintext string key
    key_bytes = s.encode('utf-8')
    label = f'"{s}"'
    return key_bytes, label


def xor_decode(data, key_bytes):
    """
    XOR-decode data (hex string or raw text) with key_bytes (repeating).
    Returns decoded string or raises.
    """
    if re.match(r'^[0-9a-fA-F]+$', data) and len(data) % 2 == 0:
        byte_data = bytes.fromhex(data)
    else:
        byte_data = data.encode('latin-1')   # latin-1 preserves raw bytes 0x00–0xFF

    key_len = len(key_bytes)
    decoded_bytes = bytes(b ^ key_bytes[i % key_len] for i, b in enumerate(byte_data))

    # Try UTF-8 first, fall back to latin-1
    try:
        return decoded_bytes.decode('utf-8')
    except UnicodeDecodeError:
        return decoded_bytes.decode('latin-1')

# ─── RECURSIVE CHAIN DETECTION ───────────────────────────────────────────────
def try_chain_decode(data, depth=0, max_depth=4):
    """Attempt to find a chain of encodings (e.g. base64 → url → hex)."""
    if depth >= max_depth:
        return None
    
    steps = []

    # Try base64
    if re.match(r'^[A-Za-z0-9+/]+={0,2}$', data) and len(data) % 4 == 0:
        try:
            dec = base64.b64decode(data).decode('utf-8', errors='strict')
            if is_printable(dec) and dec != data:
                steps.append(('Base64', dec))
                inner = try_chain_decode(dec, depth + 1, max_depth)
                if inner:
                    steps.extend(inner)
                return steps
        except Exception:
            pass

    # Try URL decode
    if '%' in data:
        dec = urllib.parse.unquote(data)
        if dec != data:
            steps.append(('URL', dec))
            inner = try_chain_decode(dec, depth + 1, max_depth)
            if inner:
                steps.extend(inner)
            return steps

    # Try hex
    if re.match(r'^[0-9a-fA-F]+$', data) and len(data) % 2 == 0:
        try:
            dec = bytes.fromhex(data).decode('utf-8', errors='strict')
            if is_printable(dec) and dec != data:
                steps.append(('Hex', dec))
                inner = try_chain_decode(dec, depth + 1, max_depth)
                if inner:
                    steps.extend(inner)
                return steps
        except Exception:
            pass

    return steps if steps else None

# ─── CAESAR ──────────────────────────────────────────────────────────────────
def caesar(text, shift):
    u, l = string.ascii_uppercase, string.ascii_lowercase
    result = []
    for ch in text:
        if ch in u:
            result.append(u[(u.find(ch) - shift) % 26])
        elif ch in l:
            result.append(l[(l.find(ch) - shift) % 26])
        else:
            result.append(ch)
    return ''.join(result)

# ─── ATBASH ──────────────────────────────────────────────────────────────────
def atbash(text):
    table = str.maketrans(
        string.ascii_lowercase + string.ascii_uppercase,
        string.ascii_lowercase[::-1] + string.ascii_uppercase[::-1]
    )
    return text.translate(table)

# ─── OUTPUT HELPER ───────────────────────────────────────────────────────────
class Output:
    def __init__(self, outfile=None):
        self.lines = []
        self.outfile = outfile

    def p(self, text=''):
        print(text)
        self.lines.append(re.sub(r'\033\[[0-9;]*m', '', text))  # strip ANSI for file

    def save(self):
        if self.outfile:
            with open(self.outfile, 'w') as f:
                f.write('\n'.join(self.lines))
            print(c(f"\n  Results saved → {self.outfile}", CYAN))

# ─── MAIN DECODER ────────────────────────────────────────────────────────────
class OmniDecoder:
    def __init__(self, outfile=None, show_all=False, quiet=False, xor_key=None):
        self.out = Output(outfile)
        self.show_all = show_all
        self.quiet = quiet
        self.xor_key = xor_key  # raw string from CLI, parsed on use

    def run(self, data):
        o = self.out
        W = 72

        o.p(box("OMNI-DECODER  v2.0", W))
        o.p(c("  ║", CYAN, BOLD) + f" {c('INPUT  :', GRAY)} {c(data, WHITE, BOLD)}")
        o.p(c("  ║", CYAN, BOLD) + f" {c('LENGTH :', GRAY)} {len(data)} chars")
        if self.xor_key:
            o.p(c("  ║", CYAN, BOLD) + f" {c('XOR KEY:', GRAY)} {c(self.xor_key, YELLOW, BOLD)}")
        o.p(box_bottom(W))
        o.p()

        # ── XOR KEYED DECODE (runs first if key supplied) ────────────────────
        if self.xor_key:
            try:
                key_bytes, key_label = parse_xor_key(self.xor_key)
                result = xor_decode(data, key_bytes)
                score = english_score(result)
                printable_ratio = sum(1 for ch in result if ch in string.printable) / max(len(result), 1)

                if printable_ratio >= 0.80:
                    self._hit(f"XOR  (key {key_label})", result, score, o)
                else:
                    # Show raw hex of result when output is non-printable
                    raw_hex = result.encode('latin-1').hex()
                    o.p(tag("XOR", YELLOW) + c(f"  Key {key_label} — output is non-printable", YELLOW))
                    o.p(divider())
                    o.p(f"  {c('KEY     :', GRAY)} {c(key_label, YELLOW, BOLD)}")
                    o.p(f"  {c('RAW HEX :', GRAY)} {c(raw_hex, RED)}")
                    o.p(f"  {c('AS TEXT :', GRAY)} {c(result[:80], DIM)}")
                    o.p(divider())
                    o.p()
            except Exception as e:
                o.p(tag("ERR", RED) + c(f"  XOR key parse failed: {e}", RED))
                o.p()
            o.save()
            return
        chain = try_chain_decode(data)
        if chain and len(chain) > 1:
            o.p(tag("CHAIN", MAGENTA) + c("  Multi-layer encoding detected!", MAGENTA, BOLD))
            o.p(divider())
            prev = data
            for i, (enc_type, result) in enumerate(chain):
                arrow = "  " * i + ("└─ " if i > 0 else "   ")
                o.p(f"{c(arrow, GRAY)}{c(enc_type, YELLOW, BOLD)} → {c(result, GREEN)}")
            o.p(divider())
            final = chain[-1][1]
            o.p(f"  {c('FINAL PLAINTEXT:', BOLD)} {c(final, GREEN, BOLD)}")
            o.p()

        if not self.show_all:
            # ── SMART IDENTIFICATION ──────────────────────────────────────────

            # Binary
            if looks_like_binary(data):
                result = decode_binary(data)
                if result and is_printable(result):
                    score = english_score(result)
                    self._hit("BINARY STRING", result, score, o)
                    o.save(); return

            # Morse
            if looks_like_morse(data):
                result = decode_morse(data)
                score = english_score(result)
                self._hit("MORSE CODE", result, score, o)
                o.save(); return

            # URL encoding
            if '%' in data:
                decoded = urllib.parse.unquote(data)
                if decoded != data:
                    score = english_score(decoded)
                    self._hit("URL ENCODING", decoded, score, o)
                    o.save(); return

            # HTML entities
            if '&' in data and ';' in data:
                decoded = html.unescape(data)
                if decoded != data:
                    score = english_score(decoded)
                    self._hit("HTML ENTITIES", decoded, score, o)
                    o.save(); return

            # Hex
            if re.match(r'^[0-9a-fA-F]+$', data) and len(data) % 2 == 0:
                try:
                    dec = bytes.fromhex(data).decode('utf-8', errors='ignore')
                    if is_printable(dec):
                        score = english_score(dec)
                        self._hit("HEXADECIMAL", dec, score, o)
                        o.save(); return
                except Exception:
                    pass

            # Base64
            if re.match(r'^[A-Za-z0-9+/]+={0,2}$', data) and len(data) % 4 == 0:
                try:
                    dec = base64.b64decode(data).decode('utf-8', errors='ignore')
                    if is_printable(dec):
                        score = english_score(dec)
                        self._hit("BASE64", dec, score, o)
                        o.save(); return
                except Exception:
                    pass

            # Base32
            if re.match(r'^[A-Z2-7]+=*$', data.upper()):
                try:
                    dec = base64.b32decode(data.upper()).decode('utf-8', errors='ignore')
                    score = english_score(dec)
                    self._hit("BASE32", dec, score, o)
                    o.save(); return
                except Exception:
                    pass

            # Base85
            if re.match(r'^[!-uz]+$', data):
                try:
                    dec = base64.b85decode(data).decode('utf-8', errors='ignore')
                    score = english_score(dec)
                    self._hit("BASE85", dec, score, o)
                    o.save(); return
                except Exception:
                    pass

        # ── BRUTE FORCE TABLE ─────────────────────────────────────────────────
        o.p(tag("BRUTE", YELLOW) + c("  No unique fingerprint — showing all decodings", YELLOW))
        o.p(divider())
        o.p(f"  {c('METHOD', BOLD):<34}  {c('RESULT', BOLD):<30}  {c('CONFIDENCE', BOLD)}")
        o.p(divider())

        rows = []

        # Atbash
        at = atbash(data)
        rows.append(("Atbash", at, english_score(at)))

        # ROT47
        r47 = rot47(data)
        rows.append(("ROT47", r47, english_score(r47)))

        # Caesar / ROT13
        for shift in range(1, 26):
            dec = caesar(data, shift)
            label = f"Caesar Shift {shift}"
            if shift == 13:
                label = "ROT13 (Shift 13)"
            rows.append((label, dec, english_score(dec)))

        # Sort by confidence descending
        rows.sort(key=lambda x: -x[2])

        RESULT_W = 46  # chars per line for the result column
        for method, result, score in rows:
            score_bar = confidence_bar(score, width=12)
            if len(result) <= RESULT_W:
                o.p(f"  {c(method, CYAN):<42}  {c(result, WHITE):<{RESULT_W}}  {score_bar}")
            else:
                # First line: method + first chunk + confidence
                chunks = [result[i:i+RESULT_W] for i in range(0, len(result), RESULT_W)]
                o.p(f"  {c(method, CYAN):<42}  {c(chunks[0], WHITE):<{RESULT_W}}  {score_bar}")
                # Continuation lines: blank method column, next chunks
                for chunk in chunks[1:]:
                    o.p(f"  {'':40}  {c(chunk, WHITE)}")

        o.p()
        o.p(box_bottom(W))
        o.save()

    def _hit(self, label, result, score, o):
        W = 72
        o.p(tag("HIT", GREEN) + c(f"  Identified encoding: {label}", GREEN, BOLD))
        o.p(divider())
        o.p(f"  {c('ENCODING  :', GRAY)} {c(label, YELLOW, BOLD)}")
        # Wrap long decoded values at 60 chars
        WRAP = 60
        if len(result) <= WRAP:
            o.p(f"  {c('DECODED   :', GRAY)} {c(result, GREEN, BOLD)}")
        else:
            chunks = [result[i:i+WRAP] for i in range(0, len(result), WRAP)]
            o.p(f"  {c('DECODED   :', GRAY)} {c(chunks[0], GREEN, BOLD)}")
            for chunk in chunks[1:]:
                o.p(f"  {'':12} {c(chunk, GREEN, BOLD)}")
        o.p(f"  {c('CONFIDENCE:', GRAY)} {confidence_bar(score)}")
        o.p(divider())
        o.p()


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        prog="omni-decoder",
        description=c("  Multi-format encoding detective — auto-identifies and decodes common encodings", CYAN),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
{c('examples:', YELLOW, BOLD)}
  %(prog)s -i "SGVsbG8gV29ybGQ="
  %(prog)s -i "48656c6c6f" --all
  %(prog)s -f encoded.txt -o results.txt
  %(prog)s -i "HELLO" --all
  %(prog)s -i "1a3b2c4d" -x 0x1f
  %(prog)s -i "1a3b2c4d" -x 31
  %(prog)s -i "deadbeef" -x "mykey"
        """
    )

    input_group = parser.add_mutually_exclusive_group(required=False)
    input_group.add_argument(
        "-i", "--input",
        metavar="STRING",
        help="encoded string to decode"
    )
    input_group.add_argument(
        "-f", "--file",
        metavar="FILE",
        help="read input from a file (decodes each non-empty line)"
    )

    parser.add_argument(
        "-o", "--output",
        metavar="FILE",
        help="save results to a file (ANSI stripped)"
    )
    parser.add_argument(
        "-a", "--all",
        action="store_true",
        help="skip smart detection; show full brute-force table for everything"
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="suppress banner (useful for piping)"
    )
    parser.add_argument(
        "-x", "--xor-key",
        metavar="KEY",
        dest="xor_key",
        help=(
            "XOR decode with this key — skips all other detection. "
            "Accepts: hex (0x1f or 1f2a), decimal (31), or plaintext string (secret). "
            "Multi-byte keys repeat cyclically."
        )
    )

    args = parser.parse_args()

    # Collect targets: -i > -f > stdin
    targets = []
    if args.input:
        targets.append(args.input.strip().strip("'").strip('"'))
    elif args.file:
        if not os.path.isfile(args.file):
            print(c(f"[ERROR] File not found: {args.file}", RED, BOLD))
            sys.exit(1)
        with open(args.file, 'r') as f:
            targets = [line.strip() for line in f if line.strip()]
    elif not sys.stdin.isatty():
        # Piped input: read all non-empty lines from stdin
        targets = [line.strip() for line in sys.stdin if line.strip()]
    else:
        parser.print_help()
        sys.exit(1)

    for i, target in enumerate(targets):
        decoder = OmniDecoder(
            outfile=args.output if len(targets) == 1 else None,
            show_all=args.all,
            quiet=args.quiet,
            xor_key=args.xor_key,
        )
        if len(targets) > 1:
            print(c(f"\n  ── Entry {i+1}/{len(targets)} ──", GRAY))
        decoder.run(target)


if __name__ == "__main__":
    main()
