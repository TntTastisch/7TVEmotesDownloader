#!/usr/bin/env python3
import argparse
import random
import re
import sys
import time
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, UnidentifiedImageError

API_BASE = "https://7tv.io/v3"
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "7TV-Set-Downloader/1.1 (Windows; Python requests)",
    "Accept": "application/json",
})

RETRY_STATUSES = {429, 500, 502, 503, 504, 520, 522, 524}


def parse_args():
    p = argparse.ArgumentParser(
        description="Download all emotes from a 7TV emote set in 2x scale as PNG/GIF."
    )
    p.add_argument("url", help="7TV user or emote-set URL, e.g. https://7tv.app/users/<id> or /emote-sets/<id>")
    p.add_argument("--scale", default="2x", choices=["1x", "2x", "3x", "4x"], help="Scale to download (default: 2x)")
    p.add_argument("--no-convert", action="store_true", help="Do not convert WEBP/AVIF to PNG/GIF; save as-is")
    p.add_argument("--timeout", type=int, default=20, help="HTTP timeout seconds (default: 20)")
    p.add_argument("--out", default=None, help="Output directory (optional; default derives from user/set name)")
    return p.parse_args()


def sanitize(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s or "").strip("_") or "unnamed"


def http_get_json(url: str, timeout: int, max_retries: int = 6, base_backoff: float = 0.7):
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            sep = "&" if "?" in url else "?"
            r = SESSION.get(f"{url}{sep}_ts={int(time.time() * 1000)}", timeout=timeout)
            if r.status_code in RETRY_STATUSES:
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            if attempt == max_retries:
                break
            sleep = base_backoff * (2 ** (attempt - 1)) + random.uniform(0.0, 0.5)
            time.sleep(sleep)
    raise last_err


def extract_ids(url: str):
    m_set = re.search(r"/emote-sets/([A-Za-z0-9]+)", url)
    if m_set:
        return {"type": "set", "id": m_set.group(1)}
    m_user = re.search(r"/users/([A-Za-z0-9]+)", url)
    if m_user:
        return {"type": "user", "id": m_user.group(1)}
    raise ValueError("Could not extract /emote-sets/<id> or /users/<id> from URL.")


def resolve_from_user(user_id: str, timeout: int):
    endpoints = [
        f"{API_BASE}/users/{user_id}",
        f"{API_BASE}/users/7tv/{user_id}",
    ]
    last_err = None
    for ep in endpoints:
        try:
            data = http_get_json(ep, timeout)
            username = data.get("username") or data.get("display_name")
            set_id = None

            if isinstance(data.get("emote_set"), dict):
                set_id = data["emote_set"].get("id")

            if not set_id:
                for c in data.get("connections", []):
                    if c.get("emote_set_id"):
                        set_id = c["emote_set_id"]
                        break

            if set_id:
                return username, set_id
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"Could not determine emote set ID for user {user_id}: {last_err}")


def fetch_emote_set(set_id: str, timeout: int):
    return http_get_json(f"{API_BASE}/emote-sets/{set_id}", timeout)


def best_file_for_emote(emote, scale: str):
    data = emote.get("data", {})
    host = data.get("host", {})
    files = host.get("files", [])
    animated = bool(data.get("animated", False))

    priority = []
    if animated:
        priority = ["gif", "webp", "avif"]
    else:
        priority = ["png", "webp", "avif"]

    by_name = {f.get("name", "").lower(): f for f in files}
    for ext in priority:
        target = f"{scale}.{ext}"
        f = by_name.get(target)
        if f:
            return f, animated

    for f in files:
        n = (f.get("name") or "").lower()
        if n.startswith(scale):
            return f, animated

    return (files[-1], animated) if files else (None, animated)


def build_cdn_url(host_url: str, file_name: str):
    base = host_url or ""
    if base.startswith("//"):
        base = "https:" + base
    if not base:
        return None
    if base.endswith("/"):
        return base + file_name
    return base + "/" + file_name


def convert_and_save(content: bytes, out_path: Path, animated: bool, target_ext: str):
    try:
        im = Image.open(BytesIO(content))
    except UnidentifiedImageError:
        out_path.with_suffix(out_path.suffix + ".orig").write_bytes(content)
        return False

    if animated and getattr(im, "is_animated", False) and target_ext.lower() == "gif":
        frames = []
        durations = []
        try:
            for i in range(im.n_frames):
                im.seek(i)
                frames.append(im.convert("RGBA"))
                durations.append(im.info.get("duration", 100))
        except Exception:
            frames = [im.convert("RGBA")]
            durations = [100]

        first, rest = frames[0], frames[1:] or []
        first.save(
            out_path,
            save_all=True,
            append_images=rest,
            loop=0,
            duration=durations if len(durations) == len(frames) else 100,
        )
        return True

    if target_ext.lower() == "png":
        im.convert("RGBA").save(out_path, format="PNG")
        return True

    out_path.with_suffix(out_path.suffix + ".orig").write_bytes(content)
    return False


def download_bytes(url: str, timeout: int, max_retries: int = 5, base_backoff: float = 0.5):
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            r = SESSION.get(url, timeout=timeout)
            if r.status_code in RETRY_STATUSES:
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            return r.content
        except Exception as e:
            last_err = e
            if attempt == max_retries:
                break
            sleep = base_backoff * (2 ** (attempt - 1)) + random.uniform(0.0, 0.4)
            time.sleep(sleep)
    raise last_err


def derive_outdir(args_out: str | None, source_type: str, meta: dict, fallback_id: str) -> Path:
    if args_out:
        return Path(args_out)

    if source_type == "user":
        username = sanitize(meta.get("username") or "")
        if username:
            return Path(f"7tv_{username}")
        return Path(f"7tv_user_{sanitize(fallback_id)}")

    set_name = sanitize(meta.get("name") or "")
    if set_name:
        return Path(f"7tv_set_{set_name}")
    return Path(f"7tv_set_{sanitize(fallback_id)}")


def main():
    args = parse_args()

    ids = extract_ids(args.url)
    meta_for_naming = {}
    source_type = ids["type"]

    if source_type == "user":
        username, set_id = resolve_from_user(ids["id"], args.timeout)
        if username:
            meta_for_naming["username"] = username
    else:
        set_id = ids["id"]

    emote_set = fetch_emote_set(set_id, args.timeout)

    if source_type == "set":
        meta_for_naming["name"] = emote_set.get("name") or ""
        owner = emote_set.get("owner") or emote_set.get("user") or {}
        if isinstance(owner, dict):
            meta_for_naming["username"] = owner.get("username") or owner.get("display_name") or ""

    outdir = derive_outdir(args.out, source_type, meta_for_naming, set_id)
    outdir.mkdir(parents=True, exist_ok=True)

    emotes = emote_set.get("emotes", [])
    if not emotes:
        print("No emotes found in this set.")
        return

    title = emote_set.get("name") or set_id
    print(f"Emote Set: {title} – {len(emotes)} emotes")
    print(f"Output Directory: {outdir.resolve()}")

    downloaded = 0
    skipped = 0

    for e in emotes:
        name_top = e.get("name") or e.get("data", {}).get("name") or e.get("id", "emote")
        name = sanitize(name_top)
        host_url = e.get("data", {}).get("host", {}).get("url")

        if not host_url:
            print(f"- {name}: missing host.url → skipped")
            skipped += 1
            continue

        file_entry, is_animated = best_file_for_emote(e, args.scale)
        if not file_entry:
            print(f"- {name}: no file available at scale {args.scale} → skipped")
            skipped += 1
            continue

        cdn_url = build_cdn_url(host_url, file_entry.get("name", ""))
        if not cdn_url:
            print(f"- {name}: invalid CDN URL → skipped")
            skipped += 1
            continue

        ext = (file_entry.get("name") or "").split(".")[-1].lower()

        try:
            blob = download_bytes(cdn_url, args.timeout)
        except Exception as ex:
            print(f"- {name}: download failed → {ex}")
            skipped += 1
            continue

        if args.no_convert:
            out_path = outdir / f"{name}_{args.scale}.{ext}"
            out_path.write_bytes(blob)
            print(f"+ {name}: {out_path.name} (no conversion)")
            downloaded += 1
            continue

        if is_animated:
            if ext == "gif":
                out_path = outdir / f"{name}_{args.scale}.gif"
                out_path.write_bytes(blob)
                print(f"+ {name}: {out_path.name}")
                downloaded += 1
            else:
                out_path = outdir / f"{name}_{args.scale}.gif"
                ok = convert_and_save(blob, out_path, animated=True, target_ext="gif")
                if ok:
                    print(f"+ {name}: {out_path.name} (converted from {ext.upper()})")
                else:
                    raw_path = outdir / f"{name}_{args.scale}.{ext}"
                    raw_path.write_bytes(blob)
                    print(f"+ {name}: {raw_path.name} (original, conversion not possible)")
                downloaded += 1
        else:
            if ext == "png":
                out_path = outdir / f"{name}_{args.scale}.png"
                out_path.write_bytes(blob)
                print(f"+ {name}: {out_path.name}")
                downloaded += 1
            else:
                out_path = outdir / f"{name}_{args.scale}.png"
                ok = convert_and_save(blob, out_path, animated=False, target_ext="png")
                if ok:
                    print(f"+ {name}: {out_path.name} (converted from {ext.upper()})")
                else:
                    raw_path = outdir / f"{name}_{args.scale}.{ext}"
                    raw_path.write_bytes(blob)
                    print(f"+ {name}: {raw_path.name} (original, conversion not possible)")
                downloaded += 1

        time.sleep(0.03)

    print(f"Done: {downloaded} files saved, {skipped} skipped.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
