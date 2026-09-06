#!/usr/bin/env python3
"""JetBrains Mono leszűkítése és base64-be csomagolása.

Miért kell egyáltalán beágyazni? Az SVG-t a GitHub <img>-ként rendereli, és az
<img>-be zárt SVG nem tölthet le külső erőforrást — a `<link>` a Google Fontsra
és a `src: url(https://…)` is némán elbukik, a szöveg pedig visszaesik a néző
gépén épp elérhető betűtípusra. Az ASCII-portré viszont CSAK akkor áll össze
képpé, ha minden karakter pontosan ugyanolyan széles. Ezért a betűtípust
base64 data URI-ként bele kell írni a fájlba.

Ez viszont minden SVG méretét megnöveli, ezért csak azokat a jeleket tartjuk
meg, amiket tényleg használunk. woff-ot állítunk elő, nem woff2-t: a woff2
tömörítéshez brotli kell, ami itt nem elérhető. A woff nagyobb, de minden mai
böngésző érti.

Futtatás egyszeri, a kimenet (assets/fonts/*.b64) verziókövetett — az éjszakai
workflow-nak nem kell se fonttools, se hálózat.
"""
import base64, pathlib, sys
from fontTools import subset
from fontTools.ttLib import TTFont

# A ténylegesen használt jelkészlet. Az ASCII-rámpa 13 jele mind benne van az
# alap ASCII-tartományban; a magyar ékezetek a nevekhez és a feliratokhoz
# kellenek; a néhány szimbólum a statisztika-kártyák díszítése.
CHARS = (
    "".join(chr(c) for c in range(0x20, 0x7F))          # nyomtatható ASCII
    + "áéíóöőúüűÁÉÍÓÖŐÚÜŰ"                              # magyar
    + "·•–—…→←↑↓✓×≈±°"                                   # tipográfia és jelek
    + "█▓▒░"                                             # tömör sávok a diagramokhoz
)

SRC = pathlib.Path("src/fonts/ttf")
DST = pathlib.Path("assets/fonts")


def build(name, out):
    font = TTFont(SRC / name)
    opts = subset.Options()
    opts.flavor = "woff"           # woff2-höz brotli kellene
    opts.desubroutinize = True
    opts.layout_features = []      # nincs ligatúra: monospace rácsot akarunk
    opts.name_IDs = ["*"]          # a licenc- és szerzőmezők maradjanak benne
    opts.notdef_outline = True
    sub = subset.Subsetter(options=opts)
    sub.populate(text=CHARS)
    sub.subset(font)
    tmp = DST / (out + ".woff")
    font.flavor = "woff"
    font.save(tmp)
    b = tmp.read_bytes()
    (DST / (out + ".b64")).write_text(base64.b64encode(b).decode())
    tmp.unlink()
    print(f"{out}: {len(b)} bájt woff -> {len(b) * 4 // 3} bájt base64")


if __name__ == "__main__":
    DST.mkdir(parents=True, exist_ok=True)
    build("JetBrainsMono-Regular.ttf", "jbmono-regular")
    build("JetBrainsMono-Bold.ttf", "jbmono-bold")
    # a rácsot csak akkor tudjuk pontosan számolni, ha ismerjük az előtolást
    f = TTFont(SRC / "JetBrainsMono-Regular.ttf")
    upm = f["head"].unitsPerEm
    adv = f["hmtx"]["A"][0]
    print(f"unitsPerEm={upm}  advance('A')={adv}  -> {adv / upm:.3f} em / karakter")
