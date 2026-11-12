"""Publica no Instagram (@primoradestaques) os itens da fila.json cujo horário já chegou.

Roda no GitHub Actions (de hora em hora). Variáveis: IG_ACCESS_TOKEN, IG_USER_ID.
Item da fila:
  {"id": "...", "tipo": "carrossel" | "story", "imagens": ["midia/..jpg", ...],
   "legenda": "...", "collabs": ["handle"], "quando": "2026-11-12T09:00:00-03:00",
   "status": "pendente" | "publicado" | "erro", "media_id": "...", "erro": "..."}
Uso local: python publicar.py [--dry-run] [--id ITEM]  (dry-run cria o container mas não publica)
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://graph.facebook.com/v23.0"
REPO = os.environ.get("GITHUB_REPOSITORY", "tarc261005-crypto/primora-publicador")
BASE_URL = f"https://raw.githubusercontent.com/{REPO}/main/"
FILA = Path(__file__).with_name("fila.json")
MAX_POR_RODADA = 20


def _env() -> tuple[str, str]:
    tok, ig = os.environ.get("IG_ACCESS_TOKEN", ""), os.environ.get("IG_USER_ID", "")
    if not tok or not ig:
        env = Path(r"C:\Users\pac17\projetos\instagram-certificados\publicador\.env")
        if env.exists():
            kv = dict(l.split("=", 1) for l in env.read_text(encoding="utf-8-sig").splitlines() if "=" in l)
            tok, ig = tok or kv.get("IG_ACCESS_TOKEN", "").strip(), ig or kv.get("IG_USER_ID", "").strip()
    if not tok or not ig:
        sys.exit("Faltam IG_ACCESS_TOKEN / IG_USER_ID")
    return tok, ig


TOKEN, IG = _env()


class ApiErro(Exception):
    pass


def chamar(metodo: str, path: str, **params) -> dict:
    params["access_token"] = TOKEN
    dados = urllib.parse.urlencode(params).encode()
    url = f"{API}/{path}"
    if metodo == "GET":
        req = urllib.request.Request(f"{url}?{dados.decode()}")
    else:
        req = urllib.request.Request(url, data=dados, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            err = json.load(e).get("error", {})
        except Exception:  # noqa: BLE001
            err = {"message": str(e)}
        raise ApiErro(err.get("error_user_msg") or err.get("message") or str(err)) from None


def aguardar(container: str) -> None:
    for _ in range(30):
        st = chamar("GET", container, fields="status_code,status").get("status_code")
        if st == "FINISHED":
            return
        if st in ("ERROR", "EXPIRED"):
            raise ApiErro(f"container {container} com status {st}")
        time.sleep(5)
    raise ApiErro(f"container {container} demorou demais")


def criar_container(item: dict, com_collab: bool = True) -> str:
    urls = [BASE_URL + urllib.parse.quote(p) for p in item["imagens"]]
    if item["tipo"] == "story":
        c = chamar("POST", f"{IG}/media", image_url=urls[0], media_type="STORIES")["id"]
    elif len(urls) == 1:
        extra = {"collaborators": json.dumps(item["collabs"][:3])} if com_collab and item.get("collabs") else {}
        c = chamar("POST", f"{IG}/media", image_url=urls[0], caption=item.get("legenda", ""), **extra)["id"]
    else:
        filhos = [chamar("POST", f"{IG}/media", image_url=u, is_carousel_item="true")["id"] for u in urls]
        for f in filhos:
            aguardar(f)
        extra = {"collaborators": json.dumps(item["collabs"][:3])} if com_collab and item.get("collabs") else {}
        c = chamar("POST", f"{IG}/media", media_type="CAROUSEL", children=",".join(filhos),
                   caption=item.get("legenda", ""), **extra)["id"]
    aguardar(c)
    return c


def publicar(item: dict, dry: bool) -> str:
    try:
        c = criar_container(item)
    except ApiErro as e:
        if item.get("collabs") and "collab" in str(e).lower():
            print(f"  collab recusado ({e}); publicando sem collab")
            item["obs"] = f"sem collab: {e}"
            c = criar_container(item, com_collab=False)
        else:
            raise
    if dry:
        return f"dry-run:{c}"
    return chamar("POST", f"{IG}/media_publish", creation_id=c)["id"]


def main() -> None:
    dry = "--dry-run" in sys.argv
    so_id = sys.argv[sys.argv.index("--id") + 1] if "--id" in sys.argv else None
    fila = json.loads(FILA.read_text(encoding="utf-8"))
    agora = datetime.now(timezone.utc)
    vencidos = [i for i in fila if i["status"] == "pendente"
                and (i["id"] == so_id if so_id else datetime.fromisoformat(i["quando"]) <= agora)]
    vencidos.sort(key=lambda i: i["quando"])
    print(f"{agora:%Y-%m-%d %H:%M} UTC | {len(vencidos)} item(ns) para publicar{' (dry-run)' if dry else ''}")
    for item in vencidos[:MAX_POR_RODADA]:
        print(f"- {item['id']} ({item['tipo']})")
        try:
            mid = publicar(item, dry)
            print(f"  ok {mid}")
            if not dry:
                item.update(status="publicado", media_id=mid, publicado_em=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        except (ApiErro, urllib.error.URLError) as e:
            print(f"  ERRO: {e}")
            if not dry:
                item["tentativas"] = item.get("tentativas", 0) + 1
                item["erro"] = str(e)
                if item["tentativas"] >= 3:
                    item["status"] = "erro"
    if not dry:
        FILA.write_text(json.dumps(fila, ensure_ascii=False, indent=1), encoding="utf-8")
    print("cota:", chamar("GET", f"{IG}/content_publishing_limit", fields="quota_usage").get("data"))


if __name__ == "__main__":
    main()
