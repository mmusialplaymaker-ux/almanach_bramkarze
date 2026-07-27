#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
slim_bramkarze.py — odchudza PEŁNY eksport do zakresu apki almanach_bramkarze:
bramkarze roczników 2012/2013 (chłopcy), z zachowaniem WSZYSTKICH kolumn.

Różnica vs slim_data.py:
  - NIE przycina kolumn (nie zgubi keeper_count ani niczego, czego build potrzebuje),
  - NIE wybiera top-N po ogólnym PM Index (który wyrzucałby bramkarzy),
  - zostawia dokładnie tych zawodników, których apka i tak pokaże → plik mały, ranking wierny.

Kolejność: wyznacz_rocznik.py -> popraw_rocznik.py -> rename na full_* -> ten skrypt.

Użycie:
  python slim_bramkarze.py --stats full_stats.csv --matches full_matches.csv
  python slim_bramkarze.py --stats full_stats.csv --matches full_matches.csv --roczniki 2012,2013 --min-keeper 3
"""
import argparse
import re
import sys
import unicodedata

import pandas as pd

ENC = ("utf-8", "utf-8-sig", "cp1250", "latin-1")
_MALE_A = {"kuba", "barnaba", "bonawentura", "kosma", "dyzma", "jarema", "luka", "nikita",
           "mikita", "danila", "ilia", "kola", "sasza", "borna", "aleksa", "andrea", "nikola"}


def _is_girl(fullname):
    fn = str(fullname).strip().split(" ")[0].lower()
    return bool(fn) and fn.endswith("a") and fn not in _MALE_A


def rd(path):
    for e in ENC:
        try:
            return pd.read_csv(path, encoding=e, sep=None, engine="python",
                               dtype=str, keep_default_na=False)
        except Exception:
            continue
    raise RuntimeError(f"Nie udało się wczytać {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", default="full_stats.csv")
    ap.add_argument("--matches", default="full_matches.csv")
    ap.add_argument("--out-stats", default="stats_test.csv")
    ap.add_argument("--out-matches", default="matches_test.csv")
    ap.add_argument("--roczniki", default="2012,2013")
    ap.add_argument("--min-keeper", type=int, default=3,
                    help="min. meczów w bramce, by uznać za bramkarza (albo >=40%% meczów)")
    a = ap.parse_args()

    print(f"Wczytuję pełne dane: {a.stats} + {a.matches}")
    s, m = rd(a.stats), rd(a.matches)
    print(f"  stats {s.shape}, matches {m.shape}")
    if "keeper_count" not in s.columns:
        sys.exit("BŁĄD: stats nie ma kolumny keeper_count — eksport z ps.* powinien ją mieć.")

    roczniki = {int(x) for x in re.findall(r"\d{4}", a.roczniki)}

    # per zawodnik: suma keeper_count (stats) + liczba meczów (matches) + rocznik + imię
    kc = pd.to_numeric(s["keeper_count"], errors="coerce").fillna(0).groupby(s["player_id"]).sum()
    mc = m.groupby("player_id").size()
    first = s.drop_duplicates("player_id").set_index("player_id")
    byr = pd.to_numeric(first["est_birth_year"], errors="coerce")
    nm = (first["firstname"].astype(str) + " " + first["lastname"].astype(str))

    keep = []
    for pid in s["player_id"].unique():
        k = float(kc.get(pid, 0))
        mm = float(mc.get(pid, 0))
        is_gk = (k >= a.min_keeper) or (mm > 0 and k >= 0.4 * mm)
        if not is_gk:
            continue
        yv = byr.get(pid)
        if pd.isna(yv) or int(yv) not in roczniki:
            continue
        if _is_girl(nm.get(pid, "")):
            continue
        keep.append(pid)
    keep = set(keep)
    print(f"  bramkarze {sorted(roczniki)} (chłopcy): {len(keep)} zawodników")

    ss = s[s["player_id"].isin(keep)]
    ms = m[m["player_id"].isin(keep)]
    ss.to_csv(a.out_stats, index=False, encoding="utf-8")
    ms.to_csv(a.out_matches, index=False, encoding="utf-8")
    import os
    for f, df in [(a.out_stats, ss), (a.out_matches, ms)]:
        print(f"  zapisano {f}: {round(os.path.getsize(f)/1e6, 1)} MB | {len(df)} wierszy "
              f"| kolumn {df.shape[1]} (komplet)")
    print("Gotowe. To są pliki do repo. keeper_count zachowany, ranking = pełny (te same osoby).")


if __name__ == "__main__":
    main()