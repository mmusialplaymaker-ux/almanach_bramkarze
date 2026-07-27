#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wyznacz_rocznik.py (v2) - wyznacza PRZEDZIAL rocznika zawodnika.
SAMODZIELNY (nie wymaga app.py).

ZMIANA v2 vs v1: zamiast jednej wartosci "rocznik_final" zwracamy PRZEDZIAL
[rocznik_od, rocznik_do] + punktowa estymate + uczciwa etykiete pewnosci.

Podstawa: blad estymacji jest JEDNOKIERUNKOWY. Zrodlo podaje WIEK, ingest cofa
date o tyle lat od dnia pobrania. Jesli urodziny juz minely -> rocznik poprawny.
Jesli nie minely -> rocznik o 1 ZA MLODY. Nigdy za stary.
Potwierdzone: 98.6% meczow mlodziezowych ma rocznik zgodny z regulaminem.
    => prawda ∈ {rocznik_z_daty - 1, rocznik_z_daty}

Drugie ograniczenie, z regulaminu: w lidze o graniczniku Y nie zagra nikt starszy
niz Y, wiec grajac w niej => rocznik >= Y. MAX(Y) po ligach i sezonach = floor.
    => prawda >= floor

Przeciecie obu daje status:
    data == floor    -> prawda = {floor}          -> PEWNY (jeden punkt)
    data == floor+1  -> prawda = {floor, floor+1} -> ZAWEZONY (remis 2-opcyjny)
    data >  floor+1  -> prawda = {data-1, data}   -> NIEPEWNY (floor nie pomaga)
    data <  floor    -> sprzecznosc               -> BLEDNY (rekord do zgloszenia)
    brak floora      -> prawda = {data-1, data}   -> NIEPEWNY

PEWNY wymaga, by zawodnik zagral SWOJA kategorie choc raz w 5 sezonach. Kto nigdy
nie gra wlasnej kategorii (flaga zawsze_w_gore) - nie da sie potwierdzic.

Dla ZAWEZONEGO wybieramy floor (jak v1). Uzasadnienie bayesowskie:
    prawda = floor    <=> data zla (~25%) I gra wlasna kategorie (~80%) ~ 0.20
    prawda = floor+1  <=> data dobra (~75%) I gra rocznik w gore (~20%) ~ 0.15
czyli ok. 57:43 na korzysc floora. Wybor dobry, ale to nie jest pewnik - i wlasnie
dlatego dostaje osobna etykiete, a nie "skorygowany" w jednym worku z BLEDNYM.

Idea: w danej lidze (sezonie) nie zagra nikt starszy niz rocznik graniczny Y.
Wiec grajac w lidze o graniczniku Y => rocznik >= Y. Bierzemy MAX(Y) po wszystkich
ligach i sezonach zawodnika = "rocznik_z_lig" (floor). To nie da sie oszukac polem
"wiek", wiec lapie bug (2011 pokazany jako 2010): jesli data mowi STARSZY niz
pozwalaja ligi (rocznik_z_daty < floor) -> sprzecznosc -> korekta w gore do floora.

Przesuniecie sezonowe: granicznik przesuwa sie o rok co sezon
   Y(liga, sezon) = baza(liga) - (2026 - rok_konca_sezonu)

Wejscie: CSV z rocznik_historia.sql (player_id, firstname, lastname, est_birth_year,
         season_id, league_name, matches, minutes).
Wyjscie: rocznik_status.csv - 1 wiersz na zawodnika.

Uzycie:
  python wyznacz_rocznik.py --hist rocznik_historia.csv
  python wyznacz_rocznik.py --hist rocznik_historia.csv --min-mecze 2
"""
import argparse
import os
import re
import sys

import pandas as pd

ROK_BAZOWY = 2026  # sezon 25/26 = mapowanie "surowe"

# dywizja -> najstarszy dopuszczalny rocznik (sezon 25/26, wg regulaminu MZPN). CLJ U-1x wg numeru.
_CAT_MAXYEAR_PATS = [
    (r'(^A1$|U-?19)', 2007), (r'(^A2$|U-?18)', 2008),
    (r'(^B1$|U-?17)', 2009), (r'(^B2$|U-?16)', 2010),
    (r'(^C1$|U-?15)', 2011), (r'(^C2$|U-?14)', 2012),
    (r'(^D1$|U-?13)', 2013), (r'(^D2$|U-?12)', 2014),
    (r'(^E1$|U-?11)', 2015), (r'(^E2$|U-?10)', 2016),
    (r'(^F1$|U-?9)',  2017), (r'(^F2$|U-?8)',  2018),
]

# prefiks season_id -> rok konca sezonu
SEASON_END_YEAR = {
    "e9d66181": 2026,  # 25/26 (biezacy)
    "4be7b40c": 2025,  # 24/25
    "29d748c8": 2024,  # 23/24
    "b004c86c": 2023,  # 22/23
    "b682af6d": 2022,  # 21/22  <- 4 sezony wstecz (musi byc zgodne z rocznik_historia.sql)
}
ENCODINGS = ("utf-8", "cp1250", "latin-1")


def _cat_max_year(name):
    """Najstarszy dopuszczalny rocznik dla dywizji (25/26). Senior/nieznane -> None."""
    n = str(name)
    for pat, y in _CAT_MAXYEAR_PATS:
        if re.search(pat, n, re.I):
            return y
    return None


def rd(path):
    for e in ENCODINGS:
        try:
            return pd.read_csv(path, encoding=e, dtype=str, keep_default_na=False)
        except Exception:
            continue
    raise RuntimeError(f"Nie udalo sie wczytac {path}")


def _year_bound(league_name, season_id):
    """Rocznik graniczny ligi w danym sezonie (z przesunieciem), albo None."""
    base = _cat_max_year(league_name)
    if base is None:
        return None
    endy = SEASON_END_YEAR.get(str(season_id)[:8])
    if endy is None:
        return None
    return base - (ROK_BAZOWY - endy)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hist", default="rocznik_historia.csv", help="CSV z rocznik_historia.sql")
    ap.add_argument("--out", default="rocznik_status.csv")
    ap.add_argument("--min-mecze", dest="min_mecze", type=int, default=2,
                    help="min. meczow w lidze, by liczyla sie do floora (chroni przed 1 blednym wpisem)")
    a = ap.parse_args()

    if not os.path.exists(a.hist):
        print(f"BLAD: brak {a.hist}. Uruchom rocznik_historia.sql i zapisz wynik jako {a.hist}.")
        sys.exit(1)

    h = rd(a.hist)
    for c in ("matches", "minutes", "est_birth_year"):
        if c in h.columns:
            h[c] = pd.to_numeric(h[c], errors="coerce")
    h["_ybound"] = [_year_bound(ln, sid) for ln, sid in zip(h["league_name"], h["season_id"])]

    rows = []
    for pid, g in h.groupby("player_id"):
        nm = f"{g['firstname'].iloc[0]} {g['lastname'].iloc[0]}".strip()
        date_z = g["est_birth_year"].dropna()
        date_z = int(date_z.iloc[0]) if len(date_z) else None

        q = g[g["_ybound"].notna() & (g["matches"].fillna(0) >= a.min_mecze)]
        if len(q):
            i = q["_ybound"].astype(int).idxmax()
            floor = int(q.loc[i, "_ybound"])
            dowod = f"{q.loc[i, 'league_name']} ({str(q.loc[i,'season_id'])[:8]}, {int(q.loc[i,'matches'])} mecz.)"
        else:
            floor, dowod = None, ""

        # ── przeciecie dwoch ograniczen -> przedzial + status ──
        if floor is None and date_z is None:
            status, od, do, final = "brak", None, None, None
        elif floor is None:
            # brak historii ligowej -> tylko model estymacji
            status, od, do, final = "niepewny", date_z - 1, date_z, date_z
        elif date_z is None:
            # floor to tylko DOLNA granica, gornej brak
            status, od, do, final = "niepewny", floor, None, floor
        elif date_z < floor:
            # data mowi STARSZY niz ligi dopuszczaja -> model estymacji zlamany
            status, od, do, final = "bledny", floor, None, floor
        elif date_z == floor:
            # jedyny przypadek PEWNY: oba ograniczenia wskazuja ten sam punkt
            status, od, do, final = "pewny", floor, floor, floor
        elif date_z - floor == 1:
            # remis 2-opcyjny: data zla + wlasna kategoria  ALBO  data dobra + rok w gore
            status, od, do, final = "zawezony", floor, date_z, floor
        else:
            # gra 2+ rocznikow w gore; floor nie zaweza, zostaje samo +/-1 z estymacji
            status, od, do, final = "niepewny", date_z - 1, date_z, date_z

        roznica = (date_z - floor) if (floor is not None and date_z is not None) else None
        # niezmiennik: pewny <=> od == do
        if od is not None and do is not None and od == do:
            widelki = str(od)
        elif od is not None and do is not None:
            widelki = f"{od}-{do}"
        else:
            widelki = f"{od}+" if od is not None else ""
        # zawsze_w_gore: nigdy nie zagral ligi, ktorej granica == jego rocznik_final
        zawsze_w_gore = bool(final is not None and len(q)
                             and not (q["_ybound"].astype(int) == int(final)).any())
        rows.append({
            "player_id": pid, "zawodnik": nm,
            "rocznik_z_daty": date_z, "rocznik_z_lig": floor,
            "rocznik_od": od, "rocznik_do": do, "rocznik": final,
            "roznica_lat": roznica, "pewnosc": status, "widelki": widelki,
            "zawsze_w_gore": zawsze_w_gore, "dowod": dowod,
            # kompatybilnosc wstecz z v1 (istniejacy precompute.py czyta te kolumny):
            "rocznik_final": final,
            "status": {"pewny": "POTWIERDZONY", "zawezony": "KOREKTA", "bledny": "KOREKTA",
                       "niepewny": "SPRAWDZ", "brak": "BRAK_HISTORII"}.get(status, "SPRAWDZ"),
        })

    out = pd.DataFrame(rows).sort_values(["pewnosc", "roznica_lat", "zawodnik"],
                                         na_position="last")
    try:
        out.to_csv(a.out, index=False, encoding="utf-8-sig")
    except PermissionError:
        print(f"\nBLAD: nie moge zapisac {a.out} - plik jest OTWARTY w Excelu/LibreOffice.")
        print("Zamknij go i uruchom ponownie.")
        sys.exit(1)
    print(f"Zapisano {a.out}: {len(out)} zawodnikow\n")
    print("Rozklad pewnosci (pewny/reczny odblokowuja premie > 1.30 w PM Score):")
    OPIS = {
        "pewny":    "data == floor -> jeden punkt, potwierdzony liga",
        "zawezony": "data == floor+1 -> remis {floor, floor+1}, bierzemy floor",
        "niepewny": "floor nie zaweza (brak historii lub gra 2+ w gore) -> +/-1",
        "bledny":   "data starsza niz ligi dopuszczaja -> rekord do zgloszenia",
        "brak":     "brak danych",
    }
    n = len(out)
    for k, v in out["pewnosc"].value_counts().items():
        gate = "PELNA SKALA" if k == "pewny" else "cap 1.30"
        licznik = f"{v:,}".replace(",", " ")
        print(f"  {k:<10} {licznik:>9} ({v/n*100:>4.1f}%)  [{gate:<11}] {OPIS.get(k,'')}")
    pewnych = (out["pewnosc"] == "pewny").sum()
    print(f"\n  Pelna skala premii dostepna dla: {pewnych:,} / {n:,} ({pewnych/n*100:.1f}%)".replace(",", " ").replace("  (", " ("))
    zwg = out["zawsze_w_gore"].sum()
    print(f"  Nigdy nie grali wlasnej kategorii (zawsze_w_gore): {zwg:,} — floor ich nie potwierdzi".replace(",", " "))
    bled = (out["pewnosc"] == "bledny").sum()
    if bled:
        print(f"  Rekordy sprzeczne z regulaminem (do zgloszenia w zrodle): {bled:,}".replace(",", " "))
    # niezmiennik
    bad = out[(out["rocznik_od"].notna()) & (out["rocznik_do"].notna())
              & ((out["rocznik_do"] - out["rocznik_od"]) > 1)]
    if len(bad):
        print(f"\n  UWAGA: {len(bad)} zawodnikow ma przedzial szerszy niz 1 rocznik — to blad logiki!")


if __name__ == "__main__":
    main()