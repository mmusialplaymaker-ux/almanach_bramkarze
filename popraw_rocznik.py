#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
popraw_rocznik.py - naklada korekty rocznika na dane apki.

Bierze rocznik_status.csv (z wyznacz_rocznik.py) i dla zawodnikow ze statusem
KOREKTA podmienia est_birth_year w stats_test.csv i matches_test.csv na rocznik_final
(rocznik wyliczony z floora lig). Oryginal zachowuje w nowej kolumnie rocznik_z_daty.

Apka czyta est_birth_year i sama przelicza "gra ze starszymi" / talent, wiec po tej
podmianie rocznik jest juz poprawiony wszedzie (znaczniki, ranking, Excel) - bez
zmian w app.py.

Domyslnie poprawia TYLKO status=KOREKTA (pewne bugi +1/+2).
SPRAWDZ_RECZNIE (duze roznice) zostawia nietkniete - chyba ze dodasz --tez-sprawdz.

Uzycie:
  python popraw_rocznik.py
  python popraw_rocznik.py --status rocznik_status.csv --stats stats_test.csv --matches matches_test.csv
"""
import argparse
import os
import sys

import pandas as pd

ENCODINGS = ("utf-8", "utf-8-sig", "cp1250", "latin-1")


def rd(path):
    for e in ENCODINGS:
        try:
            return pd.read_csv(path, encoding=e, dtype=str, keep_default_na=False)
        except Exception:
            continue
    raise RuntimeError(f"Nie udalo sie wczytac {path}")


def patch(df, corr, orig, pew, wid, label):
    """Podmien est_birth_year wg mapy corr; dopisz rocznik_z_daty, rocznik_pewnosc, rocznik_widelki."""
    if "player_id" not in df.columns or "est_birth_year" not in df.columns:
        print(f"  {label}: brak player_id/est_birth_year - pomijam")
        return df, 0
    df = df.copy()
    df["player_id"] = df["player_id"].astype(str)
    df["rocznik_z_daty"] = df["player_id"].map(orig).fillna(df["est_birth_year"])
    mask = df["player_id"].isin(corr)
    df.loc[mask, "est_birth_year"] = df.loc[mask, "player_id"].map(corr)
    df["rocznik_pewnosc"] = df["player_id"].map(pew).fillna("")
    df["rocznik_widelki"] = df["player_id"].map(wid).fillna("")
    return df, int(mask.sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", default="rocznik_status.csv")
    ap.add_argument("--stats", default="stats_test.csv")
    ap.add_argument("--matches", default="matches_test.csv")
    ap.add_argument("--tez-sprawdz", dest="tez_sprawdz", action="store_true",
                    help="poprawiaj tez SPRAWDZ_RECZNIE (domyslnie tylko KOREKTA)")
    ap.add_argument("--reczne", default="reczne_korekty.csv",
                    help="opcjonalny CSV z recznymi korektami (player_id,rocznik) - MAJA PRIORYTET nad floorem")
    a = ap.parse_args()

    for f in (a.status, a.stats, a.matches):
        if not os.path.exists(f):
            print(f"BLAD: brak {f}")
            sys.exit(1)

    st = rd(a.status)
    if "status" not in st.columns:
        print(f"BLAD: {a.status} nie ma kolumny 'status'.")
        if {"season_id", "league_name", "matches"} & set(st.columns):
            print("  Ten plik wyglada na WYNIK rocznik_historia.sql (historia), nie na status.")
            print(f"  Najpierw policz status:  python wyznacz_rocznik.py --hist {a.status}")
        else:
            print("  Uruchom najpierw:  python wyznacz_rocznik.py")
        sys.exit(1)
    st["player_id"] = st["player_id"].astype(str)
    statuses = {"KOREKTA"} | ({"SPRAWDZ_RECZNIE"} if a.tez_sprawdz else set())
    do_fix = st[st["status"].isin(statuses)]
    corr = dict(zip(do_fix["player_id"], do_fix["rocznik_final"].astype(str)))
    orig = dict(zip(st["player_id"], st["rocznik_z_daty"].astype(str)))
    pew = dict(zip(st["player_id"], st["pewnosc"].astype(str))) if "pewnosc" in st.columns else {}
    wid = dict(zip(st["player_id"], st["widelki"].astype(str))) if "widelki" in st.columns else {}
    print(f"Korekty z floora ({', '.join(sorted(statuses))}): {len(corr)} zawodnikow")

    # RECZNE korekty (z feedbacku) - priorytet nad floorem; lapia tez "za mlodo",
    # ktorego z lig nie da sie wykryc.
    if os.path.exists(a.reczne):
        try:
            rk = rd(a.reczne)
        except Exception:
            rk = pd.read_csv(a.reczne, dtype=str, keep_default_na=False,
                             sep=None, engine="python", on_bad_lines="skip")
        ycol = next((c for c in ("rocznik", "rocznik_final", "est_birth_year", "rok")
                     if c in rk.columns), None)
        if "player_id" in rk.columns and ycol:
            man = dict(zip(rk["player_id"].astype(str), rk[ycol].astype(str)))
            man = {k: v for k, v in man.items() if str(v).strip()}
            corr.update(man)  # reczne wygrywaja
            for k, v in man.items():          # feedback = pewny
                pew[k] = "pewny (feedback)"
                wid[k] = str(v)
            print(f"Reczne korekty z {a.reczne}: {len(man)} (priorytet nad floorem)")
        else:
            print(f"UWAGA: {a.reczne} bez kolumn player_id + rocznik - pomijam.")

    if corr:
        przyklady = do_fix.head(6)[["zawodnik", "rocznik_z_daty", "rocznik_final"]]
        for _, r in przyklady.iterrows():
            print(f"  {r['zawodnik']}: {r['rocznik_z_daty']} -> {r['rocznik_final']}")

    s, ns = patch(rd(a.stats), corr, orig, pew, wid, "stats")
    m, nm = patch(rd(a.matches), corr, orig, pew, wid, "matches")
    try:
        s.to_csv(a.stats, index=False, encoding="utf-8")
        m.to_csv(a.matches, index=False, encoding="utf-8")
    except PermissionError as e:
        f = getattr(e, "filename", "plik")
        print(f"\nBLAD: nie moge zapisac {f} - jest OTWARTY w Excelu/LibreOffice.")
        print("Zamknij stats_test.csv i matches_test.csv i uruchom ponownie.")
        sys.exit(1)
    print(f"Poprawiono wierszy: stats {ns}, matches {nm}")
    print(f"Zapisano: {a.stats}, {a.matches} (est_birth_year skorygowane; oryginal w rocznik_z_daty)")


if __name__ == "__main__":
    main()