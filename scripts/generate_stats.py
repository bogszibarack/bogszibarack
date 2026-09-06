#!/usr/bin/env python3
"""GitHub-statisztikák lekérése a GraphQL API-ról -> data/stats.json.

Csak a Python szabványos könyvtárát használja (urllib, json, datetime). Ez
szándékos: az éjszakai workflow-nak így nincs `pip install` lépése, nincs
függőségi lockfile, és nem tud eltörni attól, hogy egy csomag új verziót adott
ki. Cserébe magunknak kell megírni a HTTP-hívást és a lapozást — ez ~30 sor.

Környezet:
    GH_TOKEN   GitHub token (a workflow-ban a beépített GITHUB_TOKEN)
    GH_LOGIN   a felhasználónév (alapértelmezés: bogszibarack)

DETERMINIZMUS. A fájl minden éjjel újragenerálódik és bekerül egy commitba.
Ha az adat véletlenszerűen ingadozik, minden éjjel keletkezik egy zajos commit,
és a repó előzménye használhatatlan lesz. Két csapdát kerülünk el:

  1. Az időablak EGÉSZ UTC-NAPOKRA van rögzítve (ma 00:00:00Z-ig), nem
     "most mínusz 365 nap"-ra. Különben a hívás pontos időpontja beleszámít az
     eredménybe, és a szám akkor is más lesz, ha semmit nem csináltunk.
  2. A repó-lekérdezés `privacy: PUBLIC` szűrőt kap. Token nélkül csak a
     publikus adat jönne, tokennel viszont a privát repók is beleszámítanának —
     így a szám attól függene, ki futtatja. Az kiszámíthatatlan, és ráadásul
     kiszivárogtatna privát információt egy publikus SVG-be.
"""
import json, os, sys, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

API = "https://api.github.com/graphql"
LOGIN = os.environ.get("GH_LOGIN", "bogszibarack")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")


def gql(query, variables):
    """Egyetlen GraphQL hívás. Hiba esetén beszédesen elszáll, nem csendben."""
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(API, data=body, method="POST", headers={
        "Authorization": "bearer " + TOKEN,
        "Content-Type": "application/json",
        "User-Agent": LOGIN + "-profile-generator",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"GraphQL HTTP {e.code}: {e.read()[:400].decode(errors='replace')}")
    if "errors" in data:
        sys.exit("GraphQL hiba: " + json.dumps(data["errors"])[:400])
    return data["data"]


# ---------------------------------------------------------------- időablak
def window():
    """Egész UTC-napokra igazított, 52 hetes ablak.

    A GitHub `contributionsCollection` legfeljebb egy évet ad vissza. 52*7 = 364
    napot kérünk: pontosan annyi hetet, amennyit a hőtérkép kirajzol, és
    vasárnaptól vasárnapig, hogy a naptár első oszlopa ne legyen csonka.
    """
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    end = today + timedelta(days=1) - timedelta(seconds=1)      # ma 23:59:59Z
    # visszalépünk a legutóbbi vasárnapra (a GitHub naptára vasárnappal kezdődik)
    start = today - timedelta(days=364)
    start -= timedelta(days=(start.weekday() + 1) % 7)
    return start.strftime("%Y-%m-%dT00:00:00Z"), end.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- lekérdezések
Q_PROFILE = """
query($login:String!, $from:DateTime!, $to:DateTime!) {
  user(login:$login) {
    name
    login
    createdAt
    followers { totalCount }
    following { totalCount }
    repositories(privacy:PUBLIC, isFork:false, ownerAffiliations:OWNER) { totalCount }
    pullRequests(states:MERGED) { totalCount }
    issues { totalCount }
    contributionsCollection(from:$from, to:$to) {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalPullRequestReviewContributions
      totalRepositoriesWithContributedCommits
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount weekday } }
      }
    }
  }
}"""

Q_REPOS = """
query($login:String!, $cursor:String) {
  user(login:$login) {
    repositories(first:100, after:$cursor, privacy:PUBLIC, isFork:false,
                 ownerAffiliations:OWNER, orderBy:{field:PUSHED_AT, direction:DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        stargazerCount
        forkCount
        pushedAt
        primaryLanguage { name }
        languages(first:12, orderBy:{field:SIZE, direction:DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}"""


def fetch_repos():
    """Lapozás kézzel. 100 repó/oldal, addig amíg van következő."""
    out, cursor = [], None
    while True:
        page = gql(Q_REPOS, {"login": LOGIN, "cursor": cursor})["user"]["repositories"]
        out.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            return out
        cursor = page["pageInfo"]["endCursor"]


def languages(repos):
    """Nyelvek bájtban összegezve, arányra váltva.

    Bájtot számolunk, nem repószámot: egy nyelv, amiben egy tízsoros configot
    írtunk, ne kapjon ugyanakkora súlyt, mint amiben az egész projekt van.
    A kompromisszum, hogy a bőbeszédűbb nyelvek felülreprezentáltak — ezt a
    kártya felirata ki is mondja ("kód mérete szerint").
    """
    tot = {}
    colors = {}
    for r in repos:
        for e in r["languages"]["edges"]:
            n = e["node"]["name"]
            tot[n] = tot.get(n, 0) + e["size"]
            colors[n] = e["node"]["color"] or "#8b949e"
    s = sum(tot.values()) or 1
    rank = sorted(tot.items(), key=lambda kv: (-kv[1], kv[0]))   # holtverseny: név szerint
    return [{"name": n, "bytes": b, "pct": round(100.0 * b / s, 1), "color": colors[n]}
            for n, b in rank]


def streaks(days):
    """Aktuális és leghosszabb sorozat.

    A MAI nap külön eset: ha ma még nincs commit, az nem szakítja meg a
    sorozatot — csak délután lesz belőle adat. Ezért ha az utolsó nap nulla,
    a számolást a tegnapi napnál kezdjük.
    """
    vals = [d["contributionCount"] for d in days]
    best = cur = 0
    for v in vals:
        cur = cur + 1 if v > 0 else 0
        best = max(best, cur)
    i = len(vals) - 1
    if i >= 0 and vals[i] == 0:
        i -= 1                       # a mai üres nap nem szakít
    now = 0
    while i >= 0 and vals[i] > 0:
        now += 1
        i -= 1
    return now, best


def main():
    if not TOKEN:
        sys.exit("Hiányzik a GH_TOKEN / GITHUB_TOKEN.")
    frm, to = window()
    u = gql(Q_PROFILE, {"login": LOGIN, "from": frm, "to": to})["user"]
    cc = u["contributionsCollection"]
    cal = cc["contributionCalendar"]
    days = [d for w in cal["weeks"] for d in w["contributionDays"]]
    repos = fetch_repos()
    cur, best = streaks(days)

    data = {
        # a generálás napja, nem az időpontja — különben minden futás diffet ad
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "window": {"from": frm, "to": to},
        "user": {
            "login": u["login"],
            "name": u["name"] or u["login"],
            "since": u["createdAt"][:10],
            "followers": u["followers"]["totalCount"],
            "following": u["following"]["totalCount"],
        },
        "totals": {
            "repos": u["repositories"]["totalCount"],
            "stars": sum(r["stargazerCount"] for r in repos),
            "forks": sum(r["forkCount"] for r in repos),
            "merged_prs": u["pullRequests"]["totalCount"],
            "issues": u["issues"]["totalCount"],
            "commits_year": cc["totalCommitContributions"],
            "prs_year": cc["totalPullRequestContributions"],
            "reviews_year": cc["totalPullRequestReviewContributions"],
            "issues_year": cc["totalIssueContributions"],
            "active_repos_year": cc["totalRepositoriesWithContributedCommits"],
            "contributions_year": cal["totalContributions"],
        },
        "streak": {"current": cur, "longest": best, "days_tracked": len(days)},
        "languages": languages(repos)[:8],
        # a hőtérképhez: hetenként 7 nap, csak a darabszám — a dátumot nem
        # visszük át, mert az ablak eleve rögzített és a fájlt így fele akkora
        "calendar": [[d["contributionCount"] for d in w["contributionDays"]]
                     for w in cal["weeks"]],
        "repos": [{"name": r["name"], "stars": r["stargazerCount"],
                   "lang": (r["primaryLanguage"] or {}).get("name"),
                   "pushed": r["pushedAt"][:10]} for r in repos[:6]],
    }
    os.makedirs("data", exist_ok=True)
    with open("data/stats.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    print(f"data/stats.json kiírva — {data['totals']['contributions_year']} hozzájárulás, "
          f"{len(repos)} repó, {len(data['languages'])} nyelv, sorozat {cur}/{best}")


if __name__ == "__main__":
    main()
