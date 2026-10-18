# Adaptive scheduling: seasons, peak hours, exams, learning and predictions

Research and design for the owner request of 2026-10-17: *"The scheduler should adapt seasonally, during peak
hours, exam times and so on, learn from before, and maybe even make predictions, and exams."*
Ledger `adaptive-scheduling-res-2026-10-17`. The tickets are AS-01…AS-20 at the end of [docs/ROADMAP.md](../ROADMAP.md)
("Adaptive scheduling, seasons and predictions").

**BLUF.** SmartSched already does the hardest piece well. Learning from earlier terms (`services/learning*.py`)
is season-aware, decays old evidence, explains every suggestion, treats a suggestion as advice that only a person
can accept, can be reset and is KVKK-safe. Two other pieces exist on their own: an exam-period booking mode and
utilisation heatmaps. What is missing is the layer that ties these to the calendar.

- **Solver.** It does not know what kind of period it is planning. It ignores holidays, and runs use the admin's
  default weights only when the Studio page sends them.
- **Bookings.** Nobody records unmet demand.
- **Exams.** The exam solver chooses rooms only, never dates.
- **Forecasting.** No forecasting code exists.

Our own fixtures show that the patterns are very regular:

- **Weekly volume.** Bahar lecture weeks vary by 0.85 % (coefficient of variation).
- **Peak hours.** P4 and P8 run at 85–92 % of rooms, and the period profile carries over from Bahar to Güz with
  r = 0.995.
- **Exams.** Final exams peak on Wednesday 3 June 2026 (126 exam-list rows, 5,532 seats), which is 1.9× the weekday mean.
  Counted in sittings (a shared exam once), the unit the app uses since 2026-10-18 (AS20-F13), the peak is 98 sittings, 1.67×.

These are simple, explainable models: shrunken historical profiles, seasonal-naive forecasts with empirical
intervals, and request-driven what-if counts. Machine learning is not needed. The design adds season profiles, a
peak model, a demand ledger, forecasts, exam-period advice and versioned learning. Every output is a suggestion
that an admin approves.

---

## 1. Current state (code map, 2026-10-17)

Paths are relative to `smartsched/backend/app/` unless they start with `frontend/`.

### 1.1 Term types and how the solver treats them

| What | Where | Behaviour |
|---|---|---|
| Term kind | `models/catalog.py:18` `Term.kind` = `REGULAR, FINAL, BUT, SUMMER` | Free text, default `REGULAR`. Bahar and Güz are both `REGULAR`; the season comes from the code. |
| Season from code | `services/learning.py:152-163` `season_of()` | Reads `BAHAR / GUZ / YAZ / BUT / FINAL` from `Term.code` (also SPRING/FALL/SUMMER). Only the learning service uses it. |
| Week kinds | `models/catalog.py:39` `Week.kind` = `LECTURE, EXAM, HOLIDAY, MAKEUP` | Set by the weekly-grid importer from the sheet names (`importers/weekly_grid.py:93` `sheet_kind`, `LECTURE/EXAM/MAKEUP/SUMMER`), by the CRBS importer (`importers/crbs_legacy.py:689` HOLIDAY) and by `PUT /terms/{id}/weeks` (`api/v1/terms.py:173`). |
| Run kind | `models/runs.py` `ScheduleRun.kind` = `COURSE / EXAM` | `services/solver_bridge.py:587` branches only on COURSE vs EXAM. |
| Horizon | `services/solver_bridge.py:200-212` `horizon_weeks()` | Returns every week `1..week_count` (or the WEEK/MONTH slice). It ignores `Week.kind`, so HOLIDAY weeks are planned like lecture weeks. |
| Weights | `solver/weights.py:11-37` `DEFAULT_WEIGHTS`; `services/solver_bridge.py:1244` `weights=dict(params.get("weights", {}))` | One global table. The admin's `solver_weights` setting (`services/settings_service.py:33`) is **not read by the backend**. Only the Studio page copies it into run params (`frontend/src/components/studio/generate-step.tsx:78`), so moderation re-solves, API runs and `stack.sh runs` use the code defaults. No per-term-kind or per-period weights exist. |
| Relaxation policy | `solver/policy.py`, `api/v1/terms.py:231-238` | Per term (lock_first / most_classes_first). Already a per-term solver knob, and a model for profiles. |

**Gap:** the solver does not know whether it is planning Güz, Bahar, a summer term, an add/drop week or an
exam week. The only seasonal behaviour in the product is in learning.

### 1.2 Exam scheduling and invigilation

- **Exam timetable = room assignment for fixed times.** The bridge reads `ExamRequest` rows. Rows without a
  date or period are dropped (`services/solver_bridge.py:834-835`), and every exam event is fixed to its listed
  date and start (`fixed_start=first_start` and `fixed_date=head_date`, `:930-932`). The solver picks rooms and
  multi-room splits using `exam_capacity` (`solver/domains.py:48`).
- **Exam rules exist but have nothing to move.** `solver/constraints/exam_gap.py` (cohort gap) and
  `max_exams_per_day.py` are both hard/soft rules. Because times are fixed, they can only report clashes, never
  spread exams. No front-load rule exists (large exams early, as in ITC 2007). No peak-seat cap per slot exists.
- **Invigilation is mature.** `solver/invigilation.py:1-35` covers posts, staffing ratios, busy times from
  teaching and bookings, own-exam rules, daily and total caps, load fairness, stability and Hall-condition
  diagnoses. `services/invigilation.py` (pool, plans, the `/exams/invigilation` UI, the load heatmap at `:1923`)
  works on real data only.
- **Bookings in exam weeks.** `services/booking_policies.py:26-29, 293-330` has an exam-period mode
  (`off | request | closed`) for exam rooms during weeks of kind `EXAM`/`MAKEUP`. It works per whole week. It
  does not hold only the slots that exams use, and it does not adapt to load.

### 1.3 Learning extraction (what it learns, how it is applied)

- **Evidence.** `services/learning_extract.py:1-37, 76-91` turns definitive rooms (+3), planner corrections
  (±2), manual moves and locks (±2), request text and time (+1), booking series (+1), approvals (+1 / −2) and
  suggestion decisions (+2 / −3) into append-only `learned_observations` (`models/learning.py`).
  - Subjects are ids (instructor, course, section, programme, user).
  - Attributes are room, building, day, period band, day×band and tag.
  - Locked double bookings and over-capacity locks are excluded.
- **Priors.** `services/learning.py:1-30, 409-470` `recompute_priors`:
  - The score decays with a half-life of two terms.
  - Confidence is the Wilson lower bound with z = 1 and must be at least 0.6 (`:78-88`).
  - Support must be at least 2 over 2 terms, or at least 3 in one term.
  - Room, tag and time evidence counts only from the **same season** (`SAME_SEASON_ATTRS`, `:88`, applied at
    `:449-450`). Building evidence crosses seasons and is labelled "farklı dönem verisi".
- **Applied by a person only.** Accepting a suggestion (`:992`) creates one soft, targeted
  `ConstraintRow(source="LEARNED")` with weight 5. In `solver/weights.py:24-26` learned weights rank below
  explicit ones (5 and 2). Reject, snooze, restore, reset (person, term or all, with 30-day undo) and KVKK erasure
  all exist. The UI is at `frontend/src/app/(app)/moderation/learning` and in the suggestion cards.
- **Not learned yet.**
  - Solver weights.
  - Time-of-day load or peaks.
  - Booking demand beyond the series-to-user habit.
  - The planning audit stream (TODO stub at `services/learning_extract.py:573-581`).
- **When refresh runs.** Only by hand (`POST /learning/refresh`, `api/v1/learning.py:61`). The lifespan runs
  only the purge job (`main.py:124-136`).
- **Versions.** A recompute overwrites `learned_priors` in place. There is no snapshot to compare against or
  revert to (accepted rules can be undone, a prior set cannot).

### 1.4 Utilisation and heat-map analytics

`services/utilisation.py:1-20` covers:

- room × day × period occupancy for a run or the live board (published runs, blocks, BOOKED bookings, and pending
  holds counted apart);
- grouping by building, room type, capacity band or room;
- `pct = occupied / (capacity − blocked)`;
- CSV export;
- the instructor load heatmap (`:774`).

The UI is at `frontend/src/app/(app)/analytics/heatmap` (`components/analytics/*`). Scenario comparison is in
`services/scenario_compare.py`.

**Not present:**

- a trend across terms;
- peak-hour KPIs (W3E-13 is open);
- seat fill (occupancy against capacity, the HESA/SMG "occupancy rate");
- holiday-aware capacity: holidays are not removed from the denominator.

### 1.5 Booking demand data

- `models/booking.py:351-375` `Booking`: room, date, period span, user, department, status, `headcount`,
  `required_features` (from find-room) and `held_until`. `BookingSlot` keeps one row per period. This is a usable
  demand history *once bookings exist*. The gracious fixtures contain no CRBS bookings; the grid's `ETKİNLİK`
  and club cells become `Block` rows instead (`importers/weekly_grid.py:600-618`).
- **Find-room queries are not stored.** `services/find_room.py:359` `find_rooms` answers and forgets. A search
  that found nothing (unmet demand) leaves no trace. This is the most important missing demand signal.
- `services/bookings_solver.py:1-30`: confirmed bookings become solver blocks for the run's weeks.

### 1.6 Peak-hour handling

There is none. No constraint, setting or warning looks at the load per period. The closest rules are:

- `day_window` (keep a cohort inside a window);
- `evening_programs_in_buildings`;
- `min_capacity_waste`.

### 1.7 Holidays and calendar

- `models/booking.py:265` `Holiday` (per term, date range). Admin UI `/admin/holidays`, API `api/v1/holidays.py`.
- Respected by:
  - bookings (`services/bookings_calendar.py:161-173`, holidays plus HOLIDAY weeks are closed dates);
  - the CRBS export (`services/exports.py:124-167`);
  - find-room's default weeks (`services/find_room.py:192`);
  - Studio (`services/studio.py:235`).
- **Not respected by** the solver bridge, utilisation or the run grid. A class "meets" on 23 Nisan in the
  heatmap. The class calendar feeds belong to the CAL-B lane (`services/calendar_*`).

### 1.8 Forecasting

There is none (`grep -ril "forecast|predict|holt|prophet|seasonal"` hits only an unrelated council file).
numpy 2.5 and pandas 3.0 are installed in the backend venv. scipy and statsmodels are not, and none of them is
needed for the design below.

### 1.9 What the fixtures say (measured 2026-10-17 with the real parsers)

The script is in the scratchpad (`as/occ.py`). It reads `tests/fixtures/*derslikler_takvimi*.xlsx` through
`importers.weekly_grid.parse_weekly_grid` and the Final list through `importers.exam_list.parse_exam_list`.

| Fact | Value | Consequence |
|---|---|---|
| Bahar lecture weeks 1–15, course room-periods per week | mean 1,634, σ 13.8 (CV 0.85 %); non-course blocks ~705, 795 in week 1 | Lecture weeks are flat; week 1 has extra blocks (orientation). A seasonal-naive model is enough. A test that forecasts weeks 9–15 from the mean of weeks 1–8 gives MAPE 0.70 % (naive last value: 0.76 %). |
| Period profile, % of rooms busy on a weekday (Bahar / Güz) | P1 41/30 · P2 66/66 · P3 81/88 · **P4 85/92** · P5 82/88 · P6 40/44 · P7 79/78 · **P8 86/89** · P9 81/82 · P10 72/75 · P11 49/51 · P12–P18 ≤ 12 | Two daily peaks: late morning and early afternoon. Lunch (P6) and the evening have spare capacity. |
| Bahar → Güz shape transfer | Pearson 0.995, Spearman 0.986 over 18 periods | The *time* profile transfers across seasons even though *rooms* do not (consistent with the rule at `learning.py:88`). Cross-season shape with same-season level is a sound forecast. |
| Day profile (Bahar) | Mon 6,399 · Tue 7,036 · **Wed 8,086** · Thu 7,322 · Fri 5,538 · Sat 324 · Sun 555 | Wednesday is the peak day; Friday has about 30 % slack. |
| Final 2026 exams with a room (711 of 921 rows) | 1–12 June. Weekday counts 36, 71, **126**, 102, 67 / 66, 82, 51, 52, 23. Seats: Wed 3 June 5,532 | Peak day is 1.86× the weekday mean. The second Friday is almost empty: the dates are uneven. **Re-baselined 2026-10-18 (AS20-F13, FIX-G)** to sittings, a merge group once (607 sittings of 709 rows with a room and a start period): weekday counts 31, 66, **98**, 78, 59 / 64, 72, 50, 48, 22; peak 1.67× the weekday mean 58.8. |
| Final 2026 peak start-hour bucket | Wed 3 June 16:00, 1,141 seats = 58 % of the total `exam_capacity` (1,951 over 58 rooms); 13:00 is the busiest start hour over the period (165 exams) | Exam seating has headroom in total, but large cohorts fall together. Seat-level peaks matter more than room counts. |
| Bahar workbook Final / BÜT / Yaz sheets | Present but empty (0 entries) | Exam-week occupancy comes from the Final workbook and the exam list, not from the Bahar grid. |
| History depth | 1 Bahar (15 lecture weeks), 1 Güz (2 weeks in the grid, 1,037 list rows), 1 Final | One year. A yearly seasonal model (Prophet needs ≥ 2 years for yearly seasonality) cannot be fitted. Backtests must be within-term (rolling origin) or cross-season shape tests. |

---

## 2. Research (October 2026)

### 2.1 Timetabling practice: seasons, peaks, exams, room demand

- **Each term and exam session is its own problem instance, with its own constraints and objective.** The ITC
  2019 real-world course timetabling instances (built from UniTime data) are per term and per institution
  [3]. UniTime handles course and examination timetabling with separate solvers and separate preferences
  [4, 5]. Peers therefore support seasonal variation by keeping *configuration per problem instance* (term,
  exam session), not one global weight table. SmartSched already has per-term relaxation policies; season
  profiles extend that.
- **Exam timetabling.** The ITC 2007 examination track defines the soft criteria most systems copy [1, 2]:
  - two exams in a row and two in a day for one student;
  - period spread (exams of shared students at least *k* periods apart);
  - mixed durations in one room;
  - **front load** (the largest exams early, so marking can finish);
  - room and period penalties.

  The survey by Qu et al. [6] puts exam timetabling's core in student conflicts, spread and room capacity, with
  seating and invigilation as later stages. UniTime's exam solver also counts back-to-back conflicts for
  instructors and "distance back-to-back" across rooms that are far apart [4]. A 2026 Turkish faculty case ran
  the stages in sequence: date and slot, then room, then invigilators [8]. A 2022 MILP cut the invigilation-hour
  error by 86 %, back-to-back duties by 56 % and unfavourable times by 44 % against manual plans [7].
  SmartSched has stages 2–3 (room, invigilators) but not stage 1 (dates).
- **Space utilisation measures.** UK practice (NAO/SMG, as collected by HESA) uses:
  - **frequency rate** = hours in use ÷ hours available;
  - **occupancy rate** = seats used ÷ seats while in use;
  - **utilisation** = frequency × occupancy [9, 10].

  Sector medians are about 27–30 % [10]. Astra Schedule reports a room's *prime-time* utilisation next to its
  all-day utilisation and its seat fill [11]. A peak-to-mean ratio and a peak-demand forecast are standard
  workplace-analytics measures [12]. SmartSched measures frequency only, so seat fill and prime-time figures
  are cheap to add.
- **Vendors.**
  - Untis/WebUntis keeps exams and room booking as separate modules that check clashes against each other [13].
  - Syllabus Plus, Celcat, EMS and Infosilem are positioned as timetabling plus space-management suites
    (state-of-the-art doc sources 7–10).
  - No public documentation for these products describes learned or forecast demand. Peer "analytics" means
    descriptive dashboards.

  A small, explainable forecast that an admin approves would therefore put SmartSched ahead of its peers.
- **Room-demand and enrolment forecasting.** Institutions project course demand with cohort-progression
  (grade-progression) ratios: next-year enrolment in year *k+1* = this year's year-*k* enrolment × the ratio of
  past transitions. The ratio can be the mean, median, last value or a weighted mean, and it works from only
  three years of history [14]. San Diego State compared a heuristic based on recent terms with CART and random
  forests [15]. AIR work on "student trajectories" does the same per student segment [16]. For SmartSched the
  inputs are the planning list (sections, enrolment, programme, class year) and the published runs, all of
  which already exist.

### 2.2 Forecasting methods for small tabular history

- **Baselines first.** Seasonal naive (repeat the value from the same season last time) is the standard
  benchmark. A model must beat it before its added complexity is worth it, and a MASE ≥ 1 means it does not
  [17, 18]. With one year of data this baseline *is* the method.
- **ETS / Holt-Winters.** These need a few full seasonal cycles to estimate seasonal states. Use damped trend
  without seasonality only for level series of 3 or more terms (for example, total enrolment per programme).
- **Prophet-like decomposition.** Prophet turns on yearly seasonality only with at least 2 years of history and
  weekly seasonality with at least 2 weeks [19]. For SmartSched, borrow the *structure* (trend + season-of-year
  + weekly + holiday effects) as a transparent additive model with explicit calendar regressors (week kind,
  holiday, exam week, add/drop). Do not ship Prophet.
- **Gradient-boosted features.** These need many comparable series and labels; one institution and one year do
  not provide them. Leave this for a multi-year, multi-institution setting.
- **Uncertainty.** Prediction intervals come from empirical residual quantiles on a *time-ordered* split
  (conformal-style). Coverage is only approximate under temporal dependence. With small calibration sets the
  quantile can become infinite or meaningless (n = 15 at α = 0.05) [20, 21, 22]. So:
  - show 80 % intervals, not 95 %;
  - set a minimum width;
  - label any forecast with fewer than 10 calibration points "düşük güven" and fall back to a ±range from
    similar cells (hierarchical pooling: room → building → campus).

### 2.3 Learning soft-constraint weights from accepted or edited plans

- **Inverse optimisation** finds objective weights that make observed decisions (approximately) optimal. Chan,
  Mahmood and Zhu survey the field [23]. Recent MILP variants learn constraints and weights for scheduling-size
  problems with finite-sample guarantees [24]. A 2026 variant warns that standard losses pull the weights
  toward compromise values when the observed choices are suboptimal [25]. For SmartSched, a manual move is a
  pairwise preference: *the edited plan ≻ the solver plan*. Scoring both plans with `solver/evaluate.py` gives
  the vector of per-term differences (ΔΦ). A weight vector *w* agrees with the edit when *w·ΔΦ ≤ 0*.
  Counting agreements per term ("10 of 12 edits accepted 2 more units of capacity waste to keep the building")
  is a robust, explainable inverse-optimisation signal. A full MILP inverse is not needed.
- **Preference and constraint learning.** Naive-Bayes learning of lecturer day and time preferences [26] and
  active learning of soft constraints through partial preference queries [27] show the same pattern as
  SmartSched's priors: learn per-subject preferences, keep hard rules fixed.
- **Bandit-style suggestion acceptance.** Model each suggestion class (attribute × kind × confidence band) as
  Beta-Bernoulli on accept/reject. The posterior mean and its lower bound tell the admin which classes to show
  more of and which threshold to raise [28]. Use this to *rank and calibrate*, never to auto-apply.

### 2.4 Keeping humans in control and KVKK

- Every learned or forecast item is a **suggestion with an explanation and its evidence**, as the existing
  learning cards already are. Profile changes and learned weight changes are **drafts** that an admin approves.
  They are versioned, audited and revertible.
- **KVKK.**
  - Anonymised data is outside the law's scope once it can no longer be linked to a person even when combined
    with other data (KVKK Art. 7 and its regulation, in force since 2018-01-01) [29].
  - Demand and peak models use **aggregates without personal ids**: building, room type, capacity band,
    day/period, week kind.
  - The find-room ledger stores no user id, and small cells (< 5) are suppressed in displays.
  - Person-level habits stay in the existing learning tables, which already store ids only, with
    reset/erasure.
  - No forecast is made per person.

### 2.5 Sources

1. McCollum et al., "The Second International Timetabling Competition: Examination Timetabling Track", tech. report v4.0, QUB, 2007. https://www.eeecs.qub.ac.uk/itc2007/examtrack/report/Exam_Track_TechReportv4.0.pdf
2. Timefold/OptaPlanner docs, "Exam timetabling (ITC 2007 track 1 – Examination)", accessed 2026-10-17. https://docs.timefold.ai/timefold-solver/0.8.x/use-cases-and-examples/exam-timetabling/exam-timetabling · https://optaplanner.org/docs/optaplanner/latest/use-cases-and-examples/exam-timetabling/exam-timetabling.html
3. Müller, Rudová, Müllerová, "Real-world university course timetabling at the International Timetabling Competition 2019", J. Scheduling 28(2), 2024. https://link.springer.com/article/10.1007/s10951-023-00801-w
4. UniTime help, "Examination Timetabling" (conflict definitions, back-to-back, distance), accessed 2026-10-17. https://help.unitime.org/examination-timetabling
5. UniTime, "Examination Timetabling Manual", accessed 2026-10-17. https://help.unitime.org/manuals/examination-timetabling
6. Qu, Burke, McCollum, Merlot, Lee, "A survey of search methodologies and automated system development for examination timetabling", J. Scheduling 12(1):55–89, 2009 (online 2008). https://eprints.nottingham.ac.uk/28266/
7. "Invigilators assignment in practical examination timetabling problems", Int. J. Industrial Engineering 29(3), 2022 (Hacettepe). https://ijietap.journals.publicknowledgeproject.org/index.php/ijie/article/view/6943
8. Three-stage MIP + GA exam timetabling for a 12-department faculty, DergiPark (2026). https://dergipark.org.tr/en/pub/ifede/article/1777317
9. HESA, Estates Management record, "Frequency rate" and "Occupancy rate" definitions. https://www.hesa.ac.uk/collection/c16042/s/FrequencyRate · https://www.hesa.ac.uk/collection/c15042/s/occupancyrate
10. University of Wolverhampton, "Space utilisation" (U = F × O, sector medians), accessed 2026-10-17. https://www.wlv.ac.uk/current-students/central-timetabling-unit/space-audits/space-utilisation
11. Ad Astra, Astra Schedule help, "Capacity analysis" (average weekly and prime-time utilisation, seat fill), accessed 2026-10-17 (now redirects to https://help.adastra.live/hc/en-us/sections/360012191632-Astra-Schedule). https://help.aais.com/Help/75/capacity_analysis.htm
12. Vantage Space glossary, "Workplace analytics & utilization metrics" (peak demand forecast, peak-to-mean ratio). https://www.vantagespace.com/glossary/workplace-analytics-utilization-metrics
13. Untis WebHelp, "Workflow for examinations"; Untis, "WebUntis booking". https://webhelp.untis.at/HTML/WebHelp/uk/untis/wu_workflow.htm · https://www.untis.at/en/products/webuntis/booking
14. R package `enrollcast`, "Project school enrollment with grade progression ratios" (Webster 1970 method). https://rorylawless.r-universe.dev/enrollcast/doc/enrollcast.html
15. Shao, "Course demand prediction" (SDSU, CART / random forest vs heuristic), SEM Quarterly. https://asir.sdsu.edu/Documents/SMGDocs/SEMQ-1002-Shao.pdf
16. AIR Professional File 153 (2021), "Student trajectories for enrollment forecasting, management and planning". https://www.airweb.org/docs/default-source/documents-for-pages/reports-and-publications/professional-file/apf-153-2021-spring_student-trajectories-for-enrollment-forecasting-management-and-planning.pdf
17. Hewamalage, Ackermann, Bergmeir, "Forecast evaluation for data scientists: common pitfalls and best practices", arXiv 2203.10716. https://arxiv.org/pdf/2203.10716
18. Hyndman & Athanasopoulos, *Forecasting: Principles and Practice* (3rd ed.), "Some simple forecasting methods" and "Prediction intervals". https://otexts.com/fpp3/simple-methods.html · https://otexts.com/fpp3/prediction-intervals.html
19. Prophet R docs, `set_auto_seasonalities` (yearly ≥ 2 years, weekly ≥ 2 weeks). https://www.quantargo.com/help/r/latest/packages/prophet/1.0/set_auto_seasonalities
20. Stocker et al., "A gentle introduction to conformal time series forecasting", arXiv 2511.13608 (2025). https://arxiv.org/html/2511.13608v1
21. "Conformal prediction algorithms for time series forecasting: methods and benchmark", arXiv 2601.18509 (2026). https://arxiv.org/html/2601.18509v1
22. MetaHunt vignette, "Conformal prediction with different choices" (small calibration sets → unbounded quantile). https://cran.nics.utk.edu/cran/web/packages/MetaHunt/vignettes/conformal-prediction.html
23. Chan, Mahmood, Zhu, "Inverse optimization: theory and applications", arXiv 2109.03920 (Operations Research, 2025). https://arxiv.org/abs/2109.03920v1
24. Kitaoka, "Inverse mixed-integer programming: learning constraints and objective weights", arXiv 2510.04455 (2025). https://arxiv.org/html/2510.04455v2
25. "Outperformance inverse optimisation", arXiv 2610.09890 (submitted 2026-10-07). https://alphaxiv.org/abs/2610.09890v1
26. "University course timetabling using Bayesian based optimization algorithm", i-JES. https://online-journals.org/index.php/i-jes/article/view/8990
27. Learning Max-CSPs via active constraint acquisition (partial preference queries), CP 2021, LIPIcs. https://drops.dagstuhl.de/opus/volltexte/2021/15345/pdf/LIPIcs-CP-2021-54.pdf
28. Russo, Van Roy, Kazerouni, Osband, Wen, "A tutorial on Thompson sampling", FnTML 11(1), 2018. https://arxiv.org/pdf/1707.02038
29. KVKK, "Kişisel verilerin silinmesi, yok edilmesi veya anonim hale getirilmesi" regulation and guide (summaries: KTÜN, KPMG). https://ktun.edu.tr/Dosyalar/1255/files/Mevzuat_ve_Dokumanlar_HUKUKI_METINLER/Genel%20Politika%20ve%20Prosed%C3%BCrler/imha_rehberi_bc1cb353-ef85-4e58-bb99-3bba31258508.pdf · https://kpmgvergi.com/yayinlar/mali-bultenler/vergi/kisisel-verilerin-silinmesi-yok-edilmesi-veya-anonim-hale-getirilmesi-hakkinda-yonetmelik-taslagi-yayimlandi/282

Fetched pages were read as data. Vendor pages are marketing claims and were not verified. The fpp3 pages did not
render through the fetcher, so the method descriptions above follow the book's well-known content and sources
[17, 18] cite it.

---

## 3. Design for SmartSched

Principles:

- **Real data only.** Every number comes from existing tables (runs, assignments, blocks, bookings, requests,
  exam requests, holidays, weeks) or from the new aggregate ledger. There is no demo path. A model with too
  little data says so in Turkish and English and names what it needs.
- **Suggest, explain, approve, version, revert.** This extends the learning contract of `services/learning.py`
  to profiles, weights, holds and forecasts.
- **Deterministic and cheap.** numpy and pandas are available; no new dependency. Every model is a closed-form
  aggregate that can be recomputed in seconds on the 4-core pod.
- **Fix-first.** Land the two existing gaps that make "adaptive" impossible before building new features:
  server-side default weights (AS-01) and holiday-aware horizons and utilisation (AS-02).

### 3.1 Season calendar and season profiles

**Season calendar** (`services/seasons.py`, new; no table for the calendar itself). A pure function `periods(term)`
returns dated **period segments**, each with a `kind`:

- `LECTURE`, `ADD_DROP`, `MIDTERM`, `EXAM`, `MAKEUP`, `HOLIDAY`, `SUMMER`, `BREAK`.

The segments come from:

- `Week.kind` (existing values);
- `Holiday` rows;
- `TermBookingSettings` / `TermDate`;
- optional admin-defined segments stored on the profile (for example "Ekle-bırak: 1–2. hafta", "Vize haftası:
  8. hafta"), because nothing in the data marks add/drop or midterm weeks today.

The season key is `season_of(term)` (moved from `learning.py` into `seasons.py` and re-exported, so there is one
definition).

**Season profiles** (table `season_profiles`, migration at the next head). Each row has:

- `key`
- `name_tr` and `name_en`
- `applies_to`: a list of `{season: BAHAR|GUZ|YAZ|FINAL|BUT|*, period_kind: LECTURE|EXAM|…|*}`
- `solver_weights`: a sparse override of `DEFAULT_WEIGHTS`
- `booking_overlays`: a list of booking-policy deltas, for example `{"scope": "tag:PC", "max_active_bookings": 2}`
  or an exam-hold mode
- `peak_threshold_pct`: default 85
- `status`: `draft | active | retired`
- `version`, `parent_id`
- `created_by`, `approved_by`, `approved_at`
- `explanation` (`tr`/`en`)
- `evidence`: the numbers that motivated a learned draft

Rules:

- **Resolution.** For a run, `seasons.effective_weights(term, run)` merges the layers in this order, later layers
  winning: `DEFAULT_WEIGHTS` < settings `solver_weights` < active profile for (season, dominant period kind of the
  horizon) < `run.params.weights`. The bridge stores the merged weights and their sources in
  `run.stats["weights_effective"]` and `run.stats["profile"]` so the run page can say which profile shaped the
  run.
- **Booking enforcement.** `booking_policies.enforce` gains one overlay step. For the booking's date, the active
  profile's overlays for that period kind are applied as *additional* rules with `source = "season_profile"`. The
  "Neden?" text names the profile and the period ("Final haftası profili: PC laboratuvarlarında kişi başı en çok 2
  etkin rezervasyon").
- **Built-in profiles.** Two read-only profiles are shipped:
  - `standard`: every season and period, no overrides.
  - `exam_week`: EXAM/MAKEUP, exam hold mode = the current exam-period setting.

  The universal empty install therefore behaves exactly as today. Gracious gets **draft** profiles proposed from
  its history (§3.3); they become active only after an admin's approval.
- **Versioning.** Editing an active profile creates a new draft version. Activating it retires the previous one,
  and "Geri al" re-activates the parent. Every change is audited (`season_profile.*`).

### 3.2 Peak-hour model

`services/peaks.py` (new; reads `utilisation.build_scope`). The model works in four steps:

1. **Cells.** For each historical term and period kind: (weekday, period, group), where group is building, room
   type or capacity band. The measure in each cell is the occupied share of usable room-periods (frequency) and
   the seat fill (occupancy), from published runs, imported grid assignments, blocks and bookings. Holiday dates
   are removed from the denominator (AS-02).
2. **Estimate.** The shrunken mean `p̂ = (n·x̄ + k·p_parent)/(n + k)`, with the parent being building → campus and
   k = 4 weeks. The 80 % range comes from the week-to-week empirical quantiles.
3. **Season transfer.** Period and day *shape* comes from all seasons, since its correlation is 0.995 across
   seasons. The *level* comes from the same season when it exists, otherwise from the requests of the target term.
4. **Output.** Peak cells are those with `p̂ ≥ peak_threshold_pct`. On gracious this gives P3–P5 and P7–P9 on
   Monday to Thursday, with PC labs and the large amphitheatres expected to be the tightest groups.

Uses:

- **Warn (planner).** Before a solve, a data issue `peak_pressure` lists the peak cells where the term's
  *fixed-time* requests alone already need more than X % of the suitable rooms. Example: "Çarşamba 4. ders:
  bilgisayar laboratuvarı isteyen 6 ders, uygun 4 oda". The issue goes into `services/data_issues.py` (not into
  the read-only `precheck.py`).
- **Smooth (solver, opt-in).** A new soft constraint `peak_smoothing` charges one unit per room-period used
  above the threshold in a (day, period, group) cell. It affects only events whose day or start is flexible
  (`allowed_days`, flexible start), so the department's fixed times are never moved. Its weight comes from the
  profile and defaults to 0 (off) until the backtest in AS-08 shows that no placement is lost.
- **Steer bookings.** Find-room and quick reserve show a "Yoğun saat" chip on peak cells and offer the nearest
  off-peak alternative. A profile overlay can cap bookings at peak (draft, approved by an admin).

### 3.3 Learning loop from history

What is learned, by layer:

| Layer | Learned from | Output | Applied how |
|---|---|---|---|
| Person and course habits (exists) | `learned_observations` | Priors and suggestion cards | Accept → soft LEARNED rule (unchanged) |
| Suggestion calibration (new) | `suggestion_feedback` accept/reject per class (attribute × kind × confidence band) | Beta(1+acc, 1+rej) posterior; recommended `MIN_CONFIDENCE` per class and display order | Draft "öğrenme ayarı" change; an admin approves it |
| Solver weights (new) | Manual moves and locks vs the parent run (`assignments.origin = MANUAL/AI_EDIT`, the planning audit once the TODO at `learning_extract.py:573` is done), scored by `solver/evaluate.py` | Per-term agreement counts; a proposed weight ratio change | Draft season-profile version with an explanation; an admin approves it |
| Peaks and demand (new) | Occupancy history + the find-room ledger | Peak cells, demand curves | Warnings, chips, draft overlays |
| Exam load (new) | Exam lists and exam runs of earlier terms | Seat demand per day and slot, cohort conflicts | Advice and draft holds |

**Review, versioning and revert.** Each nightly or manual refresh writes a `learning_versions` row with:

- the term;
- counts of observations, priors and suggestible priors;
- a checksum;
- the diff against the previous version: new, dropped and changed suggestions.

The admin page lists the versions. "Bu sürüme dön" restores a prior snapshot, because prior rows are copied into
`learned_prior_snapshots` keyed by version (compact JSON). Accepted rules are never touched by a revert; they keep
their own restore. A nightly refresh (03:15 Istanbul) is added beside the purge job. It is on by default for the
active term, and it only changes suggestions, never rules.

**Explanation.** Every learned weight or profile draft carries:

- `explanation.tr` and `explanation.en`, for example: "Son 2 dönemde 12 elle taşımanın 10'unda bina tercihi, oda
  israfından önce geldi. Öneri: building_preference 5 → 8.";
- `evidence`: run ids, counts and the before → after score deltas, with no personal names (§2.4).

### 3.4 Predictions

All predictions live in `services/forecast.py` (new) and are exposed as `GET /analytics/forecast/*`. Each one
returns `{value, lo80, hi80, method, basis, confidence: high|medium|low|none, needs}`, where `needs` is a TR/EN
sentence for cold start.

1. **Next-term room demand per building × weekday × band × feature (tag) × capacity band.**
   - If the target term already has a planning list, demand is *computed*, not forecast: the requests' room
     needs (enrolment → capacity band, tags, building, fixed times). The method is labelled `requests`.
   - Otherwise the method is `seasonal_naive`: the same season's last published term, scaled by the
     cohort-progression ratio of sections and enrolment per programme (median of the available transitions;
     with one year, ratio = 1 and the label says so), with the cross-season period shape from §3.2.
   - Intervals come from the backtest residual quantiles of the same method and cell group. With fewer than 10
     calibration points, confidence is `low` and the interval falls back to the ±range of the parent group.
2. **Exam-period booking demand.** Bookings and blocks per day in EXAM/MAKEUP weeks of earlier terms, relative
   to lecture weeks of the same term (an "exam-week multiplier" per room group). Cold start (no bookings in exam
   weeks) returns `confidence: none` with `needs: "En az bir sınav döneminin rezervasyon geçmişi"`. The
   *structural* part is always available from the exam list: seats needed per day and slot, and the rooms the
   exam timetable occupies.
3. **Capacity-shortfall forecast.** Per peak cell and group: demand (1) against the supply of suitable rooms
   (capacity ≥ band, tags) gives the shortfall, `P(shortfall > 0)` from the interval, and the list of requests
   that would compete. For exams: seats per slot against `exam_capacity` per slot.
4. **What-if.** `POST /analytics/forecast/what-if` takes `{enrolment_pct: +10, scope: all|faculty|program,
   rooms_closed: [...], extra_sections: n}`.
   - It recomputes room fit for every request of the term. A class has no fit when no bookable room with
     `capacity ≥ enrolment × (1 + x)` and the needed tags exists, and the shortfall per peak cell is
     recalculated.
   - `solve: true` optionally queues a **draft child run** (never activated, labelled "Senaryo: +10 %
     kontenjan") through the existing run pipeline with scaled sizes. The result is then comparable in
     `/runs/compare`.

   This is real computation on real requests; nothing is mocked.

### 3.5 Exams and their interaction with the class plan and bookings

- **Exam-week class plan.** In EXAM/MAKEUP weeks there are no lecture meetings. `horizon_weeks` for COURSE runs
  drops weeks of kind HOLIDAY, EXAM and MAKEUP (AS-02), so those weeks are free for exams and bookings.
- **Midterms inside lecture weeks.** An exam run sees its own term's blocks and the confirmed bookings, but not
  the class plan (no published COURSE run is read in the exam branch, `solver_bridge.py:824-935`; the gracious
  Final is a separate term). Exams dated inside the lecture weeks of a term (midterms, "early finals",
  `solver_bridge.py:847-850`) can therefore take a room a class holds. AS-12 adds the published course
  assignments on those dates as blocks for exam runs, plus the reverse warning on the course side.
- **Slot-level exam holds for bookings.** The new exam hold mode `slots` replaces the whole-week closure. Only
  the room-periods that the active exam run uses, plus a buffer of `n` periods before and after, are closed or
  turned into requests; the rest of the exam rooms stay bookable. The draft is computed from the exam run and
  shown with the number of room-periods it frees against the whole-week closure, and an admin approves it.
- **Exam date advisor** (no change to the dates themselves). It checks the exam list against:
  - cohort exams per day > 2;
  - back-to-back exams for a cohort and for an instructor;
  - large exams in the last 2 days (front load);
  - the seat peak per slot against `exam_capacity`.

  It then suggests date or slot moves ranked by the conflict reduction. On Final 2026 the advisor flags Wed
  3 June (126 exam-list rows; 98 sittings since the AS20-F13 re-baseline) and offers moves into Fri 12 June (23). Each suggestion is a card the coordinator accepts
  by editing the request; nothing is changed automatically.
- **Exam date scheduling (later, AS-19).** Make `ExamRequest` date and slot optional, with
  `allowed_dates`/slots, and let CP-SAT choose them using `exam_gap`, `max_exams_per_day`, a new `front_load`
  rule and a `seat_peak` rule. Without student registrations (W3E-21), cohorts are programme + class year
  (`class_years`), as they are today.
- **Invigilation.** Invigilation has no seasonal gap of its own. The forecast seat load per slot (3.4-3) feeds
  the expected invigilator need, `Σ ceil(seated/students_per_invigilator)` per slot, against the pool size per
  day, as an early warning before an invigilation plan is run.

### 3.6 Admin UI surfaces (existing app)

| Surface | Route / component | Contents |
|---|---|---|
| Season calendar and profiles | `/admin/weeks` (existing week-kind editor) gains a "Dönem profilleri" section, plus a new `components/seasons/**` | Period segments per term (add/drop, midterm, exam, holiday), profiles with versions, diff, approve, revert |
| Peak hours | `/analytics/heatmap` gains a "Yoğun saatler" view (new tab, `components/analytics/peaks-*.tsx`) | Peak cells with ranges, groups, per-season comparison, CSV |
| Forecast and what-if | New `/analytics/forecast` (`components/analytics/forecast-*.tsx`) | Demand by building, band and feature with 80 % ranges, confidence badge, `needs` text, what-if form → draft run link |
| Learning versions and calibration | `/moderation/learning` (existing `LearningMemoryPanel`) gains "Sürümler" and "Ayar önerileri" | Version list, diff, revert; calibration drafts |
| Run provenance | `/runs/[id]` header | "Profil: Güz – ders dönemi v2 · ağırlıklar" with a link to the profile |
| Planner warnings | Existing data-issues list on `/generate` and `/runs/[id]` | `peak_pressure`, `exam_load` items |
| Exam advisor and holds | `/exams` (existing) gains an "Öneriler" panel; the exam hold mode lives in the booking-policies admin (`components/policies/policies-admin.tsx`) | Advisor cards; `slots` mode with freed room-periods |
| Booking hints | `/find-room` and `/reserve` | "Yoğun saat" chip and an off-peak alternative |

### 3.7 Data needed and cold start

| Need | Source | Universal (empty) | Gracious |
|---|---|---|---|
| Period kinds | `weeks.kind`, `holidays`, profile segments | Admin marks them; standard profile until then | Bahar grid sheets (LECTURE ×15, SUMMER, EXAM ×2, MAKEUP) |
| Occupancy history | Published runs, IMPORT assignments, blocks, bookings | None; peaks show "Yayımlanmış bir dönem gerekli" | Bahar 15 weeks, Güz 2 weeks, Final 3 weeks |
| Requests | `meeting_requests`, `exam_requests` | From onboarding (intake) → request-driven demand works from day 1 | Bahar 1,529, Güz 1,037, Final 921 rows |
| Find-room demand | New aggregate ledger | Starts at 0, grows | Starts at 0 (no CRBS bookings in the fixtures) |
| Edits | `assignments.origin`, planning audit | None | Moderation edits on the stack |
| Suggestion decisions | `suggestion_feedback` | None | Grows from use |

Every endpoint answers on an empty install with `confidence: "none"` and a `needs` sentence. Nothing is faked, and
no tab is hidden.

### 3.8 Evaluation (backtests on tests/fixtures)

All backtests live in `app/services/backtest.py` and `python -m app.cli backtest adaptive [--json]`. They are
asserted in `tests/test_as_backtest_*.py` on the real fixtures, using the session-cached parsed workbooks from
`tests/conftest.py`.

| ID | Backtest | Metric (target) | Baseline measured 2026-10-17 |
|---|---|---|---|
| B1 | Weekly course room-periods: fit Bahar weeks 1–8, forecast 9–15 | MAPE ≤ 2 %, MASE vs naive ≤ 1.0 | Mean model 0.70 %, naive 0.76 % |
| B2 | Peak profile transfer Bahar → Güz (18 periods, weekday share) | Pearson ≥ 0.95; the top-4 peak periods match ≥ 3/4 | 0.995; top-4 {4, 8, 5, 3} vs {4, 8, 3, 5} |
| B3 | Building × band demand Güz weeks 1–2 forecast from Bahar shape × Güz request level | WAPE ≤ 15 % per building; 80 % interval coverage reported (target ≥ 70 %) | To be measured in AS-07 |
| B4 | Learning holdout: priors from Bahar only → building suggestions vs Güz definitive buildings | precision@suggestible ≥ 0.8; no cross-season room or tag suggestion | To be measured in AS-13 (the T-R1-40 tests are the base) |
| B5 | What-if +10 % enrolment on Bahar requests | Count of classes with no fitting room and the shortfall per peak cell; deterministic; draft run never active | To be measured in AS-10 |
| B6 | Exam advisor on Final 2026 | Peak-day exams 126 → after accepting the top-N suggestions ≤ 100; cohort days with > 2 exams reported. **Re-baselined 2026-10-18 (AS20-F13, FIX-G), unit = sittings (a merge group once):** 98 → ≤ 78 (the same 79 %); B6a peak/mean 1.67 ± 0.01. Measured: 91 of 122 moves bring 98 → 78, clashes 104 → 0, cohort days over 21 → 0, 0 new conflicts | Peak/mean 1.86 (rows); 1.667 (sittings) |
| B7 | Slot-level exam holds on Final 2026 | Room-periods freed vs the whole-week closure > 0, with no exam room-period bookable | To be measured in AS-11 |
| B8 | Peak smoothing on (flexible-day subset of Bahar) | Hard score unchanged, placed count unchanged, load above the threshold ≤ off | To be measured in AS-08 |
| B9 | Weight learning on synthetic edits generated with known weights | Kendall τ of recovered weight ratios ≥ 0.8 | To be measured in AS-14 |

### 3.9 Risks

- **One year of history.** Most forecast intervals on gracious will be `low` confidence at first. That is the
  honest output. The request-driven method carries real value from the first day.
- **Little room to move classes.** Departments fix most times, so smoothing moves little. The value is in
  warnings, booking steering and exam advice; say so in the UI.
- **Profiles that change weights without notice** would surprise planners. Every run therefore shows its profile
  and weights, and drafts need approval.
- **KVKK.** The ledger and the forecasts are aggregate only; the existing learning reset and erasure cover the
  person-level layer.
