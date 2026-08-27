"""Le service worker et la coquille qu'il met en cache.

La liste COQUILLE de sw.js est écrite à la main. Un module JS ajouté et
oublié de cette liste marche en ligne et casse hors ligne, sans le
moindre message. Ce test rend l'oubli visible tout de suite.
"""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"


def coquille() -> set[str]:
    texte = (WEB / "sw.js").read_text(encoding="utf-8")
    bloc = re.search(r"COQUILLE\s*=\s*\[(.*?)\]", texte, re.S).group(1)
    return set(re.findall(r'"([^"]+)"', bloc))


def test_tout_module_js_est_dans_la_coquille():
    listes = coquille()
    modules = {f"/{p.relative_to(WEB).as_posix()}"
               for p in WEB.glob("js/**/*.js")}
    manquants = modules - listes
    assert not manquants, f"absents de COQUILLE dans sw.js: {sorted(manquants)}"


def test_la_coquille_ne_reference_pas_de_fichier_absent():
    for entree in coquille():
        if entree in ("/", "/index.html"):
            continue
        assert (WEB / entree.lstrip("/")).exists(), f"{entree} n'existe pas"
