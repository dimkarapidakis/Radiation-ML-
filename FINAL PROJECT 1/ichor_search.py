"""
ichor_search.py - SYMPTOM SEARCH tab for Project ICHOR.

The astronaut types what they feel in plain English. The algorithm
  1. understands the text (synonyms, small typos, negations like "no nausea", severity words),
  2. ranks the most likely conditions (NASA Medical Kit 3.001 mapping from ichor_symptoms.py),
  3. lists the medications from the kit with location, dose strength, rules, side effects,
     authorization level (crew use / flight-surgeon authorization) and conflicts with what is already taken,
  4. adds caution notes from the astronaut's latest vitals in the database (SpO2, BP, heart rate, temperature),
  5. can save the detected symptoms into the `symptoms` table, so the 3D organ model reacts to them.

EDUCATIONAL DECISION SUPPORT. NOT A DIAGNOSIS. NOT FOR REAL MEDICAL USE.
The symptom -> condition map is team-built; the kit contents are from the real NASA document named in ichor_symptoms.py.
"""
from __future__ import annotations

import difflib
import html
import re

from ichor_symptoms import ALL_SYMPTOMS, CONDITIONS, MEDS, RED_FLAGS, conflicts, diagnose, render_symptom_panel

# ----------------------------------------------------------------------------------------------------------------
#  Vocabulary: everyday phrase -> canonical symptom used by ichor_symptoms.CONDITIONS / RED_FLAGS
# ----------------------------------------------------------------------------------------------------------------
_SYN = {
    "headache": ["headache", "head hurts", "head ache", "migraine", "head pain", "pounding head", "throbbing head", "head is pounding"],
    "nausea": ["nausea", "nauseous", "queasy", "feel sick", "sick to my stomach", "motion sick", "space sick", "feel like throwing up"],
    "vomiting": ["vomiting", "vomit", "vomited", "throwing up", "threw up", "puking", "puke", "been sick"],
    "dizziness": ["dizziness", "dizzy", "lightheaded", "light headed", "light-headed", "vertigo", "woozy", "room is spinning", "spinning", "feel faint"],
    "disorientation": ["disoriented", "disorientation", "lost my bearings", "spatial disorientation", "dont know which way is up"],
    "fatigue": ["fatigue", "tired", "exhausted", "exhaustion", "no energy", "worn out", "drained", "lethargic", "sleepy", "wiped out"],
    "insomnia": ["insomnia", "cant sleep", "cannot sleep", "trouble sleeping", "trouble falling asleep", "sleepless", "unable to sleep", "wake up at night", "waking up at night"],
    "poor sleep": ["poor sleep", "slept badly", "slept poorly", "bad sleep", "restless sleep", "not sleeping well", "sleep disturbance", "broken sleep"],
    "diarrhea": ["diarrhea", "diarrhoea", "loose stool", "loose stools", "watery stool", "the runs"],
    "constipation": ["constipation", "constipated", "cant poop", "hard stool", "not pooping"],
    "abdominal cramps": ["abdominal cramps", "stomach cramps", "stomach ache", "stomach pain", "tummy ache", "belly pain", "abdominal pain", "cramps"],
    "bloating": ["bloating", "bloated", "gassy", "distended", "gas pain"],
    "heartburn": ["heartburn", "acid reflux", "reflux", "indigestion", "sour taste"],
    "congestion": ["congestion", "congested", "stuffy nose", "blocked nose", "stuffed up", "nasal congestion", "sinus pressure"],
    "runny nose": ["runny nose", "nose running", "sniffles", "rhinorrhea"],
    "sneezing": ["sneezing", "sneeze", "sneezes"],
    "itchy eyes": ["itchy eyes", "itchy eye", "eyes itch", "eyes are itchy", "watery eyes"],
    "red eye": ["red eye", "red eyes", "bloodshot", "pink eye"],
    "eye discharge": ["eye discharge", "crusty eyes", "eye gunk", "goopy eye"],
    "eye pain": ["eye pain", "eye hurts", "pain in my eye", "sore eye"],
    "light sensitivity": ["light sensitivity", "sensitive to light", "photophobia", "light hurts"],
    "blurred vision": ["blurred vision", "blurry vision", "vision is blurry", "vision changed", "cant focus my eyes", "near vision worse", "double vision"],
    "facial pain": ["facial pain", "face hurts", "sinus pain", "pain in my face", "cheek pain"],
    "back pain": ["back pain", "back hurts", "backache", "sore back", "lower back", "spine pain"],
    "muscle pain": ["muscle pain", "muscle ache", "muscle aches", "sore muscles", "myalgia", "muscles hurt", "body aches", "body ache", "aching muscles"],
    "joint pain": ["joint pain", "joints hurt", "sore joints", "knee pain", "shoulder pain", "elbow pain", "wrist pain"],
    "swelling": ["swelling", "swollen"],
    "painful urination": ["painful urination", "burning when i pee", "burning urination", "hurts to pee", "hurts to urinate", "burns when i urinate", "dysuria"],
    "frequent urination": ["frequent urination", "peeing a lot", "urinating often", "keep needing to pee"],
    "urgency": ["urgency", "urgent need to pee", "sudden urge to urinate"],
    "rash": ["rash", "hives", "skin rash", "red spots", "bumps on skin"],
    "itching": ["itching", "itchy skin", "itchy", "itch"],
    "skin redness": ["skin redness", "red skin", "redness", "red patch", "skin is red"],
    "ear pain": ["ear pain", "earache", "ear ache", "ear hurts", "pain in my ear"],
    "ear fullness": ["ear fullness", "ear blocked", "blocked ear", "clogged ear", "ears feel full", "ear pressure", "ear popping"],
    "hearing loss": ["hearing loss", "cant hear", "hard to hear", "muffled hearing"],
    "anxiety": ["anxiety", "anxious", "nervous", "panic", "panicky", "stressed", "stress", "worried", "on edge"],
    "restlessness": ["restlessness", "restless", "agitated", "cant relax", "jittery"],
    "shortness of breath": ["shortness of breath", "short of breath", "breathless", "out of breath", "hard to catch my breath"],
    "fever": ["fever", "feverish", "high temperature", "chills", "feel hot"],
    "cough": ["cough", "coughing", "dry cough", "hacking cough"],
    "sore throat": ["sore throat", "throat hurts", "scratchy throat", "painful swallowing", "hoarse"],
    "thirst": ["thirsty", "thirst", "dry mouth"],
    "dark urine": ["dark urine", "dark pee", "dark yellow urine"],
    "palpitations": ["palpitations", "heart racing", "racing heart", "heart pounding", "fast heartbeat", "heart skipping", "heart fluttering", "irregular heartbeat"],
    # ---- red flags (skip the medication list, go straight to emergency escalation) ----
    "chest pain": ["chest pain", "chest hurts", "pain in my chest", "chest pressure", "chest tightness", "tight chest", "crushing chest"],
    "difficulty breathing": ["difficulty breathing", "trouble breathing", "cant breathe", "cannot breathe", "struggling to breathe", "gasping", "choking"],
    "loss of consciousness": ["passed out", "fainted", "blacked out", "lost consciousness", "unconscious", "unresponsive"],
    "severe allergic reaction": ["anaphylaxis", "throat swelling", "tongue swelling", "swollen tongue", "swollen lips", "swollen throat", "severe allergic reaction"],
    "bloody stool": ["blood in stool", "blood in my stool", "bloody stool", "black stool", "tarry stool"],
    "seizure": ["seizure", "convulsion", "convulsing"],
    "sudden vision loss": ["sudden vision loss", "lost vision", "cant see", "went blind", "sudden blindness"],
    "confusion": ["confused", "confusion", "incoherent", "cant think straight"],
}
EXTRA_RED = {"sudden severe headache"}          # produced by the severity rules below
SEVERE_WORDS = {"severe", "unbearable", "excruciating", "worst", "terrible", "intense", "extreme", "sudden"}
NEGATORS = r"(?:no|not|without|never|dont have|do not have|havent|hasnt|free of|denies|isnt|arent|no longer)"

# phrase -> canonical, longest phrases first so "short of breath" wins over "breath"
_PHRASES = sorted(((p, c) for c, ps in _SYN.items() for p in ps), key=lambda t: -len(t[0]))
_PHRASE_LIST = [p for p, _ in _PHRASES]
_PHRASE_TO_CANON = dict(_PHRASES)


def _norm(text: str) -> str:
    t = text.lower().replace("’", "'").replace("'", "")
    t = re.sub(r"[.,;:!?\n]", " | ", t)                 # sentence / list boundary: negation never crosses it
    t = re.sub(r"[^a-z0-9\s\-|]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _negated(text: str, start: int) -> bool:
    before = text[max(0, start - 32):start]
    before = re.split(r"\b(?:but|however|although|though|except|and now|yet)\b|\|", before)[-1]      # a conjunction ends the negation
    b = " " + before
    return (re.search(r"\b" + NEGATORS + r"\b(?:\s+[a-z0-9\-]+){0,2}\s*$", b) is not None            # negator within 2 words
            or re.search(r"\b" + NEGATORS + r"\b(?:\s+[a-z0-9\-]+){0,4}\s+(?:or|nor)\s*$", b) is not None)   # "no X or <symptom>"


def _severe_near(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 28):end + 14]
    return any(re.search(r"\b" + w + r"\b", window) for w in SEVERE_WORDS)


def parse_symptoms(raw: str) -> dict:
    """Free text -> {'symptoms': set, 'red_flags': set, 'negated': set, 'severe': set, 'fuzzy': {typed: canonical}, 'unknown': bool}"""
    text = " " + _norm(raw) + " "
    found, negated, severe, fuzzy = set(), set(), set(), {}
    work = text

    def take(span_text: str, start: int, end: int, canon: str, how: str | None = None, typed: str = ""):
        nonlocal work
        if _negated(text, start):
            negated.add(canon)
        else:
            found.add(canon)
            if _severe_near(text, start, end):
                severe.add(canon)
            if how == "fuzzy":
                fuzzy[typed] = canon
        work = work[:start] + " " * (end - start) + work[end:]

    # 1) exact phrases (word boundaries), longest first
    for phrase, canon in _PHRASES:
        for m in re.finditer(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", work):
            take(phrase, m.start(), m.end(), canon)

    # 2) typo tolerance on what is left (1-3 word n-grams against the phrase list)
    tokens = [(m.group(), m.start(), m.end()) for m in re.finditer(r"[a-z0-9\-]+", work)]
    for n in (3, 2, 1):
        i = 0
        while i + n <= len(tokens):
            grp = tokens[i:i + n]
            gram = " ".join(t[0] for t in grp)
            if len(gram) >= 6 and work[grp[0][1]:grp[-1][2]].strip():
                hit = difflib.get_close_matches(gram, _PHRASE_LIST, n=1, cutoff=0.84)
                if hit and abs(len(hit[0]) - len(gram)) <= 3 and work[grp[0][1]:grp[-1][2]].strip() == gram:
                    take(gram, grp[0][1], grp[-1][2], _PHRASE_TO_CANON[hit[0]], "fuzzy", gram)
                    tokens = [(m.group(), m.start(), m.end()) for m in re.finditer(r"[a-z0-9\-]+", work)]
                    continue
            i += 1

    # 3) severity rules that create extra red flags
    if "abdominal cramps" in severe:
        found.add("severe abdominal pain")
    if "headache" in severe and re.search(r"\b(worst|sudden|thunderclap)\b", text):
        found.add("sudden severe headache")
    if "chest pain" in found and "heartburn" in found:
        found.discard("heartburn")                              # chest pain is NOT heartburn until a doctor says so

    red = {s for s in found if s in RED_FLAGS or s in EXTRA_RED}
    return {"symptoms": found - red, "red_flags": red, "negated": negated, "severe": severe,
            "fuzzy": fuzzy, "unknown": not found}


# ----------------------------------------------------------------------------------------------------------------
#  Context from the real database (latest vitals of the selected astronaut)
# ----------------------------------------------------------------------------------------------------------------
BP_SENSITIVE = {"pseudoephedrine", "caffeine", "prednisone", "ketorolac"}


def vitals_context(latest: dict) -> tuple[list[tuple[str, str]], dict]:
    """Return (notes, flags). notes = [(level, text)], flags = booleans used for medication cautions."""
    notes, flags = [], {"high_bp": False}
    g = lambda k: latest[k]["value"] if k in latest else None
    spo2, hr, sbp, dbp, temp = g("oxygen_saturation"), g("heart_rate"), g("systolic_bp"), g("diastolic_bp"), g("body_temperature")
    if spo2 is not None and spo2 < 95:
        notes.append(("warn", f"SpO₂ is {spo2:g}% (below 95%). Check cabin O₂/CO₂ and rule out hypoxia before treating symptoms."))
    if hr is not None and (hr > 100 or hr < 50):
        notes.append(("warn", f"Latest heart rate is {hr:g} bpm (resting range 60-100). Repeat the measurement."))
    if (sbp is not None and sbp >= 130) or (dbp is not None and dbp >= 80):
        flags["high_bp"] = True
        notes.append(("warn", f"Latest blood pressure is {sbp:g}/{dbp:g} mmHg. Decongestants, caffeine, prednisone and ketorolac can raise it: caution."
                      if sbp is not None and dbp is not None else "Latest blood pressure is elevated: caution with BP-raising drugs."))
    if temp is not None and temp >= 38.0:
        notes.append(("warn", f"Body temperature is {temp:g} °C: fever. Record it again and report to the flight surgeon."))
    return notes, flags


def analyze_text(raw: str, taking: list[str] | None = None, latest: dict | None = None) -> dict:
    """Pure function (no Streamlit): used by the UI and by the tests."""
    parsed = parse_symptoms(raw)
    taking = taking or []
    ctx_notes, ctx_flags = vitals_context(latest or {})
    results = []
    if not parsed["red_flags"] and parsed["symptoms"]:
        for c in diagnose(parsed["symptoms"]):
            meds = []
            for mid in c["meds"]:
                m = MEDS[mid]
                bad = conflicts(mid, taking)
                caution = "BP-raising drug and the latest BP is high" if (ctx_flags["high_bp"] and mid in BP_SENSITIVE) else None
                meds.append({"id": mid, "med": m, "blocked": bad, "caution": caution})
            results.append({**c, "meds_info": meds})
    return {"parsed": parsed, "conditions": results, "context": ctx_notes}


# ----------------------------------------------------------------------------------------------------------------
#  UI (HUD style shared with main.py)
# ----------------------------------------------------------------------------------------------------------------
EXAMPLES = [
    "I have a pounding headache and feel dizzy and nauseous since this morning",
    "cant sleep, very tired, a bit anxious",
    "stuffy nose, sneezing and itchy eyes",
]


def _H(markup: str):
    import streamlit as st
    st.markdown(" ".join(line.strip() for line in markup.splitlines()), unsafe_allow_html=True)


def _set_example(text: str):
    import streamlit as st
    st.session_state["sx_text"] = text


def _save_symptoms(conn, astronaut_id: int, names: list[str], severity: int, note: str):
    import ichor_radiation as ir
    ir.add_symptoms(conn, astronaut_id, [n.title() for n in names], severity, note)


def render_search_panel(astronaut_label: str, real_astro: dict | None = None) -> None:
    import streamlit as st

    _H("""<div class="p-title">◉ SYMPTOM SEARCH · DESCRIBE WHAT YOU FEEL IN YOUR OWN WORDS</div>""")
    st.caption("Educational decision support built on the NASA Medical Kit 3.001 list. Not a diagnosis. "
               "Drugs marked “surgeon authorization” need the flight surgeon's approval.")

    # ---- latest vitals of the real astronaut (optional context)
    latest, conn = {}, None
    if real_astro:
        try:
            import ichor_3d_panel as p3
            import ichor_health as ih
            import ichor_radiation as ir
            conn = p3._conn(ir.DB_PATH)
            latest = ih.latest_values(conn, real_astro["id"])
        except Exception:
            conn, latest = None, {}

    st.session_state.setdefault("sx_text", "")
    st.session_state.setdefault("sx_query", "")
    with st.form("sx_form", clear_on_submit=False):
        st.text_area("Symptoms", key="sx_text", height=110, label_visibility="collapsed",
                     placeholder="e.g. “I have a headache, feel dizzy and a bit nauseous since this morning”")
        c1, c2 = st.columns([3, 1])
        with c1:
            taking = st.multiselect("Already taking (checks conflicts)", sorted(MEDS), format_func=lambda k: MEDS[k]["name"], key="sx_taking_free")
        with c2:
            severity = st.slider("Severity (for the record)", 1, 5, 2, key="sx_sev")
        go_btn = st.form_submit_button("🔎 ANALYZE SYMPTOMS")
    if go_btn:
        st.session_state["sx_query"] = st.session_state["sx_text"]

    st.caption("Try an example:")
    ec = st.columns(len(EXAMPLES))
    for i, ex in enumerate(EXAMPLES):
        ec[i].button(ex[:34] + ("…" if len(ex) > 34 else ""), key=f"sx_ex_{i}", on_click=_set_example, args=(ex,))

    query = st.session_state["sx_query"].strip()
    if not query:
        _H("""<div class="hud"><div class="chat-lock">Waiting for input. Type your symptoms above and press ANALYZE.
             The search understands everyday words (“throwing up”, “can't sleep”), small typos and negations (“no nausea”).</div></div>""")
        _render_checklist(st)
        return

    res = analyze_text(query, taking, latest)
    p = res["parsed"]

    # ---- what was understood
    chips = "".join(f'<span class="chip {"amber" if s in p["severe"] else ""}">{html.escape(s.upper())}</span>' for s in sorted(p["symptoms"]))
    chips += "".join(f'<span class="chip red">🚨 {html.escape(s.upper())}</span>' for s in sorted(p["red_flags"]))
    neg = "".join(f'<span class="chip" style="opacity:.55;text-decoration:line-through">{html.escape(s.upper())}</span>' for s in sorted(p["negated"]))
    fz = "".join(f"<div class='chat-lock'>“{html.escape(k)}” read as {html.escape(v)}</div>" for k, v in p["fuzzy"].items())
    _H(f"""<div class="hud"><div class="p-title">◉ UNDERSTOOD SYMPTOMS</div>
          {chips or '<span class="chat-lock">nothing recognised</span>'}
          {('<div class="chat-lock" style="margin-top:6px">Ruled out by you:</div>' + neg) if neg else ''}{fz}</div>""")

    if p["unknown"]:
        st.warning("I could not recognise any symptom. Try simple words such as headache, nausea, dizziness, fatigue, cough, rash, "
                   "back pain, diarrhea, can't sleep. If something feels seriously wrong, contact the flight surgeon.")
        _render_checklist(st)
        return

    # ---- red flags: no medication list
    if p["red_flags"]:
        _H(f"""<div class="banner bad">🚨 RED FLAG: {html.escape(', '.join(sorted(p['red_flags'])).upper())}<br>
              <small>Contact the flight surgeon NOW and use the Emergency Medical Treatment Pack (red). No self-medication list is shown.</small></div>""")
        _render_save(st, conn, real_astro, p, query, severity)
        return

    # ---- context from the database
    for lvl, txt in res["context"]:
        _H(f"""<div class="banner {'bad' if lvl == 'crit' else 'ok'}" style="border-color:#ffb300;color:#ffd98a;background:rgba(255,179,0,.08);animation:none">⚠ {html.escape(txt)}</div>""")

    if not res["conditions"]:
        st.info("The recognised symptoms do not match any condition in the kit mapping. Describe more details or contact the flight surgeon.")
    for c in res["conditions"]:
        pct = c["score"] * 100
        _H(f"""<div class="hud"><div class="p-title">◉ POSSIBLE CONDITION</div>
              <div style="font-family:Orbitron;font-size:1.05rem;color:#eafff1">{html.escape(c['name'])}</div>
              <div class="chat-lock">match score {pct:.0f}% (heuristic) · matched: {html.escape(', '.join(sorted(c['hit'])))}</div>
              <div class="matchbar"><div style="width:{min(pct, 100):.0f}%"></div></div>
              <div style="font-size:1.02rem">{html.escape(c['advice'])}</div></div>""")
        if not c["meds_info"]:
            st.caption("No kit medication is suggested for this condition.")
        for mi in c["meds_info"]:
            m = mi["med"]
            tag = "🟢 crew use" if m["auth"] == "crew" else "🟠 surgeon authorization"
            if mi["blocked"]:
                st.warning(f"⛔ {m['name']}: blocked ({mi['blocked']}).")
                continue
            warn = f"  ⚠ caution: {mi['caution']}" if mi["caution"] else ""
            with st.expander(f"💊 {m['name']} · {m['strength']} · {m['route']} · {tag}{'  ⚠' if mi['caution'] else ''}"):
                st.markdown(f"**Kit location:** {m['loc']}  ·  **Qty:** {m['qty']}  \n"
                            f"**Rules:** {m['comment'] or '-'}  \n**Side effects:** {m['se']}" + (f"  \n**{warn.strip()}**" if warn else ""))
    _render_save(st, conn, real_astro, p, query, severity)
    _render_checklist(st)


def _render_save(st, conn, real_astro, parsed, query, severity):
    names = sorted(parsed["symptoms"] | parsed["red_flags"])
    if not names:
        return
    if conn is not None and real_astro:
        if st.button(f"💾 Save {len(names)} symptom(s) to the medical record of {real_astro['name']}", key="sx_save"):
            _save_symptoms(conn, real_astro["id"], names, severity, f"Symptom search: {query}")
            st.toast("Saved. The 3D organ model will use these symptoms.", icon="💾")
    else:
        st.caption("Select a database astronaut in the sidebar to save these symptoms to the medical record.")


def _render_checklist(st):
    with st.expander("Prefer a checklist? Manual symptom picker"):
        render_symptom_panel()