"""Import du livre de règles (Livre_des_armées_d_Orbis_Naturae.xlsx) vers le jeu.

    python src/livre_import.py          # régénère src/armees_livre.json + rapport

Le livre reste la source: ce script le lit (bibliothèque standard seule, le
.xlsx est un zip de XML), convertit chaque unité au format de
unit_library.UNIT_DATABASE et écrit armees_livre.json, que unit_library
charge au démarrage. Les unités déjà réglées à la main dans UNIT_DATABASE
ne sont jamais écrasées (cf. unit_library.load_livre_into_db).

Conversions (calquées sur les unités converties à la main):
    - portées divisées par deux (échelle de la grille); une arme de mêlée
      plafonne à 3 cases (4 et plus = arme de tir pour le moteur);
    - « a/b* » (valeur normale / valeur spéciale, en charge...): valeur normale;
    - cellules converties en date par Excel (« 1/2 » → 01/02): premier nombre;
    - sauvegarde « — » ou 0 → 7 (aucune); bravoure inconnue → 1;
    - « [N] », « (xN) » dans le nom d'une arme de tir → trait Munitions (N);
    - « ** » en déplacement ou trait Artillerie → machine de guerre;
    - lanceurs de sorts (Sortilèges, Lanceur de sort...): le livre ne dit pas
      lesquels, ils reçoivent les sorts du Mage de guerre (à ajuster).
"""
import datetime
import json
import os
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
XLSX = os.path.join(HERE, "Livre_des_armées_d_Orbis_Naturae.xlsx")
OUT = os.path.join(HERE, "armees_livre.json")

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_EXCEL_EPOCH = datetime.date(1899, 12, 30)

# Titre de section du livre → armée du jeu. None: section ignorée.
SECTIONS = {
    "Armée Skaldienne": "Armée Skaldienne",
    "Collège de magie": "Collège de magie",
    "Ordre de Chevalerie": "Ordre de Chevalerie",
    "Ordre Eternel": "Ordre Eternel",
    "Invocation Eternel": "Ordre Eternel",
    "Légion sacrée": "Légion sacrée",
    "Cheval": "Héros",                 # héros rangés sous un titre « Cheval »
    "Armée Orlandar": "Armée Orlandar",
    "Draconie": "Draconie",
    "Arkkar": "Arkkar",
    "Al-Athar": "Al-Athar",
    "Armée Aïdatienne": "Armée Aïdatienne",
    "Armée Marcheurs Jaunes": "Armée Marcheurs Jaunes",
    "Armée Muhr": "Armée Muhr",
    "Armée Huǒ shé": "Armée Huǒ shé",
    "Invocations du Tao": "Armée Huǒ shé",
    "Armée Vancest": None,             # titre sans unités
    "Armée Erast": "Armée Erast",
    "Unité commune": "Armée Erast",
    "Clan Marsik": "Armée Erast",
    "Clan Firast": "Armée Erast",
}
# Sections dont toutes les unités sont des héros
HERO_SECTIONS = {"Cheval", "Al-Athar"}

COLORS = {
    "Collège de magie": (120, 150, 230),
    "Ordre de Chevalerie": (70, 110, 190),
    "Ordre Eternel": (150, 150, 130),
    "Arkkar": (200, 110, 50),
    "Al-Athar": (220, 180, 70),
    "Armée Aïdatienne": (40, 170, 170),
    "Armée Marcheurs Jaunes": (225, 205, 50),
    "Armée Muhr": (190, 150, 90),
    "Armée Huǒ shé": (200, 50, 50),
    "Armée Erast": (130, 100, 80),
}

# Sorts donnés aux lanceurs (le livre ne les précise pas): ceux du Mage de guerre
DEFAULT_SPELLS = ["Boule de feu", "Soin", "Armure magique", "Projectile magique", "Mur de force"]
_CASTER = ("sort de bataille", "sorts de bataille", "sortilege", "lanceur de sort",
           "sort (", "sort eternel", "sorts du tao")
_RANGED_NAME = ("lancer", "lance ", "lancé", "bombe", "javelot", "projectile", "fronde")
_POLEARMS = ("lance", "yari", "pique", "hallebarde", "hallbarde", "naginata", "faux", "epieu")
# Grandes créatures (type Large, emprise 2×2) que ni le trait ni les PV ne signalent
_LARGE_NAME = r"elephant|crocodile|golem|dragon|behemoth|geant|rhino"


def _norm(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text)
                   if not unicodedata.combining(c)).lower().strip()


# ── Lecture brute du classeur ──


def read_rows(path=XLSX):
    """[{colonne: texte}] pour chaque ligne non vide de la première feuille."""
    z = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(_NS + "si"):
            shared.append("".join(t.text or "" for t in si.iter(_NS + "t")))
    rows = []
    for row in ET.fromstring(z.read("xl/worksheets/sheet1.xml")).iter(_NS + "row"):
        cells = {}
        for c in row.findall(_NS + "c"):
            col = re.match(r"[A-Z]+", c.get("r")).group()
            v = c.find(_NS + "v")
            if v is None:
                inline = c.find(_NS + "is")
                val = "".join(t.text or "" for t in inline.iter(_NS + "t")) if inline is not None else ""
            else:
                val = shared[int(v.text)] if c.get("t") == "s" else v.text
            val = (val or "").replace("_x007f_", "").strip()
            if val:
                cells[col] = val
        if cells:
            rows.append(cells)
    return rows


# ── Valeurs ──


def _undate(v):
    """Une saisie « 1/2 » que Excel a changée en date: le premier nombre."""
    if v > 20000:
        return (_EXCEL_EPOCH + datetime.timedelta(days=int(v))).day
    return v


def num(raw):
    """Nombre d'une cellule du livre, ou None (« — », « ... », « ** »)."""
    if raw is None or str(raw).lstrip().startswith("*"):
        return None                               # « *1 »: renvoi à une note
    s = str(raw).split("—>")[0].split("/")[0]
    s = re.sub(r"[*²\sMm]", "", s)
    try:
        v = _undate(float(s))
    except ValueError:
        return None
    return int(v) if float(v).is_integer() else v


def dice(raw):
    """Dégâts « 1 », « 1d2 », « 2+1d4 » (valeur normale si « a/b »)."""
    if raw is None:
        return None
    s = re.sub(r"[*²\s]", "", str(raw).split("/")[0]).lower()
    try:
        return str(int(_undate(float(s))))
    except ValueError:
        pass
    return s if re.fullmatch(r"\d+d\d+|\d+\+\d+d\d+", s) else None


def reach(raw):
    """Portée brute du livre (« 10-50 » → 50)."""
    if raw is None:
        return None
    m = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", str(raw))
    return int(m.group(2)) if m else num(raw)


def clean_trait(raw):
    t = re.sub(r"[*²\"]", "", raw).strip()
    t = re.sub(r"\s+", " ", t)
    if not t or re.fullmatch(r"x\d+", t) or t.startswith("("):
        return None
    return t


def split_ammo(name):
    """« Arbalète [4] » → (« Arbalète », 4); sans marque: (nom, None)."""
    m = re.search(r"\s*[\(\[]\s*x?\s*(\d+)\s*x?\s*[\)\]]", name)
    clean = re.sub(r"[*²]", "", name if m is None else name[:m.start()] + name[m.end():]).strip()
    return clean, (int(m.group(1)) if m else None)


def game_range(raw_range, name, ammo):
    """Portée du jeu: moitié du livre; mêlée plafonnée à 3, tir au moins 4."""
    r = reach(raw_range)
    if r is None:
        return None
    n = _norm(name)
    ranged = r >= 8 or (r >= 6 and (ammo is not None or any(k in n for k in _RANGED_NAME)))
    half = int(r / 2 + 0.5)
    if ranged:
        return max(4, half)
    # Armes d'hast (lance, pique...) à 2 dans le livre: allonge 2, comme les
    # lances de cavalerie converties à la main; épée ou hache à 2: contact.
    if r >= 2 and any(k in n for k in _POLEARMS):
        half = max(2, half)
    return min(3, max(1, half))


# ── Conversion ──


def _weapon(cells, report, unit_name):
    raw_name = cells.get("F", "").strip()
    if not raw_name or raw_name in ("—",):
        return None, None
    name, ammo = split_ammo(raw_name)
    porte = game_range(cells.get("G"), name, ammo)
    att = num(cells.get("H"))
    if att is None and cells.get("H", "").strip("*") in ("", "**", "—"):
        att = 1                                   # machines: « ** »
    tou, bl = num(cells.get("I")), num(cells.get("J"))
    perf = num(cells.get("K")) if cells.get("K") else 0
    deg = dice(cells.get("L"))
    if None in (porte, att, tou, bl, perf, deg):
        report.append(f"  arme ignorée: {unit_name} / {raw_name} (valeurs illisibles)")
        return None, None
    return [name, porte, att, tou, bl, perf, deg], (ammo if porte >= 4 else None)


def _traits(cells):
    return [t for t in (clean_trait(cells[c]) for c in ("M", "N", "O") if c in cells) if t]


def _finish(u, hero, report):
    """Complète une unité lue (type, taille, rôle, munitions, sorts)."""
    raw, name = u.pop("_raw"), u["nom"]
    if not u["armes"]:
        report.append(f"ignorée: {name} (aucune arme lisible)")
        return None
    pv, mv = num(raw.get("C")), num(raw.get("B"))
    mv_txt = raw.get("B", "")
    # Machine de guerre: déplacement « ** » (« 3M/** »: poussée à bras) ou
    # « —* », ou trait Artillerie (sauf un héros qui porte aussi une arme
    # de jet, comme Zarog le Géant)
    artillery = ("**" in mv_txt or (mv is None and any(k in mv_txt for k in ("*", "—")))
                 or (not hero and any("artillerie" in _norm(t) for t in u["traits"])))
    if pv is None or (mv is None and not artillery):
        report.append(f"ignorée: {name} (PV ou déplacement illisible: {raw.get('C')!r}, {mv_txt!r})")
        return None
    brav = num(raw.get("D"))
    save = num(raw.get("E"))
    notes = []
    if brav is None:
        brav = 1
        notes.append(f"bravoure « {raw.get('D', '')} » → 1")
    if save is None or save <= 0:
        save = 7
    ntraits = [_norm(t) for t in u["traits"]]
    if artillery:
        utype = "Artillerie"
    elif hero:
        utype = "Héros"
    elif (any(t.startswith("charge montee") or t.startswith("charge de char") for t in ntraits)
          or re.search(r"cavalier|cavalerie|chars|cheval|monte|rhino", _norm(name))):
        utype = "Cavalerie"
    elif "large" in ntraits or "(l)" in _norm(name) or pv >= 8 or re.search(_LARGE_NAME, _norm(name)):
        utype = "Monstre" if pv >= 8 else "Large"
    else:
        utype = "Infanterie"
    size = 3 if pv >= 10 and utype != "Héros" else (
        2 if utype in ("Cavalerie", "Large", "Monstre") or (artillery and pv >= 4)
        or (hero and re.search(_LARGE_NAME, _norm(name))) else 1)
    ranged = any(a[1] >= 4 for a in u["armes"])
    casters = any(t.startswith(_CASTER) for t in ntraits)
    if artillery or (ranged and not any(a[1] < 4 for a in u["armes"])):
        role = "back"
    elif hero or casters or "encouragement" in ntraits or utype == "Cavalerie":
        role = "mid"
    else:
        role = "front"
    ammo = u.pop("_ammo")
    if ammo and not artillery:
        u["traits"].append(f"Munitions ({ammo})")
    u.update(deplacement=mv if mv is not None else 1, blessure=int(pv), bravoure=int(brav),
             sauvegarde=int(save), role=role, size=size, unit_type=utype)
    if casters:
        u["sorts"] = list(DEFAULT_SPELLS)
        notes.append("sorts du Mage de guerre par défaut")
    prix = num(raw.get("P"))
    if prix is not None:
        u["prix"] = prix
    if notes:
        report.append(f"  {name}: " + "; ".join(notes))
    return u


def parse_livre(path=XLSX):
    """{armée: {"color": [r, g, b], "units": [définitions]}} et le rapport."""
    armies, report = {}, []
    army, hero, section = None, False, None
    cur = None

    def flush():
        nonlocal cur
        if cur is not None and army is not None:
            u = _finish(cur, hero, report)
            if u is not None:
                armies.setdefault(army, {"color": list(COLORS.get(army, (160, 160, 160))),
                                         "units": []})["units"].append(u)
        cur = None

    for cells in read_rows(path):
        a = cells.get("A", "").strip()
        if a == "Nom":
            continue
        if a and len(cells) == 1:                      # titre de section
            flush()
            if a == "Héros":
                hero = True
                if section == "Légion sacrée":
                    army = "Héros"
                continue
            if a not in SECTIONS:
                report.append(f"section inconnue ignorée: {a}")
                army = None
                continue
            section, army, hero = a, SECTIONS[a], a in HERO_SECTIONS
            continue
        if a:                                          # nouvelle unité
            flush()
            name = re.sub(r"[*²]", "", a).strip()
            cur = {"nom": name, "armes": [], "traits": [], "_raw": cells, "_ammo": None}
        if cur is None:
            continue
        w, ammo = _weapon(cells, report, cur["nom"])
        if w is not None:
            cur["armes"].append(w)
            if ammo and cur["_ammo"] is None:
                cur["_ammo"] = ammo
        for t in _traits(cells):
            if t not in cur["traits"]:
                cur["traits"].append(t)
    flush()
    return armies, report


def main():
    armies, report = parse_livre()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"source": os.path.basename(XLSX), "armies": armies}, f,
                  ensure_ascii=False, indent=1)
    n = sum(len(a["units"]) for a in armies.values())
    print(f"{n} unités dans {len(armies)} armées → {os.path.relpath(OUT)}")
    for line in report:
        print(line)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
