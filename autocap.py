"""
AutoCap - capitalizes the first letter of every sentence, in any app on Windows.

What it capitalizes:
  * the first letter in an empty text field
  * the first letter after  .  !  ?  followed by a space
  * the first letter on a new line
  * a lone "i" -> "I"   (can be turned off from the tray menu)

Safety:
  * never touches password fields (it asks Windows' UI Automation)
  * does nothing while Ctrl / Alt / Win are held (shortcuts stay normal)
  * does nothing when the keyboard layout isn't English (e.g. Arabic)
  * skips code editors, terminals and remote desktop (see BLOCKED_APPS)

Privacy: only the last 64 typed characters are kept, in memory, so the app
knows where a sentence starts. Nothing is written to disk or sent anywhere.
"""

import ctypes
import os
import sys
import threading
import time
import traceback
from ctypes import wintypes as wt

if sys.platform != "win32":
    sys.exit("AutoCap only runs on Windows.")

from logic import (
    CONTEXT_CHARS, I_TRIGGERS, MAX_BUFFER,
    char_for_vk, should_capitalize, standalone_i,
)

# --------------------------------------------------------------------------
# Settings you can edit
# --------------------------------------------------------------------------

# Apps where AutoCap stays off (lowercase .exe names).
BLOCKED_APPS = {
    # code editors / IDEs
    "code.exe", "cursor.exe", "devenv.exe", "idea64.exe", "pycharm64.exe",
    "webstorm64.exe", "studio64.exe", "sublime_text.exe", "notepad++.exe",
    # terminals
    "windowsterminal.exe", "cmd.exe", "powershell.exe", "pwsh.exe",
    "conhost.exe", "openconsole.exe", "wezterm-gui.exe", "alacritty.exe",
    # remote desktop / VMs (keys belong to the other computer)
    "mstsc.exe", "vmconnect.exe", "virtualboxvm.exe", "anydesk.exe", "teamviewer.exe",
    # password managers
    "keepass.exe", "keepassxc.exe", "1password.exe", "bitwarden.exe",
}


APP_NAME = "AutoCap"
APP_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), APP_NAME)
SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")
LOG_FILE = os.path.join(APP_DIR, "autocap.log")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


class Settings:
    """Only these options are saved (to %APPDATA%\\AutoCap\\settings.json). Never any typing."""
    enabled = True
    fix_i = True
    # When an app doesn't tell us the text before the cursor, should a mouse
    # click count as "start of field"? Off = safer (no wrong capitals mid-sentence).
    cap_after_click = False
    first_run = True
    debug = False   # diagnostic log: records decisions, never what you type

    _FIELDS = ("enabled", "fix_i", "cap_after_click", "first_run", "debug")

    def load(self):
        import json
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k in self._FIELDS:
                if isinstance(data.get(k), bool):
                    setattr(self, k, data[k])
        except (OSError, ValueError):
            pass

    def save(self):
        import json
        try:
            os.makedirs(APP_DIR, exist_ok=True)
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump({k: getattr(self, k) for k in self._FIELDS}, f, indent=2)
        except OSError:
            traceback.print_exc()


settings = Settings()


def launch_command():
    """The command Windows should run at sign-in."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return f'"{pythonw}" "{os.path.abspath(__file__)}"'


def starts_with_windows():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def set_start_with_windows(on):
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, launch_command())
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                except FileNotFoundError:
                    pass
    except OSError:
        traceback.print_exc()


class Diag:
    """Diagnostic log (tray menu > Diagnostic log). Writes WHY a letter was or
    wasn't capitalized, which app, and timings. Never the text you type."""
    _lines = []
    _lock = threading.Lock()

    @classmethod
    def log(cls, msg):
        if settings.debug:
            with cls._lock:
                cls._lines.append(f"{time.strftime('%H:%M:%S')}.{int(time.time() * 1000) % 1000:03d} {msg}")

    @classmethod
    def flush(cls):
        with cls._lock:
            lines, cls._lines = cls._lines, []
        if not lines:
            return
        try:
            os.makedirs(APP_DIR, exist_ok=True)
            with open(os.path.join(APP_DIR, "diagnostic.log"), "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except OSError:
            pass


def setup_logging():
    """Without a console window, errors go to %APPDATA%\\AutoCap\\autocap.log (no keystrokes)."""
    if sys.stderr is not None and not getattr(sys, "frozen", False):
        return
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 1_000_000:
            os.remove(LOG_FILE)
        log = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
        log.write(f"\n--- AutoCap started {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        sys.stdout = sys.stderr = log
    except OSError:
        pass

SETTLE_DELAY = 0.025     # wait for the app to move the cursor after a click/Enter
RESULT_TIMEOUT = 0.10    # max time a key waits for field info (rarely used)

# --------------------------------------------------------------------------
# Win32 declarations
# --------------------------------------------------------------------------

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
ULONG_PTR = ctypes.c_size_t

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
HC_ACTION = 0
WM_QUIT = 0x0012
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN, WM_XBUTTONDOWN = 0x0201, 0x0204, 0x0207, 0x020B
LLKHF_INJECTED = 0x10
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
EVENT_OBJECT_FOCUS = 0x8005
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002
QS_ALLINPUT = 0x04FF
PM_REMOVE = 0x0001
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

VK_BACK, VK_TAB, VK_RETURN = 0x08, 0x09, 0x0D
VK_SHIFT, VK_CONTROL, VK_MENU = 0x10, 0x11, 0x12
VK_DELETE, VK_LWIN, VK_RWIN = 0x2E, 0x5B, 0x5C
MODIFIER_KEYS = {0x10, 0x11, 0x12, 0x14, 0x5B, 0x5C, 0x90, 0x91,
                 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5}
MEDIA_KEYS = set(range(0xA6, 0xB8))   # volume, play/pause, browser keys...

# Marks keys that AutoCap itself typed, so we ignore them.
MAGIC = 0x0A07CA9

# UI Automation constants
UIA_TextPatternId = 10014
TPRE_Start, TPRE_End = 0, 1
TextUnit_Character = 0


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _INPUTUNION)]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wt.WPARAM, wt.LPARAM)
WINEVENTPROC = ctypes.WINFUNCTYPE(None, wt.HANDLE, wt.DWORD, wt.HWND,
                                  wt.LONG, wt.LONG, wt.DWORD, wt.DWORD)

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
user32.SetWindowsHookExW.restype = wt.HHOOK
user32.CallNextHookEx.argtypes = [wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wt.HHOOK]
user32.SendInput.argtypes = [wt.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wt.UINT
user32.GetForegroundWindow.restype = wt.HWND
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.GetKeyboardLayout.argtypes = [wt.DWORD]
user32.GetKeyboardLayout.restype = wt.HKL
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
user32.GetMessageW.restype = wt.BOOL
user32.PeekMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT, wt.UINT]
user32.PeekMessageW.restype = wt.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
user32.PostThreadMessageW.argtypes = [wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.MsgWaitForMultipleObjects.argtypes = [wt.DWORD, ctypes.POINTER(wt.HANDLE),
                                             wt.BOOL, wt.DWORD, wt.DWORD]
user32.MsgWaitForMultipleObjects.restype = wt.DWORD
user32.SetWinEventHook.argtypes = [wt.DWORD, wt.DWORD, wt.HMODULE, WINEVENTPROC,
                                   wt.DWORD, wt.DWORD, wt.DWORD]
user32.SetWinEventHook.restype = wt.HANDLE
user32.UnhookWinEvent.argtypes = [wt.HANDLE]
user32.SetTimer.argtypes = [wt.HWND, ULONG_PTR, wt.UINT, ctypes.c_void_p]
user32.SetTimer.restype = ULONG_PTR
user32.MessageBoxW.argtypes = [wt.HWND, wt.LPCWSTR, wt.LPCWSTR, wt.UINT]
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
kernel32.CreateMutexW.restype = wt.HANDLE

WM_TIMER = 0x0113
ERROR_ALREADY_EXISTS = 183
HOOK_REFRESH_MS = 15000   # re-install hooks regularly; Windows silently drops slow hooks

kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
kernel32.GetModuleHandleW.restype = wt.HMODULE
kernel32.GetCurrentThreadId.restype = wt.DWORD
kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.BOOL, wt.LPCWSTR]
kernel32.CreateEventW.restype = wt.HANDLE
kernel32.SetEvent.argtypes = [wt.HANDLE]
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR,
                                                ctypes.POINTER(wt.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = wt.BOOL
kernel32.CloseHandle.argtypes = [wt.HANDLE]


def is_pressed(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def is_english_layout():
    hwnd = user32.GetForegroundWindow()
    tid = user32.GetWindowThreadProcessId(hwnd, None)
    hkl = user32.GetKeyboardLayout(tid) or 0
    return (hkl & 0x3FF) == 0x09        # LANG_ENGLISH


def _key_input(vk=0, scan=0, flags=0):
    i = INPUT(type=INPUT_KEYBOARD)
    i.ki = KEYBDINPUT(vk, scan, flags, 0, MAGIC)
    return i


def send_text(text, backspaces=0):
    """Type `text` (after pressing Backspace `backspaces` times). True if Windows accepted it."""
    seq = []
    for _ in range(backspaces):
        seq += [_key_input(vk=VK_BACK), _key_input(vk=VK_BACK, flags=KEYEVENTF_KEYUP)]
    for ch in text:
        seq += [_key_input(scan=ord(ch), flags=KEYEVENTF_UNICODE),
                _key_input(scan=ord(ch), flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)]
    arr = (INPUT * len(seq))(*seq)
    return user32.SendInput(len(seq), arr, ctypes.sizeof(INPUT)) == len(seq)


_name_cache = {}


def process_name(pid):
    name = _name_cache.get(pid)
    if name is not None:
        return name
    name = ""
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if h:
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wt.DWORD(len(buf))
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                name = os.path.basename(buf.value).lower()
        finally:
            kernel32.CloseHandle(h)
    if len(_name_cache) > 256:
        _name_cache.clear()
    _name_cache[pid] = name
    return name


# --------------------------------------------------------------------------
# Focus watcher: asks Windows about the focused field (background thread)
# --------------------------------------------------------------------------

class FieldInfo:
    __slots__ = ("gen", "allowed", "context", "reason", "app", "ms")

    def __init__(self, gen, allowed, context, reason="", app="", ms=0):
        self.gen = gen              # which "focus generation" this answer belongs to
        self.allowed = allowed      # False for password fields, blocked apps, errors
        self.context = context      # text right before the cursor, or None if unknown
        self.reason = reason        # why not allowed (for the diagnostic log)
        self.app = app
        self.ms = ms                # how long Windows took to answer


class FocusWatcher(threading.Thread):
    """Every time focus/cursor may have moved, the generation number goes up and
    this thread re-checks the focused field using UI Automation:
      - is it a password field?   - which app is it?
      - what text is right before the cursor?
    It runs off the keyboard thread so typing never freezes."""

    def __init__(self):
        super().__init__(daemon=True, name="FocusWatcher")
        self.cond = threading.Condition()
        self.gen = 0
        self.bump_time = 0.0
        self.urgent = False
        self.result = None
        self.event = kernel32.CreateEventW(None, False, False, None)
        self.thread_id = None
        self.ready = threading.Event()
        self._focus_proc = WINEVENTPROC(self._on_focus_event)
        self._last_focus = None
        self.uia = None
        self.UIA = None

    # ---- called from other threads ----
    def bump(self):
        with self.cond:
            self.gen += 1
            self.bump_time = time.monotonic()
            gen = self.gen
        kernel32.SetEvent(self.event)
        return gen

    def get(self, gen, timeout=RESULT_TIMEOUT):
        """Answer for generation `gen`, waiting a little if it isn't ready. None = unknown."""
        deadline = time.monotonic() + timeout
        with self.cond:
            r = self.result
            if r is not None and r.gen == gen:
                return r
            self.urgent = True
            self.cond.notify_all()
        kernel32.SetEvent(self.event)
        with self.cond:
            while True:
                r = self.result
                if r is not None and r.gen == gen:
                    return r
                left = deadline - time.monotonic()
                if self.gen != gen or left <= 0:
                    return None
                self.cond.wait(left)

    def stop(self):
        if self.thread_id:
            user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)

    # ---- the thread ----
    def _on_focus_event(self, hook, event, hwnd, id_object, id_child, thread, ms):
        # Chrome/Electron apps (Discord, WhatsApp, Teams...) can repeat the focus
        # event for the SAME box many times. Only a real change resets the state.
        key = (hwnd, id_object, id_child)
        if key == self._last_focus:
            return
        self._last_focus = key
        Diag.log("focus changed")
        self.bump()

    def run(self):
        import comtypes
        import comtypes.client
        try:
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
            from comtypes.gen import UIAutomationClient as UIA
            self.UIA = UIA
            self.uia = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
        except Exception:
            print("AutoCap: UI Automation is not available, so AutoCap will stay off.", file=sys.stderr)
            traceback.print_exc()

        self.thread_id = kernel32.GetCurrentThreadId()
        hook = user32.SetWinEventHook(EVENT_OBJECT_FOCUS, EVENT_OBJECT_FOCUS, None,
                                      self._focus_proc, 0, 0,
                                      WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS)
        self.ready.set()

        handles = (wt.HANDLE * 1)(self.event)
        msg = wt.MSG()
        running = True
        while running:
            user32.MsgWaitForMultipleObjects(1, handles, False, 500, QS_ALLINPUT)
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message == WM_QUIT:
                    running = False
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            if running:
                self._service()
                Diag.flush()
        Diag.flush()
        if hook:
            user32.UnhookWinEvent(hook)

    def _service(self):
        while True:
            with self.cond:
                gen = self.gen
                if self.result is not None and self.result.gen == gen:
                    return
                # give the app a moment to move the cursor, unless a key is waiting
                while not self.urgent and self.gen == gen:
                    left = self.bump_time + SETTLE_DELAY - time.monotonic()
                    if left <= 0:
                        break
                    self.cond.wait(left)
                self.urgent = False
                if self.gen != gen:
                    continue
            t0 = time.monotonic()
            allowed, context, reason, app = self._query()
            ms = int((time.monotonic() - t0) * 1000)
            Diag.log(f"checked field: app={app or '?'} allowed={allowed} "
                     f"{reason} text-before-cursor={'yes' if context is not None else 'unknown'} took={ms}ms")
            with self.cond:
                if self.gen == gen:
                    self.result = FieldInfo(gen, allowed, context, reason, app, ms)
                    self.cond.notify_all()
                    return

    def _query(self):
        """Returns (allowed, text_before_cursor, reason, app_name)."""
        if self.uia is None:
            return False, None, "reason=no-ui-automation", ""
        if not settings.enabled:
            return False, None, "reason=paused", ""
        app = ""
        try:
            el = self.uia.GetFocusedElement()
            if not el:
                return False, None, "reason=nothing-focused", app
            pid = el.CurrentProcessId
            if pid == os.getpid():
                return False, None, "reason=autocap-itself", app
            app = process_name(pid)
            if app in BLOCKED_APPS:
                return False, None, "reason=blocked-app", app
            if el.CurrentIsPassword:
                return False, None, "reason=password-field", app
            return True, self._text_before_caret(el), "", app
        except Exception as e:
            # when unsure, do nothing (e.g. admin apps refuse to answer)
            return False, None, f"reason=error:{type(e).__name__}", app

    def _text_before_caret(self, el):
        try:
            unk = el.GetCurrentPattern(UIA_TextPatternId)
            if not unk:
                return None
            tp = unk.QueryInterface(self.UIA.IUIAutomationTextPattern)
            sel = tp.GetSelection()
            if not sel or sel.Length < 1:
                return None
            caret = sel.GetElement(0)
            r = caret.Clone()
            r.MoveEndpointByRange(TPRE_End, caret, TPRE_Start)          # collapse to cursor
            r.MoveEndpointByUnit(TPRE_Start, TextUnit_Character, -CONTEXT_CHARS)
            text = r.GetText(-1)
            return text if text is not None else None
        except Exception:
            return None


# --------------------------------------------------------------------------
# Engine: decides what to do with each key (runs on the hook thread)
# --------------------------------------------------------------------------

class Engine:
    def __init__(self, watcher):
        self.w = watcher
        self.buffer = None          # recent text before the cursor; None = unknown
        self.at_start = False       # does `buffer` begin at the start of the field?
        self.buffer_gen = -1
        self.fallback_start = False
        self.suppressed = set()     # keys whose key-up we must also swallow
        self.last_fg = None

    def invalidate(self, start_hint):
        """Cursor may have moved: forget the buffer and re-ask Windows."""
        self.buffer = None
        self.fallback_start = start_hint
        self.buffer_gen = self.w.bump()

    def _info(self):
        return self.w.get(self.w.gen)

    def _materialize(self, info):
        if self.buffer is not None:
            return
        if info is not None and info.context is not None:
            self.buffer = info.context
            self.at_start = len(info.context) < CONTEXT_CHARS
        else:
            self.buffer = ""
            self.at_start = self.fallback_start if info is not None else False
        self.buffer_gen = info.gen if info is not None else self.w.gen

    def _append(self, ch):
        if self.buffer is None:
            self._materialize(self._info())
        self.buffer += ch
        if len(self.buffer) > MAX_BUFFER:
            self.buffer = self.buffer[-MAX_BUFFER:]
            self.at_start = False

    # ---- keyboard ----
    def on_key(self, kb, wparam):
        """Return True to swallow the key."""
        down = wparam in (WM_KEYDOWN, WM_SYSKEYDOWN)
        vk = kb.vkCode

        if kb.flags & LLKHF_INJECTED:
            if kb.dwExtraInfo != MAGIC and down:
                self.invalidate(False)      # another program typed something
            return False

        if not down:
            if vk in self.suppressed:
                self.suppressed.discard(vk)
                return True
            return False

        # a held key repeating: let its key-up through later
        self.suppressed.discard(vk)

        if vk in MODIFIER_KEYS or vk in MEDIA_KEYS:
            return False

        fg = user32.GetForegroundWindow()
        if fg != self.last_fg:
            self.last_fg = fg
            self.invalidate(False)
        if self.buffer_gen != self.w.gen:   # focus moved (seen by the watcher)
            self.buffer = None
            self.fallback_start = False

        if is_pressed(VK_CONTROL) or is_pressed(VK_MENU) or is_pressed(VK_LWIN) or is_pressed(VK_RWIN):
            self.invalidate(False)          # shortcut: Ctrl+V, Ctrl+Z, Alt+Tab...
            return False

        shift = is_pressed(VK_SHIFT)
        english = is_english_layout()

        if 0x41 <= vk <= 0x5A:
            return self._on_letter(vk, shift, english)

        ch = char_for_vk(vk, shift)
        if ch is not None:
            return self._on_char(vk, ch, english)

        if vk in (VK_RETURN, VK_TAB):
            self.invalidate(True)           # new line / next field
        elif vk == VK_BACK:
            if self.buffer:
                self.buffer = self.buffer[:-1]
            elif not (self.buffer == "" and self.at_start):
                self.invalidate(False)
        elif vk == VK_DELETE:
            pass                            # doesn't change text before the cursor
        else:
            self.invalidate(False)          # arrows, Home, End, Esc, F-keys...
        return False

    def _on_letter(self, vk, shift, english):
        upper = chr(vk)
        typed = upper if shift else upper.lower()
        if not english:
            self._append("x")
            return False
        if not settings.enabled or shift:
            self._append(typed)
            return False
        if self.buffer is not None and not should_capitalize(self.buffer, self.at_start):
            self._append(typed)
            return False

        t0 = time.monotonic()
        info = self._info()
        waited = int((time.monotonic() - t0) * 1000)
        self._materialize(info)
        if info is None:
            Diag.log(f"SKIPPED: Windows didn't answer in time (waited {waited}ms)")
        elif not info.allowed:
            Diag.log(f"skipped: {info.reason} app={info.app}")
        elif not should_capitalize(self.buffer, self.at_start):
            Diag.log(f"no capital needed (mid-sentence) app={info.app}")
        elif send_text(upper):
            Diag.log(f"CAPITALIZED app={info.app} waited={waited}ms")
            self.suppressed.add(vk)
            self._append(upper)
            return True
        else:
            Diag.log(f"SKIPPED: Windows refused the typed capital app={info.app}")
        self._append(typed)
        return False

    def _on_char(self, vk, ch, english):
        if not english:
            self._append(" " if ch == " " else "#")
            return False
        if (settings.enabled and settings.fix_i and ch in I_TRIGGERS
                and self.buffer is not None and standalone_i(self.buffer, self.at_start)):
            info = self._info()
            if info is not None and info.allowed and send_text("I" + ch, backspaces=1):
                self.suppressed.add(vk)
                self.buffer = self.buffer[:-1] + "I"
                self._append(ch)
                return True
        self._append(ch)
        return False

    # ---- mouse ----
    def on_click(self):
        self.invalidate(settings.cap_after_click)


# --------------------------------------------------------------------------
# Hook thread
# --------------------------------------------------------------------------

class HookThread(threading.Thread):
    def __init__(self, engine):
        super().__init__(daemon=True, name="Hooks")
        self.engine = engine
        self.thread_id = None
        self.ready = threading.Event()
        self.ok = False
        self._kb_proc = HOOKPROC(self._kb)
        self._ms_proc = HOOKPROC(self._ms)

    def _kb(self, n_code, wparam, lparam):
        try:
            if n_code == HC_ACTION:
                kb = KBDLLHOOKSTRUCT.from_address(lparam)
                if self.engine.on_key(kb, wparam):
                    return 1
        except Exception:
            traceback.print_exc()
        return user32.CallNextHookEx(None, n_code, wparam, lparam)

    def _ms(self, n_code, wparam, lparam):
        try:
            if n_code == HC_ACTION and wparam in (WM_LBUTTONDOWN, WM_RBUTTONDOWN,
                                                  WM_MBUTTONDOWN, WM_XBUTTONDOWN):
                self.engine.on_click()
        except Exception:
            traceback.print_exc()
        return user32.CallNextHookEx(None, n_code, wparam, lparam)

    def _install(self, hmod):
        kb = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._kb_proc, hmod, 0)
        ms = user32.SetWindowsHookExW(WH_MOUSE_LL, self._ms_proc, hmod, 0)
        return kb, ms

    def run(self):
        self.thread_id = kernel32.GetCurrentThreadId()
        hmod = kernel32.GetModuleHandleW(None)
        kb_hook, ms_hook = self._install(hmod)
        self.ok = bool(kb_hook)
        self.ready.set()
        if not kb_hook:
            print("AutoCap: could not install the keyboard hook.", file=sys.stderr)
            return
        # Windows removes a low-level hook without telling us if it is ever too slow
        # (e.g. the PC was busy or just woke from sleep). Refresh it regularly.
        user32.SetTimer(None, 0, HOOK_REFRESH_MS, None)
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_TIMER:
                new_kb, new_ms = self._install(hmod)
                if new_kb:
                    user32.UnhookWindowsHookEx(kb_hook)
                    kb_hook = new_kb
                if new_ms:
                    if ms_hook:
                        user32.UnhookWindowsHookEx(ms_hook)
                    ms_hook = new_ms
                continue
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        user32.UnhookWindowsHookEx(kb_hook)
        if ms_hook:
            user32.UnhookWindowsHookEx(ms_hook)

    def stop(self):
        if self.thread_id:
            user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)


# --------------------------------------------------------------------------
# Tray icon
# --------------------------------------------------------------------------

def make_icon(on):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, 62, 62), radius=14, fill=(37, 99, 235) if on else (148, 163, 184))
    try:
        font = ImageFont.truetype("segoeuib.ttf", 32)
    except OSError:
        font = ImageFont.load_default()
    box = d.textbbox((0, 0), "Aa", font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text(((64 - w) / 2 - box[0], (64 - h) / 2 - box[1]), "Aa", font=font, fill="white")
    return img


def run_tray(watcher, hooks):
    import pystray

    def toggle_enabled(icon, item):
        settings.enabled = not settings.enabled
        settings.save()
        icon.icon = make_icon(settings.enabled)
        icon.title = "AutoCap (on)" if settings.enabled else "AutoCap (paused)"
        watcher.bump()

    def toggle_i(icon, item):
        settings.fix_i = not settings.fix_i
        settings.save()

    def toggle_click(icon, item):
        settings.cap_after_click = not settings.cap_after_click
        settings.save()

    def toggle_startup(icon, item):
        set_start_with_windows(not starts_with_windows())

    def toggle_debug(icon, item):
        settings.debug = not settings.debug
        settings.save()
        Diag.log("diagnostic log turned on" if settings.debug else "diagnostic log turned off")

    def open_logs(icon, item):
        os.makedirs(APP_DIR, exist_ok=True)
        os.startfile(APP_DIR)

    def open_help(icon, item):
        threading.Thread(target=show_message, args=(HELP_TEXT,), daemon=True).start()

    def quit_app(icon, item):
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Enabled", toggle_enabled, checked=lambda i: settings.enabled, default=True),
        pystray.MenuItem("Fix lone 'i' to 'I'", toggle_i, checked=lambda i: settings.fix_i),
        pystray.MenuItem("Capitalize after click (older apps)", toggle_click,
                         checked=lambda i: settings.cap_after_click),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Start with Windows", toggle_startup, checked=lambda i: starts_with_windows()),
        pystray.MenuItem("How it works", open_help),
        pystray.MenuItem("Troubleshooting", pystray.Menu(
            pystray.MenuItem("Diagnostic log", toggle_debug, checked=lambda i: settings.debug),
            pystray.MenuItem("Open log folder", open_logs),
        )),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", quit_app),
    )

    def setup(icon):
        icon.visible = True
        if settings.first_run:
            settings.first_run = False
            settings.save()
            try:
                icon.notify("AutoCap is running. It lives here in the tray: "
                            "right-click the Aa icon for settings.", "AutoCap")
            except Exception:
                pass

    title = "AutoCap (on)" if settings.enabled else "AutoCap (paused)"
    icon = pystray.Icon("AutoCap", make_icon(settings.enabled), title, menu)
    icon.run(setup=setup)
    hooks.stop()
    watcher.stop()


HELP_TEXT = (
    "AutoCap makes the first letter of each sentence a capital, in any app.\n\n"
    "\u2022 First letter in an empty box\n"
    "\u2022 After . ! ? and a space\n"
    "\u2022 At the start of a new line\n"
    "\u2022 A lone \"i\" becomes \"I\"\n\n"
    "It never changes password fields, shortcuts (Ctrl/Alt), Arabic typing, "
    "code editors or terminals.\n\n"
    "Nothing you type is saved or sent anywhere.\n\n"
    "Find the blue Aa icon near the clock (click the ^ arrow if you don't see it). "
    "Right-click it to pause, change options or quit."
)


def show_message(text, flags=0x40):   # 0x40 = information icon
    user32.MessageBoxW(None, text, "AutoCap", flags)


def main():
    setup_logging()

    # Only one copy at a time.
    kernel32.CreateMutexW(None, False, "Local\\AutoCapSingleInstance")
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        show_message("AutoCap is already running.\n\n"
                     "Look for the blue Aa icon near the clock "
                     "(click the ^ arrow if you don't see it).")
        return

    settings.load()

    # Load COM on the main thread. In the installed .exe the UI Automation
    # wrapper is already bundled; when run from source it is generated once.
    import comtypes.client
    try:
        comtypes.client.GetModule("UIAutomationCore.dll")
    except Exception:
        traceback.print_exc()

    watcher = FocusWatcher()
    watcher.start()
    watcher.ready.wait(5)

    hooks = HookThread(Engine(watcher))
    hooks.start()
    hooks.ready.wait(5)
    if not hooks.ok:
        show_message("AutoCap could not start because Windows blocked keyboard access.", 0x10)
        sys.exit(1)

    run_tray(watcher, hooks)


if __name__ == "__main__":
    main()
