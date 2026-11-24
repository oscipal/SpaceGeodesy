# Report Guidelines: Space Geodesy Project (ETH Zurich, IGP)

This file tells Claude Code how to write the final project report. Follow it strictly.
Source: "Space Geodesy project introduction" slides (Shuyin Mao, IGP, 17.09.2026).

## 1. Project context

- Course: Space Geodesy, Institute of Geodesy and Photogrammetry, ETH Zurich
- Group project (teams of 4 to 6 people)
- Topic: magma inflow and inflation cycles at Svartsengi / Sundhnúkur (Reykjanes Peninsula, Iceland), derived from GNSS position time series and InSAR
- InSAR source: COMET LiCSAR / LiCSBAS time series, starting 2020 (includes earlier Svartsengi cycles)
- GNSS source: station position time series (e.g. Nevada Geodetic Laboratory, geodesy.unr.edu); confirm the final source from the repo
- Methodological focus: GNSS and InSAR processing and time series analysis. Do NOT build geological or magma flow models; the course assumes no prior knowledge there. Interpret deformation descriptively (uplift, subsidence, rates, timing of cycles), not with physical source models.
- The report must reflect what was promised in the submitted research plan. If the analysis deviated from the plan, say so briefly and explain why.

## 2. Hard requirements (from the course)

| Item | Requirement |
|---|---|
| Format | Short proceedings paper |
| Length | **4 pages** (references count separately unless tutors say otherwise; check Moodle) |
| Deadline | **17.12.2026**, by email to soja@ethz.ch and shumao@ethz.ch |
| Extra sheet | Separate page with **working hours and individual contributions** of each group member (required for groups; not part of the 4 pages) |
| Weight | Report = 50% of the project grade (research plan 25%, presentation 25%) |

Exact template, font size and margins are not given in the slides. If no template is in the repo, ask before choosing one. Never shrink fonts or margins to fit the page limit; cut text instead.

## 3. Required structure

Use exactly these sections, in this order:

1. **Abstract**
2. **Introduction**
3. **Data**
4. **Methods**
5. **Results**
6. **Discussion**
7. **Conclusions and outlook**
8. **References**

(The slides list Methods before Data; for this project, Data first reads more naturally because the methods depend on the LiCSBAS and GNSS products. Either order is acceptable.)

The report must answer four questions, one per block:

| Question | Section(s) |
|---|---|
| Why did we start? | Introduction |
| What did we do? | Data, Methods |
| What did we find? | Results |
| What does it mean? | Discussion |

Guiding principle from the course:
> As brief as possible, without sacrificing clarity. As clear as possible, without sacrificing accuracy.

## 4. Content guidance per section

**Abstract** (about 150 words): context, research question, data and methods in one sentence each, key quantitative results, main conclusion.

**Introduction**: short scientific background on the Reykjanes / Svartsengi activity and on why space geodesy (GNSS, InSAR) is suited to monitor it. Brief literature context. End with a clearly stated, narrow research question.

**Data**: GNSS stations used (names, location, time span, reference frame, product provider). InSAR: LiCSAR frames (ascending / descending), time span, number of epochs, LiCSBAS settings that matter. State that combined, already processed products were used (the course recommends combined products over raw observations).

**Methods**: processing chain from downloaded products to results: time series cleaning, outlier handling, reference point choice, conversion of LOS to vertical / east components if done, GNSS and InSAR comparison at station locations, rate or cycle estimation. Give equations only where needed. Describe the automated pipeline only at the level needed for reproducibility.

**Results**: figures and numbers only, no interpretation. Include uncertainties for every estimated quantity (rates, offsets, amplitudes). Typical figures: map of deformation field, GNSS time series with event markers, GNSS vs InSAR comparison.

**Discussion**: what the results mean, agreement and disagreement between GNSS and InSAR, error sources (atmosphere, unwrapping errors, reference point, coherence loss from new lava flows), limitations, comparison with published values. No magma flow modelling.

**Conclusions and outlook**: direct answer to the research question, two or three key findings, realistic next steps.

**References**: consistent citation style (author year or numeric, one style throughout). Cite data providers (COMET LiCSAR/LiCSBAS, NGL) and software. Only cite sources that actually exist and that are verified; never invent references.

## 5. Writing style rules

- No first person ("we", "our", "I"). Use passive or impersonal constructions ("The time series were detrended", "This study shows").
- No hyphens or dashes in prose used as punctuation or for compound constructions where avoidable (write "time series analysis", "line of sight", not "time-series-analysis"; do not use em dashes or en dashes as sentence breaks). Standard technical names (e.g. "Sentinel 1" style names, ISO dates) may keep their official form.
- Professional but simple scientific vocabulary. Short sentences. No filler, no marketing language.
- Be specific: numbers with units and uncertainties (e.g. "uplift rate of 8.2 ± 0.4 mm/day").
- Every figure and table is referenced in the text, has a self-explanatory caption and readable labels (axis units, legend, station names).
- Consistent units, notation and terminology throughout.

## 6. LaTeX setup

- Flat file structure: one `main.tex`, one `references.bib`, figures in the same folder or a single `figures/` folder. No `\input` chains across many subfolders.
- Compile with `latexmk -pdf main.tex` and check that the result is at most 4 pages before references.
- Figures as vector PDF where possible, otherwise PNG at 300 dpi.
- Keep the working hours / contributions sheet as a separate file (`contributions.tex` compiled to its own PDF), not inside the 4 pages.

## 7. Before finishing

- [ ] Page count is 4 pages or less (excluding references and contributions sheet)
- [ ] All eight sections present, in order
- [ ] Research question stated in the Introduction and answered in the Conclusions
- [ ] Every number in the text matches the figures, tables and code output
- [ ] All references real and complete; data providers cited
- [ ] No first person, no prose hyphens or dashes
- [ ] Contributions and working hours sheet prepared
