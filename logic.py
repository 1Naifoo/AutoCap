"""
Text rules for AutoCap.

No Windows code in here, so these rules can be tested on any computer.
"""

# How many characters before the cursor we ask Windows for when a field gets focus.
CONTEXT_CHARS = 24
# How many recent characters we keep in memory (never saved anywhere).
MAX_BUFFER = 64

SENTENCE_END = ".!?"
CLOSERS = "\"')]}”’»"      # " ' ) ] } ” ’ »
OPENERS = "\"'([{“‘«"      # " ' ( [ { “ ‘ «
NEWLINES = "\r\n  \x0b"
SPACES = " \t "

# Words that end with a dot but usually do NOT end a sentence.
ABBREVIATIONS = {
    "e.g.", "i.e.", "vs.", "cf.", "approx.",
    "mr.", "mrs.", "ms.", "dr.", "prof.", "st.", "no.", "jr.", "sr.",
}

# After a lone "i", these keys turn it into "I" (e.g. "i am", "i'm", "i,").
I_TRIGGERS = set(" ,'!?;:")

_SHIFTED_DIGITS = ")!@#$%^&*("  # US layout: Shift+0 .. Shift+9

_OEM = {
    0xBE: (".", ">"), 0xBC: (",", "<"), 0xBF: ("/", "?"), 0xDE: ("'", '"'),
    0xBA: (";", ":"), 0xBD: ("-", "_"), 0xBB: ("=", "+"), 0xDB: ("[", "{"),
    0xDD: ("]", "}"), 0xDC: ("\\", "|"), 0xC0: ("`", "~"),
    0x6E: (".", "."), 0x6A: ("*", "*"), 0x6B: ("+", "+"), 0x6D: ("-", "-"), 0x6F: ("/", "/"),
}


def should_capitalize(before: str, at_field_start: bool) -> bool:
    """Should the next letter be capital, given the text right before the cursor?

    before          -- the last characters before the cursor
    at_field_start  -- True if `before` starts at the very beginning of the field
    """
    stripped = before.rstrip(SPACES)

    # Empty field (or only spaces so far).
    if not stripped:
        return at_field_start

    # Start of a new line.
    if stripped[-1] in NEWLINES:
        return True

    # We need at least one space between the end of a sentence and the next letter.
    # This keeps "google.com", "3.5" and "file.txt" lowercase.
    if len(stripped) == len(before):
        return False

    core = stripped.rstrip(CLOSERS)          # allow: He said "Hi." Then...
    if not core or core[-1] not in SENTENCE_END:
        return False

    if core.endswith(".."):                  # "wait... what" -> not a new sentence
        return False

    word = core.split()[-1].lstrip(OPENERS).lower()
    if word in ABBREVIATIONS:
        return False

    return True


def standalone_i(before: str, at_field_start: bool) -> bool:
    """Is the text before the cursor ending with a lone word 'i'?"""
    if not before.endswith("i"):
        return False
    if len(before) == 1:
        return at_field_start
    prev = before[-2]
    return prev in SPACES or prev in NEWLINES or prev in OPENERS


def char_for_vk(vk: int, shift: bool):
    """The character a non-letter key types on a US English layout, or None."""
    if vk == 0x20:
        return " "
    if 0x30 <= vk <= 0x39:
        return _SHIFTED_DIGITS[vk - 0x30] if shift else chr(vk)
    if 0x60 <= vk <= 0x69:                   # numpad digits
        return chr(vk - 0x30)
    pair = _OEM.get(vk)
    if pair:
        return pair[1] if shift else pair[0]
    return None
