#!/usr/bin/env python3
"""ASCII-portré előállítása fotóból.

A csővezeték az ASCII Portrait README Guide szerint, két eltéréssel:
  - rembg helyett OpenCV GrabCut vágja ki az alanyt (nincs 176 MB-os modell)
  - a vágás automatikus: Haar-arcdetektálás, majd hajtól állig szoros keret

Kimenet: az ASCII sorok listája, plusz egy PNG előnézet ellenőrzéshez.
"""
import cv2, numpy as np, sys
from PIL import Image, ImageDraw, ImageFont

RAMP = " .`:-=+*cs#%@"          # 13 fokozat, a szóköz üríti a hátteret
COLS = 108
ASPECT = 0.48                    # a monospace karakter kb. kétszer olyan magas, mint széles

# Tónus-paraméterek. Ezek nem általános alapértékek, hanem ERRE a fotóra
# beállított értékek: több változatot kirendereltem és a valós, 460 px-es
# megjelenítési méreten hasonlítottam össze (out/gh_final.png).
CLIP, TILE = 5.0, 6              # kis CLAHE-csempe = több helyi kontraszt
GAMMA = 1.0                      # a nyújtás után nincs szükség külön görbére
LO, HI = 4.0, 62.0               # az alany pixeleinek percentilisei
BIL = 11                         # bilaterális simítás: a bőrpórust elveszi, az élt nem


def tight_crop(img):
    """Hajtól állig, az arcra szorítva."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = cc.detectMultiScale(g, 1.1, 6, minSize=(200, 200))
    if len(faces) == 0:
        raise SystemExit("nem találtam arcot")
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    cx = x + w / 2
    top = int(y - 0.52 * h)                 # a haj teteje fölé
    bot = int(y + 1.10 * h)                 # épp az áll alá — a sötét póló kimarad
    half = int((bot - top) * 0.46)          # a magasságból származtatott szélesség
    l, r = int(cx - half), int(cx + half)
    H, W = img.shape[:2]
    pad_t, pad_b = max(0, -top), max(0, bot - H)
    pad_l, pad_r = max(0, -l), max(0, r - W)
    if pad_t or pad_b or pad_l or pad_r:
        img = cv2.copyMakeBorder(img, pad_t, pad_b, pad_l, pad_r,
                                 cv2.BORDER_REPLICATE)
        top, bot, l, r = top + pad_t, bot + pad_t, l + pad_l, r + pad_l
    return img[top:bot, l:r]


def cut_out(img):
    """Alany kivágása GrabCut-tal, arc-ellipszissel megvezetve.

    A puszta téglalapos indítás a konyhai háttér darabjait bent hagyta, ezért a
    maszkot előre feltöltjük: középen biztos előtér, a sarkokban biztos háttér.
    Visszaadja a szürkeárnyalatos képet és az alany maszkját.
    """
    h, w = img.shape[:2]
    mask = np.full((h, w), cv2.GC_PR_BGD, np.uint8)
    # az alany nagyjából a keret közepén, függőlegesen megnyújtott ellipszisben
    cv2.ellipse(mask, (w // 2, int(h * 0.52)), (int(w * 0.40), int(h * 0.47)),
                0, 0, 360, cv2.GC_PR_FGD, -1)
    cv2.ellipse(mask, (w // 2, int(h * 0.52)), (int(w * 0.26), int(h * 0.34)),
                0, 0, 360, cv2.GC_FGD, -1)
    m = int(min(w, h) * 0.06)
    mask[:m, :] = cv2.GC_BGD
    mask[:, :m] = cv2.GC_BGD
    mask[:, -m:] = cv2.GC_BGD
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(img, mask, None, bgd, fgd, 5, cv2.GC_INIT_WITH_MASK)
    fg = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype("uint8")
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((15, 15), np.uint8))
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    # csak a legnagyobb összefüggő folt marad — a hűtő és a csempe kiesik
    n, lab, stats, _ = cv2.connectedComponentsWithStats((fg > 127).astype("uint8"), 8)
    if n > 1:
        big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        fg = np.where(lab == big, 255, 0).astype("uint8")
    fg = cv2.GaussianBlur(fg, (0, 0), 4)
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return g, fg


def tone(g, fg, clip=CLIP, gamma=GAMMA, lo=LO, hi=HI, tile=TILE, bil=BIL):
    """Simítás, helyi kontraszt, majd az ALANY kiterítése a teljes rámpára.

    A kulcs a percentilises nyújtás, és nem a README-ben javasolt globális
    (v/255)^1.7 sötétítés. A fotó frontálisan, lapos fényben készült: a globális
    görbe az egész arcot egyszerre húzza le, és egyetlen sötét folt lesz belőle.
    A percentilises nyújtás viszont CSAK az alany pixelein számol, és a felső
    határt szándékosan alacsonyra (hi≈62) teszi, így a bőr fehérre telítődik, és
    csak a valódi vonások — szemöldök, szem, bajusz, száj, haj, állvonal —
    esnek a rámpa sűrű végére.
    """
    g = cv2.bilateralFilter(g, bil, 75, 75)
    g = cv2.createCLAHE(clipLimit=clip, tileGridSize=(tile, tile)).apply(g)
    subj = g[fg > 200]
    if subj.size:
        a, b = np.percentile(subj, lo), np.percentile(subj, hi)
        if b > a:
            g = np.clip((g.astype(np.float32) - a) * (255.0 / (b - a)), 0, 255)
    g = np.power(g / 255.0, gamma) * 255.0
    a = fg.astype(np.float32) / 255.0
    return (g * a + 255.0 * (1 - a)).astype(np.uint8)


def to_ascii(g, cols=COLS):
    h, w = g.shape
    rows = max(1, int(cols * (h / w) * ASPECT))
    small = cv2.resize(g, (cols, rows), interpolation=cv2.INTER_AREA)
    idx = (small.astype(np.float32) / 256.0 * len(RAMP)).astype(int)
    idx = np.clip(len(RAMP) - 1 - idx, 0, len(RAMP) - 1)   # sötét = sűrű karakter
    return ["".join(RAMP[i] for i in row) for row in idx]


def preview_png(lines, path, cw=8, ch=17):
    """Monospace előnézet, hogy meg lehessen nézni, mit rajzoltunk."""
    W, H = cw * len(lines[0]) + 20, ch * len(lines) + 20
    im = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(im)
    try:
        f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 14)
    except Exception:
        f = ImageFont.load_default()
    for i, ln in enumerate(lines):
        d.text((10, 10 + i * ch), ln, font=f, fill=20)
    im.save(path)


def trim(lines):
    """Üres sorok/oszlopok levágása, hogy a rács ne vigyen felesleges helyet."""
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    l = min((len(s) - len(s.lstrip()) for s in lines if s.strip()), default=0)
    r = max((len(s.rstrip()) for s in lines), default=0)
    return [s[l:r] for s in lines]


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "src/foto.jpg"
    img = cv2.imread(src)
    crop = tight_crop(img)
    cv2.imwrite("out/crop.jpg", crop)
    grey, fg = cut_out(crop)
    cv2.imwrite("out/mask.jpg", fg)
    g = tone(grey, fg)
    cv2.imwrite("out/tone.jpg", g)
    lines = trim(to_ascii(g))
    open("out/portrait.txt", "w").write("\n".join(lines))
    preview_png(lines, "out/portrait_preview.png")
    print("vágott kép:", crop.shape[1], "x", crop.shape[0])
    print("ASCII rács:", len(lines[0]), "oszlop x", len(lines), "sor")
