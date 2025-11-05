# 7TV Emote Set Downloader

A Python tool that downloads **all emotes** from a **7TV emote set**, automatically at **2x scale**, saving them as **GIF** (animated) or **PNG** (static).  
Works with both **user profile URLs** and **direct emote-set URLs**.

---

## Features

| Feature | Description |
|--------|-------------|
| 🔗 Accepts **User** or **Emote Set** links | Example: `https://7tv.app/users/<id>` or `https://7tv.app/emote-sets/<id>` |
| 📁 **Automatic folder naming** | Outputs to `7tv_<username>` or `7tv_set_<setname>` |
| 🖼️ **Correct file formats** | Animated → `.gif`, Static → `.png` |
| 🔄 **Smart conversion** | Converts WEBP/AVIF → GIF/PNG if needed |
| ♻️ **Retry & Cloudflare protection** | Automatically retries on 429/502/503/520 etc. |
| 🧱 Optional raw download | `--no-convert` keeps original WEBP/AVIF files |

---

## Requirements

- Python **3.8+**
- `pip` package manager

### Install dependencies:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Usage

### Download a user’s active emote set:

```bash
python main.py "https://7tv.app/users/01HW7FGSAR0005KAADWK50GSZE"
```

Output directory will be named automatically.

### Download a specific emote set:

```bash
python main.py "https://7tv.app/emote-sets/<SET_ID>"
```

### Optional flags

| Flag                    | Description                                   | Default   |
| ----------------------- | --------------------------------------------- | --------- |
| `--scale {1x,2x,3x,4x}` | Which resolution to download                  | `2x`      |
| `--no-convert`          | Save original WEBP/AVIF instead of converting | Off       |
| `--out <folder>`        | Override output directory name                | Automatic |
| `--timeout <seconds>`   | Network timeout                               | `20`      |

Example:

```bash
python main.py "https://7tv.app/users/<id>" --scale 4x --out Emotes_HD
```

---

## Output Examples

Animated emote:

```
example_emote_2x.gif
```

Static emote:

```
example_emote_2x.png
```

---

## Troubleshooting

| Issue                               | Solution                                          |
| ----------------------------------- | ------------------------------------------------- |
| ❗ Cloudflare 520 / 502 / 503 errors | The script **automatically retries** — just wait. |
| 🟨 Missing GIF/PNG output           | Use `--no-convert` to keep original formats.      |
| 🟥 Some emotes fail                 | They may be private or removed from CDN.          |
