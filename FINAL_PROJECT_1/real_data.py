"""
real_data.py - reference thresholds, scenario simulation and clinical playbooks for Project ICHOR.
Thresholds come from published sources (see SOURCES_MD); a flight surgeon decides on any medication.
"""
import random

# ---------------------------------------------------------------- thresholds
NASA_THRESHOLDS = {
    # ---- official / published values --------------------------------------
    "max_cumulative_radiation_msv": 600.0,   # NASA-STD-3001 Vol.1: career limit
    "spe_limit_msv": 250.0,                  # NASA-STD-3001: limit per solar particle event
    "iss_dose_msv_per_day": 0.5,             # NASA OCHMO brief: ~0.5 mSv/day on ISS
    "deep_space_dose_msv_per_day": 1.5,      # same brief: 1.5 mSv/day used for Mars transit
    "alc_normal_low": 1000.0,                # adult lymphocytes 1,000-4,800 per microlitre;
    "alc_normal_high": 4800.0,               #   below 1,000 = lymphocytopenia (NHLBI)
    "alc_mean": 2450.0,                      # REMM: consensus mean 2.45 x10^9 cells/L
    "iop_normal_high": 21.0,                 # standard clinical upper limit of normal (mmHg)
    "bone_loss_pct_per_month": 1.25,         # NASA: 1-1.5 % per month, weight-bearing bones
    "sleep_rec_low_h": 7.0,                  # NSF/AASM 7-9 h (quoted in NASA OCHMO sleep brief)
    "sleep_rec_high_h": 9.0,
    # ---- TEAM early-warning thresholds (NOT official NASA limits) ---------
    "rad_warn_career_frac": 0.80,            # warn at 80 % of the career limit
    "rad_warn_event_frac": 0.50,              # warn at 50 % of the per-event limit
    "alc_warn": 1500.0,                      # mild-lymphopenia early warning
    "iop_warn": 19.0,                        # within 2 mmHg of the upper limit
    "bmd_warn_pct": -5.0,                    # BMD change vs baseline
    "bmd_crit_pct": -10.0,                   # NASA: >10 % losses seen in some crew after ~6 months
    "sleep_crit_h": 6.0,                     # NASA: crews average ~6-6.5 h, below the 7-9 h guidance
}

# Fallback simulation profiles (used only if the database has no astronaut of that name). Baseline sleep numbers are published:
# Alex Morgan = ISS cohort mean (Barger 2014), Sarah Chen = Shuttle cohort mean, James Wilson = 7-9 h guideline midpoint.
PROFILES = {
    "Alex Morgan": {
        "sleep_h": 6.09,   # mean sleep on ISS missions, Barger et al., Lancet Neurol 2014 (crews were scheduled for 8.5 h)
        "source": "Barger et al. 2014, doi 10.1016/S1474-4422(14)70122-X",
    },
    "Sarah Chen": {
        "sleep_h": 5.96,   # mean sleep on Space Shuttle missions, same study
        "source": "Barger et al. 2014, doi 10.1016/S1474-4422(14)70122-X",
    },
    "James Wilson": {
        "sleep_h": 8.0,    # midpoint of the 7-9 h recommendation quoted in NASA OCHMO-TB-041
        "source": "NASA OCHMO-TB-041 (sleep technical brief); NSF/AASM 7-9 h",
    },
}

SCENARIOS = [
    "Routine Operations",
    "Solar Particle Event (Storm)",
    "Deep Space Isolation Fatigue",
    "Fluid Shift / Vision Change (SANS)",
]


# ------------------------------------------------------------------ simulate
def simulate_scenario(astronaut: str, day: int, scenario: str) -> dict:
    """Scenario values around REAL published reference numbers (stable per input); baseline sleep comes from the selected profile."""
    T = NASA_THRESHOLDS
    rng = random.Random(f"{astronaut}|{day}|{scenario}")

    rad = day * T["deep_space_dose_msv_per_day"]
    event = 0.0
    alc = T["alc_mean"] + rng.uniform(-150, 150)
    iop = 16.0 + rng.uniform(-1.0, 1.0)
    base_sleep = PROFILES.get(astronaut, {}).get("sleep_h", 7.4)
    sleep = base_sleep + rng.uniform(-0.3, 0.3)
    bmd = -T["bone_loss_pct_per_month"] * day / 30.0 * (1 + rng.uniform(-0.1, 0.1))

    if scenario.startswith("Solar"):
        event = 260.0 + rng.uniform(-10, 10)   # just above the 250 mSv per-event limit
        rad += event
        alc = 1300.0 + rng.uniform(-60, 60)
        sleep = min(base_sleep, 6.6) + rng.uniform(-0.2, 0.2)
    elif "Isolation" in scenario:
        sleep = min(base_sleep - 0.7, 5.4) + rng.uniform(-0.3, 0.3)
    elif "SANS" in scenario:
        iop = 22.4 + rng.uniform(-0.4, 0.4)

    return {
        "rad_msv": round(rad, 1),
        "event_msv": round(event, 1),
        "alc": round(alc),
        "iop": round(iop, 1),
        "bmd_pct": round(bmd, 1),
        "sleep_h": round(sleep, 1),
    }


def _level(is_crit: bool, is_warn: bool) -> str:
    return "crit" if is_crit else "warn" if is_warn else "ok"


def assess(sim: dict) -> dict:
    """Status ('ok' / 'warn' / 'crit') for each indicator."""
    T = NASA_THRESHOLDS
    career = sim["rad_msv"] / T["max_cumulative_radiation_msv"]
    event = sim["event_msv"] / T["spe_limit_msv"]
    return {
        "radiation": _level(career >= 1 or event >= 1,
                            career >= T["rad_warn_career_frac"] or event >= T["rad_warn_event_frac"]),
        "immune": _level(sim["alc"] < T["alc_normal_low"], sim["alc"] < T["alc_warn"]),
        "ocular": _level(sim["iop"] > T["iop_normal_high"], sim["iop"] >= T["iop_warn"]),
        "bone": _level(sim["bmd_pct"] <= T["bmd_crit_pct"], sim["bmd_pct"] <= T["bmd_warn_pct"]),
        "sleep": _level(sim["sleep_h"] < T["sleep_crit_h"], sim["sleep_h"] < T["sleep_rec_low_h"]),
    }


def build_raw_alerts(states: dict, sim: dict) -> list:
    """List of (severity, reason, playbook_id) for the app's alert merger."""
    T = NASA_THRESHOLDS
    sev = {"crit": "CRITICAL", "warn": "WARNING"}
    out = []

    if states["radiation"] != "ok":
        if sim["event_msv"] >= T["spe_limit_msv"]:
            why = f"Solar particle event dose ({sim['event_msv']:.0f} mSv) reached the {T['spe_limit_msv']:.0f} mSv per-event limit"
        elif sim["rad_msv"] >= T["max_cumulative_radiation_msv"]:
            why = "Cumulative dose reached the 600 mSv career limit"
        else:
            why = "Radiation dose approaching a NASA limit"
        out.append((sev[states["radiation"]], why, "ASCLEPIUS_RAD_SHIELD"))

    if states["immune"] != "ok":
        why = ("Lymphocytopenia: count below 1,000 per microlitre" if states["immune"] == "crit"
               else "Lymphocyte count falling (early warning below 1,500 per microlitre)")
        out.append((sev[states["immune"]], why, "ASCLEPIUS_RAD_SHIELD"))

    if states["ocular"] != "ok":
        why = ("Intraocular pressure above the normal range (SANS follow-up needed)" if states["ocular"] == "crit"
               else "Intraocular pressure close to the upper normal limit")
        out.append((sev[states["ocular"]], why, "ASCLEPIUS_SANS_REVERSE"))

    if states["bone"] != "ok":
        why = (f"Bone density down {abs(sim['bmd_pct']):.1f} percent versus baseline")
        out.append((sev[states["bone"]], why, "ASCLEPIUS_BMD_BOOST"))

    if states["sleep"] != "ok":
        why = (f"Sleep {sim['sleep_h']:.1f} h per night, below the 7-9 h recommendation")
        out.append((sev[states["sleep"]], why, "ASCLEPIUS_MENTAL_DECOMPRESSION"))

    return out


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def crew_integrity(sim: dict) -> int:
    """Team-defined 0-100 summary (NOT a clinical score): mean of five 0-1 sub-scores."""
    T = NASA_THRESHOLDS
    parts = [
        1 - _clamp(max(sim["rad_msv"] / T["max_cumulative_radiation_msv"],
                       sim["event_msv"] / T["spe_limit_msv"])),
        _clamp((sim["alc"] - T["alc_normal_low"]) / (T["alc_mean"] - T["alc_normal_low"])),
        _clamp((T["iop_normal_high"] - sim["iop"]) / (T["iop_normal_high"] - 15.0)),
        _clamp(1 + sim["bmd_pct"] / 10.0),
        _clamp((sim["sleep_h"] - 4.0) / (T["sleep_rec_low_h"] - 4.0)),
    ]
    return round(100 * sum(parts) / len(parts))


# ------------------------------------------------------------------ playbooks
# Same structure the dashboard already renders. Doses are REFERENCE INFORMATION
# from public sources; a flight surgeon decides what is actually given.
PLAYBOOKS = {
    "ASCLEPIUS_RAD_SHIELD": {
        "title": "Radiation Shielding & Monitoring Protocol",
        "condition": "High radiation dose (solar particle event) or falling lymphocyte count",
        "medication": {
            "name": "Shielding and dose avoidance come first; no drug replaces them. "
                    "If blood work shows a significant lymphocyte drop, the flight surgeon may consider filgrastim (G-CSF).",
            "dosage": "Filgrastim (only on flight-surgeon decision): 10 mcg/kg/day subcutaneously, the typical dose for acute "
                      "exposure to myelosuppressive radiation doses. 5 mcg/kg/day applies only when supplies are limited.",
            "source": "NLM REMM (myeloid cytokines for H-ARS) · NASA-STD-3001 (dose limits)",
        },
        "steps": [
            "🔴 Move to the most shielded area / storm shelter of the vehicle, as the mission procedure defines.",
            "💧 Use the available shielding around the sleeping area, only as the mission plan provides.",
            "📟 Record the personal dosimeter readings and notify the flight surgeon in parallel (communication delay applies).",
            "🩸 Run a blood test (CBC with differential) and repeat it so the lymphocyte trend becomes visible.",
            "🛑 Postpone non-essential extravehicular activities (EVA) until the event subsides.",
        ],
    },
    "ASCLEPIUS_SANS_REVERSE": {
        "title": "Eye-Change Monitoring Protocol (SANS)",
        "condition": "Spaceflight-associated neuro-ocular syndrome (SANS): vision changes / raised intraocular pressure",
        "medication": {
            "name": "There is no established drug therapy. The decision belongs to the flight surgeon.",
            "dosage": "—",
            "source": "NASA Human Research Program · Risk of SANS (Human Research Roadmap)",
        },
        "steps": [
            "👁️ Check visual acuity (one eye at a time) and note blurred vision or a change in near vision.",
            "📷 If the equipment is available, take fundus/OCT imaging or an eye ultrasound and send it to Earth.",
            "👖 Discuss with the flight surgeon the use of a lower-body negative pressure device (e.g. Chibis) to shift fluids.",
            "📡 Notify Earth: vision changes need medical evaluation.",
        ],
    },
    "ASCLEPIUS_BMD_BOOST": {
        "title": "Bone Protection Protocol (Exercise & Therapy)",
        "condition": "Bone-density loss due to microgravity (~1-1.5% per month in weight-bearing bones)",
        "medication": {
            "name": "Alendronate (bisphosphonate) and vitamin D/calcium, only on flight-surgeon instruction.",
            "dosage": "Alendronate 70 mg by mouth once a week (dose used in ISS studies); "
                      "the vitamin D dose is set by the flight surgeon.",
            "source": "NASA HRP Evidence Report: Risk of Bone Fracture (2017) · NASA: Risk of Spaceflight-Induced Bone Changes · Sibonga 2013",
        },
        "steps": [
            "🏋️ Perform the scheduled resistive exercise (e.g. ARED): it is the main countermeasure for bone.",
            "🥛 If you were given alendronate: take it with a full glass of plain water, at least 30 minutes before the first food or drink (standard label instruction).",
            "🥗 Check that calcium and vitamin D intake meets the nutrition plan.",
            "📊 Log exercise load and frequency; do not increase the load on your own without trainer/flight-surgeon advice.",
        ],
    },
    "ASCLEPIUS_MENTAL_DECOMPRESSION": {
        "title": "Sleep & Behavioral Health Protocol",
        "condition": "Insufficient sleep / circadian disruption and psychological strain due to isolation",
        "medication": {
            "name": "Sleep medication (e.g. melatonin) only on flight-surgeon instruction.",
            "dosage": "The dose is set by the flight surgeon. Caution: sleep aids can reduce alertness "
                      "if a sudden alarm wake-up is needed.",
            "source": "NASA OCHMO sleep technical brief (OCHMO-TB-041) · Barger et al., Lancet Neurology 2014",
        },
        "steps": [
            "😴 Aim for 7-9 hours of sleep (NSF/AASM recommendation) with fixed sleep and wake times.",
            "💡 If the habitat allows, use dim/warm lighting before sleep and alerting light in the morning.",
            "🤫 Reduce noise and light in the sleeping area; environmental causes affect sleep in space.",
            "🗣️ If low mood, anxiety or withdrawal continue for days, talk to the behavioral-health team on Earth.",
        ],
    },
}


# -------------------------------------------------------------------- sources
SOURCES_MD = """
**What is real, what is simulated**

Individual astronaut health records are private, so no open dataset contains a full vitals time series for named
astronauts. ICHOR therefore uses three layers, always labelled:

1. **Real open data**: NASA OSDR Inspiration4 de-identified crew data (blood counts, OSD-569 / metabolic panel, OSD-575),
   and published cohort statistics (ISS and Shuttle sleep, Barger et al. 2014). These are the records in the database.
2. **Real reference limits**: NASA-STD-3001 radiation limits, NHLBI / clinical normal ranges (used for the thresholds).
3. **Simulated scenarios and team-defined scores**: the scenario simulator, the live ECG stream, the per-cell spread in the
   3D scans, the early-warning thresholds and the Crew Integrity Index. Educational prototype, not medical advice.

**Data sources (open) and links**

| What | Source and link |
|---|---|
| Inspiration4 crew blood counts (CBC), RNA-seq, WGS; de-identified crew C001-C004, time points L-92 ... R+194 | NASA OSDR **OSD-569** · https://osdr.nasa.gov/bio/repo/data/studies/OSD-569 |
| Inspiration4 blood serum metabolic panel and immune/cardiac cytokines | NASA OSDR **OSD-575** · https://osdr.nasa.gov/bio/repo/data/studies/OSD-575 |
| All Inspiration4 studies (OSD-569 to OSD-575, OSD-630, OSD-656, OSD-687) | https://osdr.nasa.gov/bio/repo/data/missions/SpaceX%20Inspiration4 |
| How to access the Inspiration4 data (GLOpenAPI) | Sanders et al., npj Microgravity 2024, doi 10.1038/s41526-024-00393-5 · https://doi.org/10.1038/s41526-024-00393-5 · API: https://visualization.genelab.nasa.gov/GLOpenAPI/ |
| Sleep on ISS = 6.09 h/night, Shuttle = 5.96 h/night (85 astronauts, >4,200 nights in space); 8.5 h scheduled | Barger et al., *Lancet Neurology* 2014 · https://doi.org/10.1016/S1474-4422(14)70122-X |
| Career limit 600 mSv; 250 mSv per solar particle event; ~0.5 mSv/day ISS; ~1.5 mSv/day Mars transit | NASA OCHMO *Radiation Protection Technical Brief* (NASA-STD-3001) · https://www.nasa.gov/wp-content/uploads/2023/03/radiation-protection-technical-brief-ochmo.pdf |
| Rationale for the 600 mSv limit | National Academies, *Space Radiation and Astronaut Health* (2021) · https://doi.org/10.17226/26155 |
| Bone loss 1-1.5 % per month; >10 % in some crew | Sibonga, *Curr Osteoporos Rep* 2013 · https://doi.org/10.1007/s11914-013-0136-5 · NASA HRP *Risk of Fracture* evidence report |
| Hip loss 1.4-1.5 %/month, spine 0.9 %/month (ISS) | *J Bone Miner Res* 2004;19(6):1006-12 · https://doi.org/10.1359/JBMR.040307 |
| Sleep 7-9 h recommended | NASA OCHMO *Sleep Accommodations Technical Brief* (OCHMO-TB-041) |
| Lymphocytes 1,000-4,800 per microlitre; mean 2.45 x10^9/L; filgrastim for acute radiation exposure | NHLBI (lymphocytopenia) · NLM REMM https://remm.hhs.gov |
| Intraocular pressure normal up to about 21 mmHg | Standard clinical reference range |
| Risk pages (radiation, SANS, bone, sleep, behavioral health) | NASA Human Research Program · https://humanresearchroadmap.nasa.gov |
| Space biology data, general | NASA Open Science Data Repository · https://osdr.nasa.gov |
| Astronaut medical kit used by the symptom search | NASA Medical Kit 3.001 (MED CL/SpX-6, 09 APR 15), see ichor_symptoms.py |
| Challenge context (2026: physiological and behavioral health monitoring for long-duration travel) | https://science.nasa.gov/universe/nasa-welcomes-all-ages-experience-levels-for-space-apps-challenge/ · https://www.spaceappschallenge.org |
| Related NASA HRP challenge (Artemis II small-sample human data) | https://www.nasa.gov/hrp/winners-of-nasa-hrps-artemis-ii-data-methodology-challenge/ |
| Lifetime astronaut health data (restricted access, not open) | NASA LSDA / LSAH · https://lsda.jsc.nasa.gov |

**Team assumptions (not NASA limits):** early-warning thresholds (80 % of career limit, 50 % of the per-event limit,
lymphocytes below 1,500, IOP 19 mmHg or more, bone change of -5 % / -10 %, sleep below 7 h / 6 h), the organ mapping of
each indicator, the scenario events, the live ECG stream, the per-organ spread in the 3D scans and the Crew Integrity Index.

**Libraries:** Streamlit (Apache 2.0), Plotly (MIT), pandas and NumPy (BSD).
"""