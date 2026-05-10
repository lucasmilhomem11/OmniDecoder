# OmniDecoder
A command-line tool for identifying and decoding encoded strings. It automatically fingerprints common encodings and decodes them, or falls back to a ranked brute-force table when no fingerprint is found.
# omni-decoder

A command-line tool for identifying and decoding encoded strings. It automatically fingerprints common encodings and decodes them, or falls back to a ranked brute-force table when no fingerprint is found. Zero dependencies — standard library only.

---

## Requirements

- Python 3.6+
- No third-party packages

---

## Usage

```
python3 omni_decoder.py -i <STRING> [OPTIONS]
python3 omni_decoder.py -f <FILE>   [OPTIONS]
```

### Flags

| Flag | Long form | Description |
|---|---|---|
| `-i STRING` | `--input` | Encoded string to decode |
| `-f FILE` | `--file` | Read input from file, one entry per line |
| `-o FILE` | `--output` | Save results to file (ANSI codes stripped) |
| `-x KEY` | `--xor-key` | XOR decode with a known key (see XOR section) |
| `-a` | `--all` | Skip smart detection, show full brute-force table |
| `-q` | `--quiet` | Suppress the banner |

`-i` and `-f` are mutually exclusive. One is required.

---

## How It Works

### Smart detection mode (default)

The tool inspects the input for structural fingerprints — character sets, length constraints, delimiters — and attempts to identify the encoding before decoding. If a match is found, it prints a `[HIT]` result with the decoded value and a confidence score based on English letter frequency analysis.

Detections are attempted in this order:

1. Binary string (`01001000 01100101 ...`)
2. Morse code (`.-  -...  -.-.`)
3. URL encoding (`Hello%20World`)
4. HTML entities (`&lt;div&gt;`)
5. Hexadecimal (`48656c6c6f`)
6. Base64 (`SGVsbG8=`)
7. Base32 (`JBSWY3DPEB3W64TMMQ======`)
8. Base85

### Chain detection

Before smart detection runs, the tool checks whether the input is multi-layer encoded — for example, Base64 wrapping a hex string. If a chain is found, it prints each decode step with arrows and displays the final plaintext separately. The chain detector recurses up to 4 layers deep.

### Brute force mode

If no fingerprint is matched, or if `--all` is passed, the tool runs every classical cipher against the input and displays all results in a ranked table, sorted by English confidence score from highest to lowest. Long results wrap onto continuation lines.

Ciphers included in the brute-force table:

- Caesar shifts 1-25 (ROT13 labeled separately at shift 13)
- Atbash
- ROT47

### Confidence scoring

Every result is scored using English letter frequency analysis (ETAOIN SHRDLU distribution). The score is displayed as a filled bar and a percentage. Color indicates confidence level:

- Green: above 70%
- Yellow: 40-70%
- Red: below 40%

This scoring determines sort order in the brute-force table and gives a rough signal for whether a decode result is meaningful plaintext.

---

## XOR Decoding

XOR requires a known key, so it is not included in the brute-force table. Use `-x` to supply one. When a key is provided, all other detection is skipped and only the XOR result is shown.

The key can be provided in several formats:

```bash
# Hex with 0x prefix (single or multi-byte)
python3 omni_decoder.py -i "577a737370..." -x 0x1f
python3 omni_decoder.py -i "ciphertext"   -x 0x1f2a3b

# Bare hex string (even length, contains non-decimal hex chars)
python3 omni_decoder.py -i "ciphertext" -x 1f2a

# Decimal integer (0-255, single byte only)
python3 omni_decoder.py -i "ciphertext" -x 31

# Plaintext string (multi-byte, repeats cyclically)
python3 omni_decoder.py -i "ciphertext" -x "secret"
```

The input is treated as a hex string if it matches `[0-9a-fA-F]+` with even length, otherwise as raw text. Multi-byte keys repeat across the input cyclically. If the output is non-printable (suggesting a wrong key), the raw hex of the result is shown instead.

---

## File Mode

When using `-f`, each non-empty line in the file is decoded as a separate entry. Results are printed sequentially with an entry counter. The `-o` output flag only applies when decoding a single input; it is ignored in file mode with multiple entries.

```
# encoded.txt
SGVsbG8gV29ybGQ=
48656c6c6f
Uryyb Jbeyq
```

```bash
python3 omni_decoder.py -f encoded.txt
```

---

## Examples

```bash
# Auto-detect and decode a Base64 string
python3 omni_decoder.py -i "SGVsbG8gV29ybGQ="

# Auto-detect a hex string
python3 omni_decoder.py -i "48656c6c6f20576f726c64"

# Decode ROT13 (shows up ranked first in brute-force table)
python3 omni_decoder.py -i "Uryyb Jbeyq"

# Force brute-force table even if a fingerprint would match
python3 omni_decoder.py -i "SGVsbG8=" --all

# XOR decode with a known single-byte key
python3 omni_decoder.py -i "577a737370" -x 0x1f

# XOR decode with a plaintext multi-byte key
python3 omni_decoder.py -i "230015070a593c0a0b0701" -x "key"

# Decode a file and save results
python3 omni_decoder.py -f targets.txt -o results.txt

# Decode Morse code
python3 omni_decoder.py -i ".... . .-.. .-.. ---"

# Decode a binary string
python3 omni_decoder.py -i "01001000 01100101 01101100 01101100 01101111"
```

---

## Output Format

All output is color-coded using ANSI escape codes. When saving to a file with `-o`, ANSI codes are stripped automatically so the file is clean plaintext.

Tags used in output:

- `[HIT]` — encoding identified, result shown
- `[CHAIN]` — multi-layer encoding detected, decode tree shown
- `[BRUTE]` — no fingerprint found, brute-force table displayed
- `[XOR]` — XOR result (non-printable output case)
- `[ERR]` — key parse error or other failure

---

## Limitations

- Confidence scoring is based on English letter frequency. Non-English plaintext will score low even if correctly decoded.
- The chain detector covers Base64, URL, and hex only. Other encoding combinations will not be detected as chains.
- XOR brute force is intentionally not included. If you do not know the key, use a dedicated tool like `xortool`.
- Base85 detection can produce false positives on short inputs due to its wide character set overlapping with other formats.
- The `-o` flag does not apply when processing multiple lines from a file.
