-- seed_real.sql : REAL, OPEN, published numbers only (no invented measurements).
-- Every cohort row cites its source in assessment_sessions.notes and in the data_sources table.
-- Inspiration4 crew rows (C001-C004) start EMPTY: run  python import_osdr_cbc.py <LSDS-7 CBC csv>  to load the real blood counts.

-- Subjects: named after the open dataset they come from (individual astronaut names are not used:
-- the OSDR crew data is de-identified as C001-C004 and the sleep data is a cohort mean).
INSERT INTO astronauts (id, name, mission_name, mission_day, created_at) VALUES
 (1, 'ISS Crew Cohort (Barger 2014, n=21)',     'ISS long-duration missions 2006-2011', 155, '2014-08-08 00:00:00'),
 (2, 'Shuttle Crew Cohort (Barger 2014, n=64)', 'Space Shuttle missions 2001-2011',      13, '2014-08-08 00:00:00'),
 (3, 'Inspiration4 · Crew C001',                'SpaceX Inspiration4 (OSDR OSD-569)',     3, '2021-09-18 00:00:00'),
 (4, 'Inspiration4 · Crew C002',                'SpaceX Inspiration4 (OSDR OSD-569)',     3, '2021-09-18 00:00:00'),
 (5, 'Inspiration4 · Crew C003',                'SpaceX Inspiration4 (OSDR OSD-569)',     3, '2021-09-18 00:00:00'),
 (6, 'Inspiration4 · Crew C004',                'SpaceX Inspiration4 (OSDR OSD-569)',     3, '2021-09-18 00:00:00');

INSERT INTO indicators (id, slug, name, category, unit, instructions, equipment, preparation, frequency) VALUES
 (1,  'heart_rate',        'Heart Rate',               'Cardiovascular',  'bpm',         'Measure your pulse using the designated heart-rate sensor. Remain still while the reading is taken.', 'Heart-rate monitor', 'Rest before taking the measurement and follow the sensor instructions.', 'According to mission protocol'),
 (2,  'systolic_bp',       'Systolic Blood Pressure',  'Cardiovascular',  'mmHg',        NULL, NULL, NULL, NULL),
 (3,  'diastolic_bp',      'Diastolic Blood Pressure', 'Cardiovascular',  'mmHg',        NULL, NULL, NULL, NULL),
 (4,  'sleep_duration',    'Sleep Duration',           'Psychological',   'hours',       'Record the total time you slept during the previous sleep period.', 'Sleep tracking system or manual input', 'Use the previous completed sleep period.', 'Daily'),
 (5,  'body_temperature',  'Body Temperature',         'General Health',  '°C',          NULL, NULL, NULL, NULL),
 (6,  'oxygen_saturation', 'Oxygen Saturation',        'General Health',  '%',           NULL, NULL, NULL, NULL),
 (7,  'respiratory_rate',  'Respiratory Rate',         'Cardiovascular',  'breaths/min', NULL, NULL, NULL, NULL),
 (8,  'body_weight',       'Body Weight',              'General Health',  'kg',          NULL, NULL, NULL, NULL),
 (9,  'sleep_quality',     'Sleep Quality',            'Behavioral',      'score_1_5',   NULL, NULL, NULL, NULL),
 (10, 'mood',              'Mood',                     'Behavioral',      'score_1_5',   NULL, NULL, NULL, NULL),
 (11, 'fatigue',           'Fatigue',                  'Behavioral',      'score_1_5',   NULL, NULL, NULL, NULL),
 (12, 'exercise_duration', 'Exercise Duration',        'Musculoskeletal', 'minutes',     NULL, NULL, NULL, NULL),
 (13, 'balance_performance','Balance Performance',     'Sensorimotor',    'score',       NULL, NULL, NULL, NULL),
 (14, 'hydration_status',  'Hydration Status',         'Nutrition',       'score_1_5',   NULL, NULL, NULL, NULL),
 -- blood counts from NASA OSDR OSD-569 (Quest Diagnostics CBC, Sysmex XN). Units are normalised by import_osdr_cbc.py
 (15, 'lymphocytes',       'Lymphocyte count',         'Immune',          'cells/uL',    NULL, NULL, NULL, NULL),
 (16, 'hemoglobin',        'Hemoglobin',               'Blood',           'g/dL',        NULL, NULL, NULL, NULL),
 (17, 'hematocrit',        'Hematocrit',               'Blood',           '%',           NULL, NULL, NULL, NULL),
 (18, 'white_blood_cells', 'White blood cells',        'Immune',          '10^3/uL',     NULL, NULL, NULL, NULL),
 (19, 'platelets',         'Platelets',                'Blood',           '10^3/uL',     NULL, NULL, NULL, NULL);

-- Barger et al., Lancet Neurology 2014: mean sleep per night in space (ISS 6.09 h, Shuttle 5.96 h). NASA scheduled 8.5 h.
INSERT INTO assessment_sessions (id, astronaut_id, assessment_type, started_at, completed_at, notes) VALUES
 (1, 1, 'published_cohort_mean', '2014-08-08 00:00:00', '2014-08-08 00:00:00', 'SOURCE barger2014: ISS mean sleep 6.09 h/night, 21 crew, 13 flights, avg 155 in-flight nights. doi 10.1016/S1474-4422(14)70122-X'),
 (2, 2, 'published_cohort_mean', '2014-08-08 00:00:00', '2014-08-08 00:00:00', 'SOURCE barger2014: Shuttle mean sleep 5.96 h/night, 64 crew, avg 13.2 in-flight nights. doi 10.1016/S1474-4422(14)70122-X');
INSERT INTO measurements (astronaut_id, indicator_id, value, measured_at, session_id) VALUES
 (1, 4, 6.09, '2014-08-08 00:00:00', 1),
 (2, 4, 5.96, '2014-08-08 00:00:00', 2);

CREATE TABLE IF NOT EXISTS data_sources (
    id INTEGER PRIMARY KEY, key TEXT NOT NULL UNIQUE, title TEXT NOT NULL, url TEXT NOT NULL, license_note TEXT, used_for TEXT);
INSERT INTO data_sources (key, title, url, license_note, used_for) VALUES
 ('osdr_osd569',  'NASA OSDR OSD-569: Whole blood measurements from SpaceX Inspiration4 (CBC, RNA-seq, WGS)', 'https://osdr.nasa.gov/bio/repo/data/studies/OSD-569', 'Open access, de-identified crew C001-C004', 'Blood counts (lymphocytes, hemoglobin, hematocrit, WBC, platelets) via import_osdr_cbc.py'),
 ('osdr_osd575',  'NASA OSDR OSD-575: Inspiration4 blood serum metabolic panel and immune/cardiac cytokines', 'https://osdr.nasa.gov/bio/repo/data/studies/OSD-575', 'Open access, de-identified', 'Optional: metabolic panel (potassium, glucose ...)'),
 ('osdr_i4',      'NASA OSDR: SpaceX Inspiration4 mission (all studies)', 'https://osdr.nasa.gov/bio/repo/data/missions/SpaceX%20Inspiration4', 'Open access', 'Mission overview'),
 ('i4_paper',     'Sanders et al. 2024, Inspiration4 data access through the NASA OSDR, npj Microgravity', 'https://doi.org/10.1038/s41526-024-00393-5', 'Open access article', 'How to download / query (GLOpenAPI)'),
 ('glopenapi',    'NASA GeneLab GLOpenAPI', 'https://visualization.genelab.nasa.gov/GLOpenAPI/', 'Public API', 'Programmatic access to OSDR files'),
 ('barger2014',   'Barger et al. 2014, Lancet Neurology: sleep deficiency and hypnotic use in astronauts', 'https://doi.org/10.1016/S1474-4422(14)70122-X', 'Published article; numbers quoted as cohort means', 'Sleep duration of the ISS and Shuttle cohorts'),
 ('nasa_radiation','NASA OCHMO Radiation Protection Technical Brief (NASA-STD-3001)', 'https://www.nasa.gov/wp-content/uploads/2023/03/radiation-protection-technical-brief-ochmo.pdf', 'US Government work', '600 mSv career limit, 250 mSv per event, ISS and deep-space dose rates'),
 ('natacad_2021', 'National Academies: Space Radiation and Astronaut Health (2021)', 'https://doi.org/10.17226/26155', 'Published report', 'Rationale for radiation limits'),
 ('sibonga2013',  'Sibonga 2013, Spaceflight-induced bone loss, Curr Osteoporos Rep', 'https://doi.org/10.1007/s11914-013-0136-5', 'Published article', 'Bone loss 1-1.5 %/month'),
 ('hrp',          'NASA Human Research Program: Human Research Roadmap', 'https://humanresearchroadmap.nasa.gov', 'US Government work', 'Risk pages: radiation, SANS, bone, sleep, behavioral health'),
 ('remm',         'NLM REMM: Radiation Emergency Medical Management', 'https://remm.hhs.gov', 'US Government work', 'Lymphocyte reference values, filgrastim reference dose'),
 ('spaceapps2026','NASA Space Apps Challenge 2026', 'https://www.spaceappschallenge.org', 'Event site', 'Challenge context: physiological and behavioral health monitoring'),
 ('lsda',         'NASA Life Sciences Data Archive / LSAH (restricted access, not open)', 'https://lsda.jsc.nasa.gov', 'Access by request only', 'Reference only: individual astronaut records are NOT open');