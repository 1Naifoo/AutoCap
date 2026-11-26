<div align="center">

<img src="assets/autocap.png" width="110" alt="AutoCap icon">

# AutoCap

**Capital letters at the start of every sentence, in every app on Windows.**

[![Download](https://img.shields.io/github/v/release/1Naifoo/AutoCap?label=Download&style=for-the-badge&color=2563eb)](https://github.com/1Naifoo/AutoCap/releases/latest)
![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6?style=for-the-badge&logo=windows)
![Free](https://img.shields.io/badge/Free-Open%20Source-22c55e?style=for-the-badge)

</div>

---

## 💡 The story

A friend of mine asked me a simple question:

> *"Why doesn't my computer capitalize the first letter like my phone does?"*

Phones do it everywhere. Microsoft Word does it. But on Windows, in WhatsApp, Chrome, Discord or Notepad, you're on your own.

There was no built-in setting and no simple app for it. So I built one for him: small, free, and simple enough for anyone to install.

---

## ⬇️ Install in 30 seconds

1. Download **[AutoCap-Setup.exe](https://github.com/1Naifoo/AutoCap/releases/latest)**
2. Open it and click **Next → Install**
3. Look for the blue **Aa** icon near the clock. You're done ✨

> 🛡️ If Windows says *"Windows protected your PC"*, click **More info → Run anyway**.
> This shows up for new apps that aren't signed yet.

---

## ✍️ What it does

| You type | You get |
|---|---|
| `hello world` | `Hello world` |
| `done. see you` | `Done. See you` |
| `really? yes` | `Really? Yes` |
| `i think so` | `I think so` |

## 🔒 What it leaves alone

🔑 Password fields · ⌨️ Shortcuts · 🇸🇦 Arabic typing · 💻 Code editors · 🌐 `google.com`, `3.5`, `e.g.`

**Nothing you type is saved or sent anywhere.**

---

<details>
<summary><b>🛠️ For developers</b></summary>

<br>

**How it works**
- A low-level keyboard hook catches the lowercase key and types the capital instead, so there's no flicker.
- Windows UI Automation detects password fields and reads the text before the cursor.
- Built with Python, packaged with PyInstaller and Inno Setup by GitHub Actions.

**Run from source**
```
pip install -r requirements.txt
python autocap.py
```

**Release a new version**
```
git tag v1.0.0
git push origin v1.0.0
```

</details>

---

<div align="center">

Made with ❤️ by **[Naif Omran](https://github.com/1Naifoo)** for a friend, and now for anyone who wants it.

⭐ If AutoCap saves you a few Shift presses, give it a star!

</div>
