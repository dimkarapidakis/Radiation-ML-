"""
ICHOR symptom checker: decision support built on NASA Medical Kit 3.001 (MED CL/SpX-6, 09 APR 15).
Educational prototype. NOT a diagnosis and NOT for real medical use.
Kit contents = real document. Symptom->condition map = team-built; condition names follow the
NASA Integrated Medical Model / Exploration Medical Capability lists (verify against NTRS).
"""
import streamlit as st

# auth: "crew" = convenience pack (self-use within limits), "surgeon" = flight surgeon / CMO authorization
# (id, name, category, strength, route, qty, location, auth, comments, side effects)
_M = [
    ("loperamide", "Loperamide (Imodium)", "Antidiarrheal", "2 mg", "Oral", "40 tab", "Convenience B2", "crew", "Non-bloody diarrhea only. Max 8 tablets/24 h.", "Abdominal discomfort, nausea, constipation, drowsiness"),
    ("fexofenadine", "Fexofenadine (Allegra)", "Antihistamine", "180 mg", "Oral", "100 tab", "Convenience B2", "crew", "No other antihistamines. No grapefruit juice 1 h before / 2 h after.", "Headache, drowsiness, nausea, dizziness"),
    ("loratadine", "Loratadine (Claritin)", "Antihistamine", "10 mg", "Oral", "375 tab", "Convenience A2", "crew", "No other antihistamines.", "Headache, drowsiness, dry mouth"),
    ("olopatadine", "Olopatadine (Pataday)", "Antihistamine", "0.2 %", "Eye", "6 btl", "Convenience A3", "crew", "Remove contacts; wait 10 min before reinserting.", "Blurred vision, stinging, burning"),
    ("oxymetazoline", "Oxymetazoline (Afrin)", "Decongestant", "0.05 %", "Nasal", "10 btl", "Convenience A1", "crew", "Max 3 consecutive days (rebound congestion).", "Burning, dryness, sneezing"),
    ("pseudoephedrine", "Pseudoephedrine (Sudafed 12 h)", "Decongestant", "120 mg", "Oral", "100 tab", "Convenience B1", "crew", "Caution with high blood pressure.", "Rapid heart rate, high BP, tremor, insomnia"),
    ("saline", "Sodium Chloride (AYR Saline)", "Lubricant", "0.9 %", "Nasal", "3 btl", "Convenience A2", "crew", "", "No significant side effects"),
    ("tears", "Carboxymethylcellulose (Refresh Plus)", "Lubricant", "0.5 %", "Eye", "40 dose", "Convenience A4", "crew", "", "Temporary blurred vision"),
    ("acetaminophen", "Acetaminophen (Tylenol)", "Pain reliever", "325 mg", "Oral", "150 tab", "Convenience B4", "crew", "Max 12 tablets/24 h.", "None within dose"),
    ("ibuprofen", "Ibuprofen (Motrin)", "Pain reliever", "400 mg", "Oral", "400 tab", "Convenience B3", "crew", "Take with food. Max 8 tablets/24 h.", "Upset stomach, dizziness, rash, ringing in ears"),
    ("aspirin", "Aspirin", "Pain reliever", "325 mg", "Oral", "60 tab", "Convenience B4", "crew", "Take with food.", "Upset stomach, dizziness, blood in stool"),
    ("melatonin", "Melatonin", "Sleep", "3 mg", "Oral", "60 tab", "Convenience A4", "crew", "Do not use with other sleep meds.", "Headache, drowsiness, dizziness"),
    ("zolpidem", "Zolpidem (Ambien)", "Sleep", "10 mg", "Oral", "200 tab", "Convenience A3", "surgeon", "Do not use with other sleep meds.", "Drowsiness, dizziness, memory impairment"),
    ("hydrocortisone", "Hydrocortisone", "Steroid", "1 %", "Topical", "60 pkt", "Convenience B1", "crew", "", "None significant"),
    ("mometasone", "Mometasone (Nasonex)", "Steroid", "50 mcg", "Nasal", "3 btl", "Convenience A1", "surgeon", "", "Headache, cough"),
    ("bisacodyl", "Bisacodyl (Dulcolax)", "Stool softener", "5 mg", "Oral", "40 tab", "Convenience B2", "crew", "", "Cramps, nausea, dizziness"),
    ("bacitracin", "Bacitracin", "Antibiotic", "500 u/g", "Topical", "30 pkt", "Convenience Spine", "crew", "", "None significant"),
    ("caffeine", "Caffeine (Vivarin)", "Stimulant", "200 mg", "Oral", "100 tab", "Convenience A3", "crew", "", "Fast heartbeat, anxiety, insomnia"),
    ("diphenhydramine", "Diphenhydramine (Benadryl)", "Antihistamine", "25 mg", "Oral", "60 cap", "Oral A1", "crew", "Sedating. No sleep meds.", "Drowsiness, dry mouth, blurred vision, urinary retention"),
    ("amoxicillin", "Amoxicillin (Amoxil)", "Antibiotic", "500 mg", "Oral", "100 cap", "Oral B1", "surgeon", "", "Nausea, diarrhea, rash"),
    ("azithromycin", "Azithromycin (Zithromax)", "Antibiotic", "250 mg", "Oral", "18 tab", "Oral B1", "surgeon", "", "Diarrhea, nausea, abdominal pain"),
    ("bactrim", "Sulfamethoxazole/Trimethoprim (Bactrim DS)", "Antibiotic", "800/160 mg", "Oral", "40 tab", "Oral B1", "surgeon", "", "Rash, nausea, photosensitivity"),
    ("levofloxacin", "Levofloxacin (Levaquin)", "Antibiotic", "500 mg", "Oral", "50 tab", "Oral B2", "surgeon", "", "Headache, nausea, photosensitivity"),
    ("metronidazole", "Metronidazole (Flagyl)", "Antibiotic", "500 mg", "Oral", "100 tab", "Oral B2", "surgeon", "Take with food.", "Metallic taste, nausea, headache"),
    ("fluconazole", "Fluconazole (Diflucan)", "Antifungal", "150 mg", "Oral", "5 tab", "Oral B2", "surgeon", "", "Headache, nausea, rash"),
    ("acetazolamide", "Acetazolamide (Diamox)", "Altitude sickness", "250 mg", "Oral", "100 tab", "Oral A4", "surgeon", "", "Tingling, increased urine, drowsiness, kidney stones"),
    ("meclizine", "Meclizine (Antivert)", "Motion sickness", "25 mg", "Oral", "20 tab", "Oral A2", "crew", "Sedating. No sleep meds.", "Drowsiness, dry mouth, blurred vision"),
    ("ondansetron", "Ondansetron (Zofran ODT)", "Anti-nausea", "8 mg", "Oral", "30 tab", "Oral A2", "surgeon", "", "Headache, constipation, fatigue"),
    ("promethazine", "Promethazine (Phenergan)", "Anti-nausea", "25 mg", "Oral", "100 tab", "Oral A2", "surgeon", "Sedating. No sleep meds.", "Sedation, blurred vision, dry mouth"),
    ("prednisone", "Prednisone (Deltasone)", "Steroid", "20 mg", "Oral", "40 tab", "Oral A4", "surgeon", "Take with food.", "Fluid retention, high BP, mood changes"),
    ("bismuth", "Bismuth Subsalicylate (Pepto-Bismol)", "Stomach", "262 mg", "Oral", "80 chew", "Oral A3", "crew", "Darkens tongue and stool.", "Dark stool/tongue"),
    ("omeprazole", "Omeprazole (Prilosec)", "Stomach", "20 mg", "Oral", "90 cap", "Oral A4", "crew", "", "Headache, diarrhea, nausea"),
    ("ranitidine", "Ranitidine (Zantac)", "Stomach", "150 mg", "Oral", "60 tab", "Oral A3", "surgeon", "WITHDRAWN from US market in 2020 (kit list is from 2015). Prefer omeprazole.", "Dizziness, headache"),
    ("tamsulosin", "Tamsulosin (Flomax)", "Urinary", "0.4 mg", "Oral", "10 cap", "Oral A4", "surgeon", "", "Dizziness, drowsiness, runny nose"),
    ("lorazepam", "Lorazepam (Ativan)", "Behavioral health", "1 mg", "Oral", "60 tab", "Oral A1", "surgeon", "Sedating. No sleep meds.", "Drowsiness, slowed breathing, memory impairment"),
    ("hydrocodone", "Hydrocodone/Acetaminophen (Vicodin HP)", "Pain reliever", "10/300 mg", "Oral", "30 tab", "Oral A2", "surgeon", "Sedating. No sleep meds.", "Drowsiness, constipation, urinary retention"),
    ("ketorolac", "Ketorolac (Toradol)", "Pain reliever", "30 mg/mL", "IM", "3 vial", "Topical/Inj B4", "surgeon", "", "Nausea, elevated BP, swelling"),
    ("ceftriaxone", "Ceftriaxone (Rocephin)", "Antibiotic", "1 g", "IM", "3 vial", "Topical/Inj B1", "surgeon", "", "Injection-site thickening, rash, diarrhea"),
    ("mupirocin", "Mupirocin (Bactroban)", "Antibiotic", "2 %", "Topical", "2 tube", "Topical/Inj A1", "surgeon", "", "Skin irritation, itching"),
    ("clotrimazole", "Clotrimazole (Lotrimin)", "Antifungal", "1 %", "Topical", "2 tube", "Topical/Inj A2", "crew", "", "Skin irritation"),
    ("moxifloxacin", "Moxifloxacin (Vigamox)", "Antibiotic", "0.5 %", "Eye", "4 btl", "Topical/Inj A1", "surgeon", "No contacts during therapy.", "Eye pain, itching, tearing"),
    ("ciprodex", "Ciprofloxacin/Dexamethasone (Ciprodex)", "Antibiotic", "0.3/0.1 %", "Ear", "2 btl", "Topical/Inj Spine", "surgeon", "", "Ear discomfort, itching"),
    ("debrox", "Carbamide Peroxide (Debrox)", "Earwax removal", "6.5 %", "Ear", "2 btl", "Topical/Inj A4", "crew", "", "Ear irritation"),
    ("cromolyn", "Cromolyn (Nasalcrom)", "Antihistamine", "5.2 mg", "Nasal", "4 btl", "Topical/Inj A3", "crew", "", "Sneezing, nasal burning, cough"),
    ("albuterol", "Albuterol (Proventil HFA)", "Breathing", "90 mcg", "Inhaler", "3", "Topical/Inj A3", "surgeon", "", "Tremor, palpitations, nervousness"),
]
MEDS = {m[0]: dict(zip(("id", "name", "cat", "strength", "route", "qty", "loc", "auth", "comment", "se"), m)) for m in _M}

SLEEP = {"melatonin", "zolpidem"}
SEDATING = {"diphenhydramine", "meclizine", "promethazine", "lorazepam", "hydrocodone"}
ANTIHIST = {"fexofenadine", "loratadine", "diphenhydramine"}

# Symptoms that skip the medication list and go straight to emergency escalation
RED_FLAGS = {"chest pain", "difficulty breathing", "loss of consciousness", "severe allergic reaction",
             "bloody stool", "seizure", "sudden vision loss", "severe abdominal pain", "confusion"}

# (condition, symptoms, kit meds, advice)
CONDITIONS = [
    ("Allergic rhinitis", {"sneezing", "congestion", "runny nose", "itchy eyes"}, ["fexofenadine", "loratadine", "mometasone", "saline", "olopatadine"], "Avoid mixing antihistamines."),
    ("Nasal congestion / sinusitis", {"congestion", "facial pain", "runny nose", "headache"}, ["saline", "pseudoephedrine", "oxymetazoline", "amoxicillin"], "Afrin max 3 days. Antibiotic only if the surgeon confirms bacterial."),
    ("Headache", {"headache", "light sensitivity", "nausea"}, ["acetaminophen", "ibuprofen", "aspirin"], "Check hydration and CO2 levels; persistent or worsening headache needs the surgeon."),
    ("Space motion sickness", {"nausea", "vomiting", "dizziness", "disorientation"}, ["meclizine", "promethazine", "ondansetron"], "Typical in the first days of microgravity."),
    ("Acute diarrhea", {"diarrhea", "abdominal cramps", "nausea"}, ["loperamide", "bismuth", "azithromycin"], "Hydrate. Loperamide only for non-bloody diarrhea."),
    ("Constipation", {"constipation", "abdominal cramps", "bloating"}, ["bisacodyl"], "Fluids and fiber first."),
    ("Insomnia / sleep disruption", {"insomnia", "fatigue", "poor sleep"}, ["melatonin", "zolpidem"], "Use one sleep med only."),
    ("Back pain (space adaptation)", {"back pain", "muscle pain"}, ["ibuprofen", "acetaminophen", "ketorolac"], "Stretching and hot/cold pack from the Diagnostic Pack."),
    ("Urinary tract infection", {"painful urination", "frequent urination", "urgency"}, ["bactrim", "levofloxacin", "ceftriaxone"], "Antibiotics need surgeon authorization."),
    ("Skin rash / infection", {"rash", "itching", "skin redness"}, ["hydrocortisone", "clotrimazole", "bacitracin", "mupirocin"], "Photograph and report if it spreads."),
    ("Eye irritation / infection", {"red eye", "itchy eyes", "eye discharge", "eye pain"}, ["tears", "olopatadine", "moxifloxacin"], "Remove contacts. Use the tonometer if pain is severe."),
    ("Ear infection / blockage", {"ear pain", "ear fullness", "hearing loss"}, ["debrox", "ciprodex"], "Otoscope check first."),
    ("Heartburn / reflux", {"heartburn", "nausea", "abdominal cramps"}, ["omeprazole", "bismuth"], "Chest pain is NOT heartburn until a doctor says so."),
    ("Anxiety / acute stress", {"anxiety", "insomnia", "fatigue", "restlessness"}, ["lorazepam"], "Surgeon authorization only. Talk to the ground psychologist."),
    ("Altitude / hypoxia symptoms", {"headache", "dizziness", "shortness of breath", "nausea"}, ["acetazolamide"], "Check cabin O2 and SpO2 immediately."),
    # --- added by the ICHOR team for the free-text symptom search (same kit, team-built mapping) ---
    ("Fever / viral illness", {"fever", "cough", "sore throat", "fatigue", "muscle pain", "headache"}, ["acetaminophen", "ibuprofen", "saline"], "Isolate from the crew, record temperature, hydrate. No cough suppressant is in this kit list."),
    ("Dehydration", {"thirst", "dark urine", "dizziness", "headache", "fatigue"}, [], "Drink fluids and check the hydration log; no kit drug is needed. Report if dizziness continues."),
    ("Muscle / joint strain", {"joint pain", "muscle pain", "swelling", "back pain"}, ["ibuprofen", "acetaminophen"], "Rest the area, use the hot/cold pack from the Diagnostic Pack, report swelling that grows."),
    ("Vision change (possible SANS)", {"blurred vision", "eye pain", "headache", "light sensitivity"}, ["tears"], "Run a visual-acuity check, one eye at a time, and report to the flight surgeon: see the SANS protocol."),
    ("Rapid heartbeat (needs a vitals check)", {"palpitations", "dizziness", "anxiety", "shortness of breath"}, [], "Measure heart rate and blood pressure with the kit. Contact the flight surgeon if resting HR stays above 100 or with chest pain."),
]
ALL_SYMPTOMS = sorted({s for _, sy, _, _ in CONDITIONS for s in sy} | RED_FLAGS)


def diagnose(symptoms):
    out = []
    for name, sy, meds, advice in CONDITIONS:
        hit = sy & symptoms
        if hit:
            score = len(hit) / len(sy) * 0.6 + len(hit) / len(symptoms) * 0.4
            out.append({"name": name, "score": score, "hit": hit, "meds": meds, "advice": advice})
    return sorted(out, key=lambda c: -c["score"])[:3]


def conflicts(med, taking):
    t = set(taking)
    if med in SLEEP and t & SEDATING: return "sedating drug already taken"
    if med in SEDATING and t & SLEEP: return "sleep med already taken"
    if med in SLEEP and t & (SLEEP - {med}): return "another sleep med taken"
    if med in ANTIHIST and t & (ANTIHIST - {med}): return "another antihistamine taken"
    return None


def render_symptom_panel():
    st.markdown("### 🩺 SYMPTOM CHECKER · KIT 3.001 (DECISION SUPPORT)")
    st.caption("Educational prototype. Not a diagnosis. Kit data: NASA Medical Kit 3.001 (2015). Any drug beyond crew-use items needs flight surgeon authorization.")
    c1, c2 = st.columns([2, 1])
    with c1:
        syms = set(st.multiselect("Symptoms", ALL_SYMPTOMS, key="sx_sel"))
    with c2:
        taking = st.multiselect("Already taking", sorted(MEDS), format_func=lambda k: MEDS[k]["name"], key="sx_taking")
    if not syms:
        return
    flags = syms & RED_FLAGS
    if flags:
        st.error("🚨 RED FLAG: " + ", ".join(sorted(flags)) + ". Contact the flight surgeon NOW and use the Emergency Medical Treatment Pack (red). No self-medication list is shown.")
        return
    for c in diagnose(syms):
        st.markdown(f"**{c['name']}** · match {c['score']*100:.0f}% · symptoms: {', '.join(sorted(c['hit']))}")
        st.caption(c["advice"])
        for mid in c["meds"]:
            m = MEDS[mid]
            bad = conflicts(mid, taking)
            tag = "🟢 crew use" if m["auth"] == "crew" else "🟠 surgeon authorization"
            if bad:
                st.warning(f"⛔ {m['name']}: blocked ({bad}).")
                continue
            with st.expander(f"💊 {m['name']} · {m['strength']} · {m['route']} · {tag}"):
                st.markdown(f"**Kit location:** {m['loc']}  ·  **Qty:** {m['qty']}  \n"
                            f"**Rules:** {m['comment'] or '-'}  \n**Side effects:** {m['se']}")