#!/usr/bin/env python3
"""data/stats.json + data/portrait.txt  ->  assets/*.svg

Szabványos könyvtár, semmi más. Az SVG-ket kézzel, sztringből építjük — nincs
sablonmotor, mert egy sablonmotor itt csak egy újabb függőség lenne, amit az
éjszakai workflow-nak telepítenie kell.

HÁROM MEGKÖTÉS, amit a GitHub támaszt, és ami az egész felépítést meghatározza:

1. A README-ben az SVG `<img>`-ként jelenik meg. Az `<img>`-be zárt SVG NEM tölt
   le külső erőforrást: se webfontot, se képet. Ezért a betűtípus base64-ként
   bele van írva a fájlba (lásd scripts/subset_font.py).

2. Ugyanezért nincs benne JavaScript sem — az `<img>`-SVG-ben a szkript nem fut.
   Az animáció SMIL (`<animate>`), ami viszont működik.

3. A GitHub világos és sötét témában is ugyanazt a fájlt mutatja, és az
   `<img>`-SVG nem tudja megkérdezni, melyik van érvényben. Ezért minden kártya
   SAJÁT sötét háttérrel rendelkezik: mindkét témában ugyanúgy néz ki. A
   `prefers-color-scheme` itt megbízhatatlan lenne, mert a néző operációs
   rendszerének beállítását olvassa, nem a GitHub témáját — a kettő simán
   eltérhet, és akkor sötét lapon sötét szövegű kártya lenne.
"""
import base64, json, os, pathlib

# ----------------------------------------------------------------- vizuális nyelv
BG      = "#0d1117"   # ugyanaz, mint a GitHub sötét vászna — ott beleolvad
PANEL   = "#11161d"
BORDER  = "#222c38"
FG      = "#e6edf3"
DIM     = "#8b949e"
FAINT   = "#3d4753"
ACCENT  = "#58a6ff"
WARM    = "#f0a04b"
GREEN   = "#3fb950"
# a hőtérkép skálája szándékosan a GitHub sajátja: ismerős, és rögtön olvasható
HEAT    = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]

ADV = 0.600           # JetBrains Mono: 600/1000 em karakterenként
LINE = 1 / 0.48       # a portré rácsának sormagassága karakterszélességben

ROOT = pathlib.Path(__file__).resolve().parent.parent


def cw(size):
    """Egy karakter szélessége adott betűméretnél."""
    return size * ADV


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ----------------------------------------------------------------- betűtípus
def font_css():
    out = []
    for name, weight in (("jbmono-regular", 400), ("jbmono-bold", 700)):
        p = ROOT / "assets" / "fonts" / (name + ".b64")
        if not p.exists():
            continue
        out.append(
            "@font-face{font-family:'JBMono';font-style:normal;font-weight:%d;"
            "src:url(data:font/woff;base64,%s) format('woff');}" % (weight, p.read_text().strip()))
    out.append(".f{font-family:'JBMono','SFMono-Regular',Consolas,monospace;}")
    return "".join(out)


def svg(w, h, body, title):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">'
        f"<title>{esc(title)}</title>"
        f"<defs><style>{font_css()}</style></defs>"
        f'<rect width="{w}" height="{h}" rx="10" fill="{BG}"/>'
        f'<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="9.5" fill="none" stroke="{BORDER}"/>'
        f"{body}</svg>\n")


def text(x, y, s, size=12, fill=FG, weight=400, anchor="start", extra=""):
    return (f'<text class="f" x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" '
            f'font-weight="{weight}" text-anchor="{anchor}" {extra}>{esc(s)}</text>')


def label(x, y, s):
    """Kártyafejléc: kicsi, ritkított, halvány — nem versenyez az adattal."""
    return (f'<text class="f" x="{x}" y="{y}" font-size="10" fill="{DIM}" '
            f'letter-spacing="1.6">{esc(s.upper())}</text>')


def num(n):
    """Ezres tagolás keskeny szóközzel — a monospace rács így nem csúszik el."""
    return f"{n:,}".replace(",", " ")


# ----------------------------------------------------------------- gépelő animáció
def typing(phrases, x, y, size, cycle=14.0, fill=FG):
    """Gépelődő szöveg SMIL-lel, JavaScript nélkül.

    A trükk: a szöveget NEM építjük karakterenként. Mindegyik mondat egyben ott
    van, és egy `clipPath` téglalapja takarja ki; ennek a szélességét léptetjük
    karakterenként, `calcMode="discrete"`-tel. Így a betűk pontosan a rácson
    jelennek meg, és nem kell 40 külön `<tspan>` mondatonként.

    Miért egyetlen, `cycle` hosszú animáció mondatonként, és nem `begin`
    láncolás? Mert a láncolt `begin="elozo.end"` egyes renderelőkben (és a
    GitHub kép-proxija mögött) nem indul újra megbízhatóan. Egy önmagában
    ismétlődő, azonos hosszú animáció mindenhol ugyanazt csinálja.
    """
    n = len(phrases)
    slot = 1.0 / n
    out = []
    for i, p in enumerate(phrases):
        L = len(p)
        t0 = i * slot
        type_end = t0 + slot * 0.45        # gépelés
        hold_end = t0 + slot * 0.92        # állás, hogy el lehessen olvasni
        # kulcsidők: 0 -> t0 (üres), majd L lépés a gépeléshez, tartás, majd 0
        times, widths = [0.0], [0.0]
        if t0 > 0:
            times.append(t0); widths.append(0.0)
        for k in range(1, L + 1):
            times.append(t0 + (type_end - t0) * k / L)
            widths.append(cw(size) * k + 1)
        times.append(hold_end); widths.append(cw(size) * L + 1)
        times.append(min(1.0, hold_end + 1e-4)); widths.append(0.0)
        times.append(1.0); widths.append(0.0)
        # a keyTimes-nak szigorúan monoton növekvőnek kell lennie
        for j in range(1, len(times)):
            times[j] = max(times[j], times[j - 1] + 1e-6)
        times = [min(t, 1.0) for t in times]
        kt = ";".join(f"{t:.5f}" for t in times)
        vw = ";".join(f"{w:.2f}" for w in widths)
        cid = f"clip{i}"
        out.append(
            f'<clipPath id="{cid}"><rect x="{x}" y="{y - size}" height="{size * 1.5:.1f}" width="0">'
            f'<animate attributeName="width" values="{vw}" keyTimes="{kt}" '
            f'dur="{cycle}s" calcMode="discrete" repeatCount="indefinite"/></rect></clipPath>')
        out.append(f'<g clip-path="url(#{cid})">{text(x, y, p, size, fill)}</g>')
        # a kurzor a most gépelt mondat végét követi
        out.append(
            f'<rect y="{y - size * 0.85:.1f}" width="{cw(size):.2f}" height="{size * 1.05:.1f}" '
            f'fill="{ACCENT}" opacity="0">'
            f'<animate attributeName="x" values="{";".join(f"{x + w - 1:.2f}" for w in widths)}" '
            f'keyTimes="{kt}" dur="{cycle}s" calcMode="discrete" repeatCount="indefinite"/>'
            f'<animate attributeName="opacity" '
            f'values="{";".join("0" if w == 0 else "1" for w in widths)}" '
            f'keyTimes="{kt}" dur="{cycle}s" calcMode="discrete" repeatCount="indefinite"/>'
            f'<animate attributeName="fill-opacity" values="1;1;0.15;1" dur="1.1s" '
            f'repeatCount="indefinite"/></rect>')
    return "".join(out)


# ----------------------------------------------------------------- 1. fejléc
def header(d, portrait):
    W = 900
    size = 7.6                       # a portré betűmérete
    ch, lh = cw(size), size * LINE
    pw, ph = ch * max(len(r) for r in portrait), lh * len(portrait)
    px, py = 34, 26
    # a jobb oldali oszlop fix rácsra van tervezve, ezért van alsó korlát:
    # ha a portré rácsa kisebb lenne, a szöveg akkor sem lóghat ki
    H = int(max(py * 2 + ph, 700))

    b = [f'<rect x="16" y="16" width="{W-32}" height="{H-32}" rx="8" fill="{PANEL}"/>']
    # --- portré
    for i, row in enumerate(portrait):
        b.append(f'<text class="f" xml:space="preserve" x="{px}" y="{py + lh * (i + 0.8):.2f}" '
                 f'font-size="{size}" fill="{FG}" letter-spacing="0">{esc(row)}</text>')

    cx = px + pw + 46
    cwid = W - cx - 34
    u, t, s = d["user"], d["totals"], d["streak"]

    def rule(y):
        return f'<rect x="{cx}" y="{y}" width="{cwid}" height="1" fill="{BORDER}"/>'

    b.append(text(cx, 78, u["name"], 32, FG, 700))
    b.append(text(cx, 104, "Szoftverfejlesztő · Budapest", 12.5, DIM))
    b.append(rule(122))

    # A gépelődő sor az egyetlen mozgó elem. Szándékosan: ha minden animál,
    # semmi nem hívja fel magára a figyelmet.
    #
    # A négy mondatban NINCS darabszám ("hat projekt", "négy nyelv"). Az ilyen
    # kézzel beírt szám a következő repónál elavul, és senki nem veszi észre —
    # a projektek és a nyelvek számát úgyis a kártyák számolják ki az adatból.
    b.append(typing([
        "Flutter appok · .NET + Angular webek",
        "shift_app · FitnessApp · TeamCalendar",
        "árnyékoló konfigurátor JS-ben, teszttel",
        "most éppen: Magic xpa / xpi",
    ], cx, 154, 13))

    b.append(rule(176))
    bio = ["Mobilappokat írok Flutterben, webet .NET-ben és",
           "Angularban. A legutóbbi egy B2B konfigurátor —",
           "adatmodell, szabálymotor, árazás, integrációk."]
    for i, ln in enumerate(bio):
        b.append(text(cx, 206 + i * 18, ln, 11.5, DIM))
    b.append(rule(266))

    for i, (k, v) in enumerate([
            ("publikus repó", num(t["repos"])),
            ("hozzájárulás (52 hét)", num(t["contributions_year"])),
            ("aktuális sorozat", f'{s["current"]} nap'),
            ("GitHub óta", u["since"])]):
        yy = 296 + i * 24
        b.append(text(cx, yy, k, 11.5, DIM))
        b.append(text(cx + cwid, yy, v, 11.5, FG, 700, anchor="end"))
    b.append(rule(392))

    # --- nyelvek: egyetlen összefüggő sáv, alatta a három legnagyobb
    b.append(label(cx, 418, "Nyelvek"))
    x = float(cx)
    for l in d["languages"]:
        w = cwid * l["pct"] / 100.0
        b.append(f'<rect x="{x:.1f}" y="430" width="{max(2, w):.1f}" height="8" fill="{l["color"]}"/>')
        x += w
    for i, l in enumerate(d["languages"][:3]):
        yy = 462 + i * 20
        b.append(f'<circle cx="{cx + 5}" cy="{yy - 4}" r="4.5" fill="{l["color"]}"/>')
        b.append(text(cx + 18, yy, l["name"], 11.5, FG))
        b.append(text(cx + cwid, yy, f'{l["pct"]:.1f}%', 11.5, DIM, anchor="end"))
    b.append(rule(534))

    # --- legutóbb mozgatott repók
    b.append(label(cx, 560, "Legutóbb frissítve"))
    for i, r in enumerate(d.get("repos", [])[:3]):
        yy = 584 + i * 20
        b.append(text(cx, yy, r["name"][:34], 11.5, FG))
        b.append(text(cx + cwid, yy, r["pushed"], 11, FAINT, anchor="end"))

    b.append(text(cx, H - py - 4, "github.com/" + u["login"], 11, ACCENT))
    b.append(text(W - 34, H - py - 4, "frissítve: " + d["generated"], 10, FAINT, anchor="end"))
    return svg(W, H, "".join(b), f'{u["name"]} — GitHub profil')


# ----------------------------------------------------------------- 2. áttekintés
def card_stats(d):
    W, H = 440, 210
    t, u = d["totals"], d["user"]
    b = [label(22, 30, "Áttekintés")]
    b.append(text(22, 74, num(t["contributions_year"]), 34, ACCENT, 700))
    b.append(text(22, 92, "hozzájárulás az elmúlt 52 hétben", 10.5, DIM))
    rows = [("publikus repó", t["repos"]), ("csillag", t["stars"]),
            ("összevont PR", t["merged_prs"]), ("nyitott/lezárt issue", t["issues"]),
            ("követő", u["followers"]), ("aktív repó idén", t["active_repos_year"])]
    for i, (k, v) in enumerate(rows):
        x = 22 + (i % 2) * 210
        y = 122 + (i // 2) * 28
        b.append(text(x, y, k, 11, DIM))
        b.append(text(x + 186, y, num(v), 12.5, FG, 700, anchor="end"))
    return svg(W, H, "".join(b), "Áttekintés")


# ----------------------------------------------------------------- 3. sorozat
def card_streak(d):
    W, H = 440, 210
    s, t = d["streak"], d["totals"]
    b = [label(22, 30, "Aktivitás")]
    cells = [("jelenlegi\nsorozat", s["current"], GREEN),
             ("leghosszabb\nsorozat", s["longest"], WARM),
             ("commit\n52 hét alatt", t["commits_year"], ACCENT)]
    for i, (k, v, c) in enumerate(cells):
        x = 22 + i * 138
        b.append(text(x, 78, num(v), 30, c, 700))
        for j, line in enumerate(k.split("\n")):
            b.append(text(x, 98 + j * 13, line, 10, DIM))
    # az utolsó 30 nap oszlopdiagramja: mutatja a ritmust, nem csak az összeget
    flat = [v for w in d["calendar"] for v in w][-30:]
    mx = max(flat, default=0) or 1
    b.append(text(22, 148, "utolsó 30 nap", 10, DIM))
    for i, v in enumerate(flat):
        h = max(2, round(38 * v / mx))
        b.append(f'<rect x="{22 + i * 13.2:.1f}" y="{192 - h}" width="9" height="{h}" rx="2" '
                 f'fill="{HEAT[min(4, 0 if v == 0 else 1 + int(3 * v / mx))]}"/>')
    return svg(W, H, "".join(b), "Aktivitás és sorozat")


# ----------------------------------------------------------------- 4. nyelvek
def card_langs(d):
    """Teljes szélességű sáv. Vízszintesen jobban olvasható, mint egy szűk
    listaoszlop: az arányt a hosszúság mutatja, nem a százalék elolvasása."""
    W, H = 900, 152
    langs = d["languages"][:6]
    b = [label(22, 32, "Nyelvek"),
         text(W - 22, 32, "a publikus, nem forkolt repók kódmérete szerint", 10.5, FAINT, anchor="end")]
    x = 22.0
    for l in langs:
        w = (W - 44) * l["pct"] / 100.0
        b.append(f'<rect x="{x:.1f}" y="54" width="{max(2, w):.1f}" height="14" fill="{l["color"]}"/>')
        x += w
    if x < W - 44 + 22:                      # a maradék (a 6 alattiak) semleges szürke
        b.append(f'<rect x="{x:.1f}" y="54" width="{W - 22 - x:.1f}" height="14" fill="{FAINT}"/>')
    # a sáv két vége lekerekítve: maszk helyett egy ráfestett keret, hogy
    # `<img>`-SVG-ben is biztosan ugyanúgy nézzen ki
    b.append(f'<rect x="21" y="53" width="{W-42}" height="16" rx="8" fill="none" '
             f'stroke="{BG}" stroke-width="3"/>')
    per = (W - 44) / max(1, min(3, len(langs)))
    for i, l in enumerate(langs):
        cx = 22 + (i % 3) * per
        y = 104 + (i // 3) * 24
        b.append(f'<circle cx="{cx + 5:.0f}" cy="{y - 4}" r="5" fill="{l["color"]}"/>')
        b.append(text(cx + 20, y, l["name"], 12.5, FG))
        b.append(text(cx + per - 26, y, f'{l["pct"]:.1f}%', 12.5, DIM, anchor="end"))
    if not langs:
        b.append(text(22, 100, "még nincs publikus kód", 12, DIM))
    return svg(W, H, "".join(b), "Nyelvek")


# ----------------------------------------------------------------- 5. hőtérkép
def card_year(d):
    weeks = d["calendar"]
    cell, gap = 11, 3
    W = 900
    top = 52
    H = top + 7 * (cell + gap) + 34
    mx = max((v for w in weeks for v in w), default=0) or 1
    b = [label(22, 30, "Hozzájárulások — utolsó 52 hét"),
         text(W - 22, 30, num(d["totals"]["contributions_year"]) + " összesen", 11, DIM, anchor="end")]
    x0 = (W - len(weeks) * (cell + gap)) / 2
    for wi, week in enumerate(weeks):
        for di, v in enumerate(week):
            # a küszöbök arányosak a csúccsal, nem fixek: így egy csendes év is
            # olvasható marad, nem lesz egyszínű üres tábla
            lvl = 0 if v == 0 else min(4, 1 + int(3.0 * (v - 1) / max(1, mx - 1)))
            b.append(f'<rect x="{x0 + wi * (cell + gap):.1f}" y="{top + di * (cell + gap)}" '
                     f'width="{cell}" height="{cell}" rx="2.5" fill="{HEAT[lvl]}"/>')
    ly = H - 14
    b.append(text(x0, ly, "kevesebb", 10, DIM))
    for i, c in enumerate(HEAT):
        b.append(f'<rect x="{x0 + 58 + i * 15:.0f}" y="{ly - 9}" width="11" height="11" rx="2.5" fill="{c}"/>')
    b.append(text(x0 + 58 + 5 * 15 + 4, ly, "több", 10, DIM))
    b.append(text(W - 22, ly, f'csúcs: {mx} / nap', 10, FAINT, anchor="end"))
    return svg(W, H, "".join(b), "Hozzájárulási naptár")


# ----------------------------------------------------------------- futtatás
def stale_badge(d, W, H, name=""):
    """Ha az adat még a bootstrap-fájlból jön, mondjuk ki.

    Nullát mutatni úgy, mintha mérés lenne, félrevezető. Viszont az egész
    kártyát letakarni is túlzás — egy sarokba tett, feltűnő színű csík elég.
    A workflow első lefutása után magától eltűnik, mert a generált stats.json
    nem tartalmazza a `placeholder` mezőt."""
    if not d.get("placeholder"):
        return ""
    w, y = 330, H - 26
    if name == "year.svg":           # ott a kártya alján a jelmagyarázat áll
        y = H * 0.42
    return (f'<rect x="{W - w - 14}" y="{y:.0f}" width="{w}" height="17" rx="8" '
            f'fill="{WARM}" opacity="0.16"/>'
            + text(W - w - 2, y + 13, "bootstrap adat — az első futás felülírja", 10.5, WARM, 700))


def main():
    d = json.loads((ROOT / "data" / "stats.json").read_text(encoding="utf-8"))
    portrait = (ROOT / "data" / "portrait.txt").read_text(encoding="utf-8").split("\n")
    portrait = [p for p in portrait if p.strip()] or [" "]
    out = ROOT / "assets"
    out.mkdir(exist_ok=True)
    files = {
        "header.svg": header(d, portrait),
        "stats.svg": card_stats(d),
        "streak.svg": card_streak(d),
        "langs.svg": card_langs(d),
        "year.svg": card_year(d),
    }
    for name, body in files.items():
        if d.get("placeholder"):
            import re
            m = re.search(r'width="(\d+)" height="(\d+)"', body)
            body = body.replace("</svg>", stale_badge(d, int(m.group(1)), int(m.group(2)), name) + "</svg>")
        (out / name).write_text(body, encoding="utf-8")
        print(f"assets/{name}  {len(body.encode()) / 1024:.0f} kB")


if __name__ == "__main__":
    main()
