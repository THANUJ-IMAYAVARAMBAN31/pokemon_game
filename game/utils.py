from pathlib import Path

import pandas as pd

_BASE = Path(__file__).resolve().parent
df = pd.read_csv(_BASE / "data.csv", encoding="utf-8-sig")
df.columns = df.columns.str.strip().str.lower()
# Level must come only from the Level column — never use Pokédex no. as level.
if "level" not in df.columns:
    df["level"] = pd.NA
else:
    df["level"] = pd.to_numeric(df["level"], errors="coerce")


def _parse_level_number(val):
    """Coerce level to float for comparisons; None if missing or invalid."""
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    if isinstance(val, str) and not str(val).strip():
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _get_field(obj, key):
    """Case-insensitive dict field access (handles old session keys like 'Level')."""
    if not obj:
        return None
    if key in obj:
        return obj.get(key)
    lower_map = {str(k).lower(): v for k, v in obj.items()}
    return lower_map.get(key.lower())


def _level_from_name(name):
    """Read numeric level from the dataframe by Pokémon name."""
    if not name:
        return None
    mask = df["name"].astype(str).str.strip().str.lower() == str(name).strip().lower()
    if not mask.any() or "level" not in df.columns:
        return None
    return _parse_level_number(df.loc[mask].iloc[0]["level"])


def _level_from_no(no_value):
    """Read numeric level from the dataframe by Pokédex number."""
    if no_value is None or "no" not in df.columns or "level" not in df.columns:
        return None
    try:
        no_num = int(float(no_value))
    except (TypeError, ValueError):
        return None
    no_series = pd.to_numeric(df["no"], errors="coerce")
    subset = df[no_series == no_num]
    if subset.empty:
        return None
    return _parse_level_number(subset.iloc[0]["level"])


def _level_from_pokemon_dict(pokemon_dict):
    if not pokemon_dict:
        print("DEBUG: pokemon_dict is None")
        return None

    print("DEBUG: Checking level for:", pokemon_dict.get("name"))
    print("DEBUG DICT:", pokemon_dict)
    n = _parse_level_number(_get_field(pokemon_dict, "level"))
    print("DEBUG: Direct level:", n)

    if n is not None:
        return n

    n = _level_from_name(_get_field(pokemon_dict, "name"))
    print("DEBUG: From name:", n)

    if n is not None:
        return n

    n = _level_from_no(_get_field(pokemon_dict, "no"))
    print("DEBUG: From no:", n)

    return n

def _enrich_level_in_dict(out):
    """Ensure `out['level']` is set from the dataset when missing (e.g. stale session)."""
    if not out:
        return out
    if _parse_level_number(_get_field(out, "level")) is not None:
        return out
    n = _level_from_name(_get_field(out, "name"))
    if n is None:
        n = _level_from_no(_get_field(out, "no"))
    if n is None:
        return out
    out["level"] = int(n) if abs(n - int(n)) < 1e-6 else n
    return out


def pokemon_row_to_session_dict(row):
    out = {}
    for col in row.index:
        v = row[col]
        if pd.isna(v):
            out[col] = None
            continue
        if hasattr(v, "item"):
            v = v.item()
        if col == "level":
            try:
                fv = float(v)
                v = int(fv) if fv == int(fv) else fv
            except (TypeError, ValueError):
                pass
        elif col == "no":
            try:
                v = int(float(v))
            except (TypeError, ValueError):
                pass
        out[col] = v
    _enrich_level_in_dict(out)
    return out


def get_random_pokemon(filter_type):
    if filter_type == "only_type1":
        df_filtered = df[df["type2"].isna()]
    else:
        df_filtered = df
    return df_filtered.sample(1).iloc[0]


def get_hints(pokemon, attempts, single_type_pool=False):
    """
    Hints after wrong guesses.
    - Normal pool: after 3rd wrong → Type 2; after 4th → Color.
    - Single-type-only customization: no Type 2 hint; after 3rd → Level; after 4th → Color.
    """
    hints = {}
    hints["Type 1"] = _get_field(pokemon, "type1") or "—"
    if single_type_pool:
        if attempts >= 3:
            lv = _get_field(pokemon, "level")
            hints["Level"] = "—" if lv is None else str(lv)
        if attempts >= 4:
            hints["Color"] = _get_field(pokemon, "color") or "—"
    else:
        if attempts >= 3:
            t2 = _get_field(pokemon, "type2")
            hints["Type 2"] = t2 if t2 else "—"
        if attempts >= 4:
            hints["Color"] = _get_field(pokemon, "color") or "—"
    return hints


def get_all_pokemon_names():
    """Sorted names for autocomplete (prefix search on the client)."""
    return sorted(df["name"].astype(str).unique().tolist(), key=str.casefold)


def lookup_pokemon_by_name(raw_name):
    if not raw_name or not str(raw_name).strip():
        return None
    key = str(raw_name).strip().lower()
    subset = df[df["name"].str.lower() == key]
    if subset.empty:
        return None
    return pokemon_row_to_session_dict(subset.iloc[0])


def canonical_pokemon_from_session(session_pokemon):
    """
    Rebuild Pokémon dict from the dataframe row by name or Pokédex no.
    Fixes missing level, mixed-case session keys (Name vs name), and stale sessions.
    """
    if not session_pokemon:
        return session_pokemon
    name = _get_field(session_pokemon, "name")
    no_val = _get_field(session_pokemon, "no")
    mask = None
    if name:
        mask = df["name"].astype(str).str.strip().str.lower() == str(name).strip().lower()
    if mask is None or not mask.any():
        if no_val is not None and "no" in df.columns:
            try:
                n = int(float(no_val))
            except (TypeError, ValueError):
                n = None
            if n is not None:
                no_series = pd.to_numeric(df["no"], errors="coerce")
                mask = no_series == n
    if mask is None or not mask.any():
        _enrich_level_in_dict(session_pokemon)
        return session_pokemon
    row = df.loc[mask].iloc[0]
    return pokemon_row_to_session_dict(row)


def sync_pokemon_from_csv(session_pokemon):
    """Alias: full canonical merge from CSV (do not rely on .get('name') only)."""
    return canonical_pokemon_from_session(session_pokemon)


def _fmt_type2(val):
    if val is None:
        return "—"
    if isinstance(val, float) and pd.isna(val):
        return "—"
    s = str(val).strip()
    return s if s else "—"


def _norm_type2_key(val):
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    s = str(val).strip()
    return s.lower() if s else None


def _cmp_float(g, t, low_msg, high_msg, same_msg):
    """Safe numeric comparison with None handling."""
    if g is None or t is None:
        return "mismatch", "Level data not available."

    try:
        g = float(g)
        t = float(t)
    except (TypeError, ValueError):
        return "mismatch", "Invalid numeric values."

    eps = 1e-4
    if abs(g - t) < eps:
        return "same", same_msg
    elif t > g:
        return "higher", high_msg
    else:
        return "lower", low_msg

def _fmt_num(val, suffix):
    if val is None:
        return "—"
    try:
        return f"{float(val):g} {suffix}".strip()
    except (TypeError, ValueError):
        return "—"


def _fmt_level(val):
    if val is None:
        return "—"
    try:
        f = float(val)
        return str(int(f)) if f == int(f) else str(f)
    except (TypeError, ValueError):
        return str(val)


def _fmt_level_display(pokemon_dict):
    n = _level_from_pokemon_dict(pokemon_dict)
    if n is None:
        return "—"
    return str(int(n)) if abs(n - int(n)) < 1e-6 else str(n)


def build_comparison_rows(guess_dict, target_dict):
    """
    Attribute-wise feedback for an incorrect guess. Does not reveal the target Pokémon's name.
    Returns (rows, error_message). error_message is set when guess_dict is None.
    """
    if guess_dict is None:
        return [], "This Pokémon is not in the dataset."

    rows = []

    def append_row(label, guess_display, verdict, message):
        rows.append(
            {
                "label": label,
                "guess_display": guess_display,
                "verdict": verdict,
                "message": message,
            }
        )

    g1 = (_get_field(guess_dict, "type1") or "").strip()
    t1 = (_get_field(target_dict, "type1") or "").strip()
    t1_ok = g1.lower() == t1.lower() if g1 or t1 else not g1 and not t1
    append_row(
        "Type 1",
        g1 or "—",
        "match" if t1_ok else "mismatch",
        "Matches the target's first type." if t1_ok else "Does not match the target's first type.",
    )

    gt2 = _norm_type2_key(_get_field(guess_dict, "type2"))
    tt2 = _norm_type2_key(_get_field(target_dict, "type2"))
    t2_ok = gt2 == tt2
    append_row(
        "Type 2",
        _fmt_type2(_get_field(guess_dict, "type2")),
        "match" if t2_ok else "mismatch",
        "Matches the target's second type (or both have none)."
        if t2_ok
        else "Does not match the target's second-type slot.",
    )

    gh, th = _get_field(guess_dict, "height"), _get_field(target_dict, "height")
    verdict, msg = _cmp_float(
        gh,
        th,
        "Target is shorter than your guess.",
        "Target is taller than your guess.",
        "Same height as the target.",
    )
    append_row("Height", _fmt_num(gh, "m"), verdict, msg)

    gw, tw = _get_field(guess_dict, "weight"), _get_field(target_dict, "weight")
    verdict_w, msg_w = _cmp_float(
        gw,
        tw,
        "Target is lighter than your guess.",
        "Target is heavier than your guess.",
        "Same weight as the target.",
    )
    append_row("Weight", _fmt_num(gw, "kg"), verdict_w, msg_w)

    gl = _level_from_pokemon_dict(guess_dict)
    tl = _level_from_pokemon_dict(target_dict)
    verdict_l, msg_l = _cmp_float(
        gl,
        tl,
        "Target has a lower level than your guess.",
        "Target has a higher level than your guess.",
        "Same level as the target.",
    )
    append_row("Level", _fmt_level_display(guess_dict), verdict_l, msg_l)

    g_leg = int(_get_field(guess_dict, "legendary") or 0)
    t_leg = int(_get_field(target_dict, "legendary") or 0)
    leg_ok = g_leg == t_leg
    append_row(
        "Legendary",
        "Yes" if g_leg else "No",
        "match" if leg_ok else "mismatch",
        "Same legendary status as the target." if leg_ok else "Different legendary status than the target.",
    )

    gc = (_get_field(guess_dict, "color") or "").strip()
    tc = (_get_field(target_dict, "color") or "").strip()
    col_ok = gc.lower() == tc.lower() if gc or tc else not gc and not tc
    append_row(
        "Color",
        gc or "—",
        "match" if col_ok else "mismatch",
        "Matches the target's color category." if col_ok else "Different color category than the target.",
    )

    return rows, None


def check_guess(user_guess, pokemon, attempts, single_type_pool=False):
    hints = get_hints(pokemon, attempts, single_type_pool)
    name = (_get_field(pokemon, "name") or "").strip()
    guess = (user_guess or "").strip()
    is_correct = guess.lower() == name.lower()
    return is_correct, hints
