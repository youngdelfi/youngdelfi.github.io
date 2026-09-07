#!/usr/bin/env python3
"""Arma design/releva-navegacion.html (un solo archivo, para el Artifact)
a partir de las fuentes legibles en design/releva-app/ (index.html, styles.css, app.js).
Correr despues de editar cualquiera de esas tres fuentes."""
import re
from pathlib import Path

SRC = Path(__file__).parent / "releva-app"
OUT = Path(__file__).parent / "releva-navegacion.html"

index = (SRC / "index.html").read_text(encoding="utf-8")
css = (SRC / "styles.css").read_text(encoding="utf-8")
js = (SRC / "app.js").read_text(encoding="utf-8")

out = index.replace(
    '<link rel="stylesheet" href="styles.css">',
    f"<style>\n{css}</style>",
    1,
)
out = re.sub(
    r'<script src="app\.js"></script>\n?$',
    lambda m: f"<script>\n{js}</script>\n",
    out,
)

OUT.write_text(out, encoding="utf-8")
print(f"escrito {OUT} ({len(out)} bytes)")
