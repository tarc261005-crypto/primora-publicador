"""Gera FILA.md: a fila de publicações em formato legível (abre bonito no GitHub, inclusive no celular)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

AQUI = Path(__file__).parent
BRT = timezone(timedelta(hours=-3))
DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
ICONE = {"pendente": "⏳ agendado", "publicado": "✅ publicado", "erro": "❌ erro"}


def _quando(iso: str) -> str:
    d = datetime.fromisoformat(iso).astimezone(BRT)
    return f"{DIAS[d.weekday()]} {d:%d/%m %H:%M}"


def gerar() -> None:
    fila = json.loads((AQUI / "fila.json").read_text(encoding="utf-8"))
    pend = [i for i in fila if i["status"] == "pendente"]
    pub = [i for i in fila if i["status"] == "publicado"]
    err = [i for i in fila if i["status"] == "erro"]
    ultimo_feed = max((i["quando"] for i in pend if i["tipo"] == "carrossel"), default=None)
    agora = datetime.now(BRT)
    linhas = [
        "# Fila de publicações · @primoradestaques",
        "",
        f"Atualizado em {agora:%d/%m/%Y %H:%M} (horário de Brasília).",
        "",
        f"**{len(pend)} agendados** · **{len(pub)} publicados** · **{len(err)} com erro**"
        + (f" · posts do feed garantidos até **{_quando(ultimo_feed)[:9]}**" if ultimo_feed else " · ⚠️ fila do feed vazia"),
        "",
    ]
    if err:
        linhas += ["## ❌ Com erro", "", "| Quando | Tipo | O quê | Erro |", "|---|---|---|---|"]
        linhas += [f"| {_quando(i['quando'])} | {i['tipo']} | {i.get('empresa') or i['id']} | {i.get('erro', '')} |" for i in err]
        linhas.append("")

    def tabela(titulo: str, itens: list[dict]) -> None:
        linhas.extend([f"## {titulo}", "", "| Quando | Tipo | O quê | Cidade | Status |", "|---|---|---|---|---|"])
        grupos: list[list[dict]] = []
        for i in itens:  # stories da mesma cidade e horário viram uma linha só
            if grupos and i["tipo"] == "story" and grupos[-1][0]["tipo"] == "story" \
                    and grupos[-1][0]["quando"][:16] == i["quando"][:16] and grupos[-1][0]["status"] == i["status"]:
                grupos[-1].append(i)
            else:
                grupos.append([i])
        for g in grupos:
            i = g[0]
            oque = f"{len(g)} stories da lista de ganhadores" if i["tipo"] == "story" else i.get("empresa") or i["id"]
            tipo = "story" if i["tipo"] == "story" else "post (carrossel)"
            link = f" · [ver]({i['permalink']})" if i.get("permalink") else ""
            linhas.append(f"| {_quando(i['quando'])} | {tipo} | {oque} | {i.get('cidade', '')} | {ICONE[i['status']]}{link} |")
        linhas.append("")

    tabela("⏳ Próximas publicações", sorted(pend, key=lambda i: i["quando"]))
    if pub:
        tabela("✅ Últimas publicadas", sorted(pub, key=lambda i: i["quando"], reverse=True)[:30])
    (AQUI / "FILA.md").write_text("\n".join(linhas), encoding="utf-8")


if __name__ == "__main__":
    gerar()
