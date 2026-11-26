# AutoCap

Capitalizes the first letter of every sentence in **any app on Windows**: browsers, WhatsApp, Discord, Notepad, Outlook and so on.

## For users: install
1. Go to the **Releases** page and download **`AutoCap-Setup.exe`**.
2. Open it and click **Next → Install → Finish**. No admin password is needed.
3. A blue **Aa** icon appears near the clock. That's it.

> If Windows shows *"Windows protected your PC"*, click **More info → Run anyway**.
> This appears for new apps that aren't signed yet.

Right-click the **Aa** icon to pause it, change options, turn "Start with Windows" on or off, or quit.
Uninstall it from **Settings → Apps** like any other app.

## What it does
- First letter in an empty text field → capital
- After `.` `!` `?` and a space → capital
- First letter on a new line → capital
- A lone `i` → `I` (optional)

## What it never touches
- Password fields
- Shortcuts (when Ctrl, Alt or Win is held)
- Non-English keyboard layouts (e.g. Arabic)
- Code editors, terminals, remote desktop, password managers
- `google.com`, `3.5`, `e.g.`, `Dr.`, `wait...`

Nothing you type is saved or sent anywhere. Only the settings are saved, in `%APPDATA%\AutoCap\settings.json`.

---

## For developers

### Build the installer (no Windows PC needed)
The GitHub Action in `.github/workflows/build.yml` builds `AutoCap.exe` and `AutoCap-Setup.exe` on a Windows machine for free.

- **Test build:** Actions tab → *Build AutoCap for Windows* → **Run workflow**. Download the files from the run page.
- **Public release:**
  ```
  git tag v1.0.0
  git push origin v1.0.0
  ```
  This creates a Release with `AutoCap-Setup.exe` attached.

### Run from source
```
pip install -r requirements.txt
python autocap.py
```

### Tests
```
python -m unittest test_logic.py
```

### How it works
- A **low-level keyboard hook** sees each key before the app does. When a letter should be capital, AutoCap blocks the lowercase key and types the capital instead.
- **UI Automation** (the Windows accessibility API) tells it whether the focused field is a password field and what text is right before the cursor.
- Hooks are refreshed every 15 seconds, because Windows silently removes a hook that is ever too slow.
- Errors (never keystrokes) are logged to `%APPDATA%\AutoCap\autocap.log`.

### Known limits
- Apps running **as administrator** are skipped.
- The app isn't code-signed, so SmartScreen warns on first run. Open-source projects can get free signing from the SignPath Foundation.
