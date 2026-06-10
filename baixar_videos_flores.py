#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Baixa vídeos gratuitos que correspondem a uma busca (ex.: 'flores') de bibliotecas públicas (Pexels, Pixabay e opcionalmente Coverr).
Requisitos: Python 3.9+, requests, tqdm.

Instalar deps:
  pip install requests tqdm
"""

import argparse, os, sys, json, time, re
from pathlib import Path
from urllib.parse import urlencode
import requests
from tqdm import tqdm

# -------- utilidades ----------
def slugify(text, fallback="video"):
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", "-", text.strip())
    return text.lower() or fallback

def safe_write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_json(path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default

def download_file(url, dest, session, chunk=1024*1024):
    dest.parent.mkdir(parents=True, exist_ok=True)
    with session.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length") or 0)
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as f, tqdm(total=total, unit="B", unit_scale=True, desc=dest.name) as pbar:
            for chunk_data in r.iter_content(chunk_size=chunk):
                if chunk_data:
                    f.write(chunk_data)
                    pbar.update(len(chunk_data))
        tmp.rename(dest)

# -------- provedores ----------
def fetch_pexels(query, api_key, per_page, max_pages, min_duration, orientation):
    # Docs: https://www.pexels.com/api/documentation/ (Video Search)
    headers = {"Authorization": api_key}
    base = "https://api.pexels.com/videos/search"
    page = 1
    while page <= max_pages:
        params = {
            "query": query,
            "per_page": per_page,
            "page": page,
            # filtros extras disponíveis: orientation (portrait/landscape/square), size, locale, etc.
        }
        # Nota: Pexels não filtra por duração diretamente; filtraremos localmente
        r = requests.get(base, headers=headers, params=params, timeout=60)
        if r.status_code == 429:
            time.sleep(5);  # rate limiting básico
            continue
        r.raise_for_status()
        data = r.json()
        videos = data.get("videos", [])
        if not videos:
            break
        for v in videos:
            duration = int(v.get("duration") or 0)
            if duration < min_duration:
                continue
            title = v.get("user", {}).get("name") or f"Pexels-{v.get('id')}"
            files = v.get("video_files", [])
            # escolha a melhor qualidade horizontal/vertical conforme orientação pedida
            def score(f):
                w, h = f.get("width") or 0, f.get("height") or 0
                # prefira MP4, maior resolução e oriente conforme pedido
                s = (1 if f.get("file_type","").lower()=="video/mp4" else 0)
                s += (w*h)/1e6
                if orientation == "landscape" and w >= h: s += 1
                if orientation == "portrait" and h > w: s += 1
                return s
            files = sorted(files, key=score, reverse=True)
            if files:
                yield {
                    "provider": "pexels",
                    "id": str(v.get("id")),
                    "title": title,
                    "url": files[0].get("link"),
                    "width": files[0].get("width"),
                    "height": files[0].get("height"),
                    "duration": duration,
                    "source_page": v.get("url"),
                }
        page += 1

def fetch_pixabay(query, api_key, per_page, max_pages, min_duration, orientation):
    # Docs: https://pixabay.com/api/docs/ (Video API)
    base = "https://pixabay.com/api/videos/"
    page = 1
    while page <= max_pages:
        params = {
            "key": api_key,
            "q": query,
            "per_page": per_page,
            "page": page,
            "safesearch": "true",
            # category, editors_choice etc. podem ser usados aqui
        }
        r = requests.get(base, params=params, timeout=60)
        if r.status_code == 429:
            time.sleep(5); continue
        r.raise_for_status()
        data = r.json()
        hits = data.get("hits", [])
        if not hits:
            break
        for v in hits:
            vids = v.get("videos", {})
            # escolha melhor qualidade conforme orientação
            candidates = []
            for label, meta in vids.items():
                url = meta.get("url")
                w, h = meta.get("width"), meta.get("height")
                d = int(v.get("duration") or 0)
                if not url: continue
                if d < min_duration: continue
                sc = (w*h if w and h else 0)
                if orientation == "landscape" and w and h and w >= h: sc += 1
                if orientation == "portrait" and w and h and h > w: sc += 1
                candidates.append((sc, url, w, h, d))
            if candidates:
                candidates.sort(reverse=True)
                sc, url, w, h, d = candidates[0]
                yield {
                    "provider": "pixabay",
                    "id": str(v.get("id")),
                    "title": v.get("user") or f"Pixabay-{v.get('id')}",
                    "url": url,
                    "width": w,
                    "height": h,
                    "duration": d,
                    "source_page": v.get("pageURL"),
                }
        page += 1

def fetch_coverr(query, api_key, per_page, max_pages, min_duration, orientation):
    # Docs: https://api.coverr.co/docs/videos/ (requer chave solicitada por e-mail)
    headers = {"Authorization": f"Bearer {api_key}"}
    base = "https://api.coverr.co/videos"
    page = 1
    while page <= max_pages:
        params = {
            "q": query,
            "page": page,
            "per_page": per_page,
            "sort": "relevance"
        }
        r = requests.get(base, headers=headers, params=params, timeout=60)
        if r.status_code == 401:
            raise RuntimeError("Coverr API key inválida ou ausente.")
        if r.status_code == 429:
            time.sleep(5); continue
        r.raise_for_status()
        data = r.json()
        items = data.get("items", [])
        if not items: break
        for v in items:
            duration = int(v.get("duration") or 0)
            if duration < min_duration: continue
            # Coverr normalmente fornece múltiplos sources
            sources = v.get("sources") or []
            def score(s):
                w, h = s.get("width", 0), s.get("height", 0)
                sc = (w*h)
                if orientation == "landscape" and w >= h: sc += 1
                if orientation == "portrait" and h > w: sc += 1
                return sc
            sources = sorted(sources, key=score, reverse=True)
            if sources:
                s0 = sources[0]
                yield {
                    "provider": "coverr",
                    "id": str(v.get("id")),
                    "title": v.get("title") or f"Coverr-{v.get('id')}",
                    "url": s0.get("src"),
                    "width": s0.get("width"),
                    "height": s0.get("height"),
                    "duration": duration,
                    "source_page": f"https://coverr.co/videos/{v.get('slug')}" if v.get("slug") else None,
                }
        page += 1

# -------- main ----------
def main():
    ap = argparse.ArgumentParser(description="Baixa vídeos gratuitos por palavra-chave de bibliotecas públicas.")
    ap.add_argument("--query", "-q", default="flores", help="Termo de busca (default: flores)")
    ap.add_argument("--out", "-o", default="videos_flores", help="Pasta de saída")
    ap.add_argument("--providers", "-p", default="pexels,pixabay", help="Lista separada por vírgula: pexels,pixabay,coverr")
    ap.add_argument("--per-page", type=int, default=40, help="Itens por página/consulta")
    ap.add_argument("--max-pages", type=int, default=5, help="Número máximo de páginas por provedor")
    ap.add_argument("--min-duration", type=int, default=0, help="Duração mínima em segundos (ex.: 5)")
    ap.add_argument("--orientation", choices=["any","landscape","portrait"], default="landscape", help="Preferência de orientação")
    ap.add_argument("--pexels-key", default=os.getenv("PEXELS_API_KEY"), help="Chave API Pexels (ou defina PEXELS_API_KEY)")
    ap.add_argument("--pixabay-key", default=os.getenv("PIXABAY_API_KEY"), help="Chave API Pixabay (ou defina PIXABAY_API_KEY)")
    ap.add_argument("--coverr-key", default=os.getenv("COVERR_API_KEY"), help="Chave API Coverr (opcional)")


    args = ap.parse_args()
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    downloaded_idx = outdir / "_baixados.json"
    idx = load_json(downloaded_idx, {})

    session = requests.Session()
    total_found, total_new = 0, 0

    def already_done(item):
        key = f"{item['provider']}:{item['id']}"
        return key in idx

    def mark_done(item, path):
        key = f"{item['provider']}:{item['id']}"
        idx[key] = {
            "title": item["title"],
            "url": item["url"],
            "width": item["width"],
            "height": item["height"],
            "duration": item["duration"],
            "source_page": item["source_page"],
            "path": str(path),
        }

    fetchers = []
    provs = [p.strip().lower() for p in args.providers.split(",") if p.strip()]
    if "pexels" in provs:
        if not args.pexels_key:
            print("Aviso: sem PEXELS_API_KEY; pulando Pexels.", file=sys.stderr)
        else:
            fetchers.append(("pexels", fetch_pexels(args.query, args.pexels_key, args.per_page, args.max_pages, args.min_duration, args.orientation)))
    if "pixabay" in provs:
        if not args.pixabay_key:
            print("Aviso: sem PIXABAY_API_KEY; pulando Pixabay.", file=sys.stderr)
        else:
            fetchers.append(("pixabay", fetch_pixabay(args.query, args.pixabay_key, args.per_page, args.max_pages, args.min_duration, args.orientation)))
    if "coverr" in provs:
        if not args.coverr_key:
            print("Aviso: sem COVERR_API_KEY; pulando Coverr.", file=sys.stderr)
        else:
            fetchers.append(("coverr", fetch_coverr(args.query, args.coverr_key, args.per_page, args.max_pages, args.min_duration, args.orientation)))

    for provider, gen in fetchers:
        for item in gen:
            total_found += 1
            if already_done(item):
                continue
            # nome do arquivo
            base = f"{item['provider']}-{item['id']}-{slugify(item['title'])}"
            if item.get("width") and item.get("height"):
                base += f"-{item['width']}x{item['height']}"
            dest = outdir / f"{base}.mp4"

            try:
                download_file(item["url"], dest, session)
                mark_done(item, dest)
                total_new += 1
                safe_write_json(downloaded_idx, idx)
            except Exception as e:
                print(f"Falhou: {item['url']} -> {e}", file=sys.stderr)
                time.sleep(1)

    print(f"\nConcluído. Encontrados: {total_found}, baixados novos: {total_new}, total no índice: {len(idx)}")
    safe_write_json(downloaded_idx, idx)

if __name__ == "__main__":
    main()

