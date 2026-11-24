# Presentation Guidelines: Space Geodesy Project (ETH Zurich, IGP)

This file tells Claude Code how to build the final project presentation. Follow it strictly.
Source: "Space Geodesy project introduction" slides (Shuyin Mao, IGP, 17.09.2026).

## 1. Project context

- Course: Space Geodesy, Institute of Geodesy and Photogrammetry, ETH Zurich
- Group project (teams of 4 to 6 people)
- Topic: magma inflow and inflation cycles at Svartsengi / Sundhnúkur (Reykjanes Peninsula, Iceland), derived from GNSS position time series and InSAR
- InSAR source: COMET LiCSAR / LiCSBAS time series, starting 2020
- GNSS source: station position time series (e.g. Nevada Geodetic Laboratory); confirm the final source from the repo
- Focus is GNSS and InSAR processing and time series analysis. No geological or magma flow modelling; interpret deformation descriptively.
- The presentation must state **whether the research plan was kept** and **which challenges came up**. This is explicitly asked for by the course.

## 2. Hard requirements (from the course)

| Item | Requirement |
|---|---|
| Date | **15.12.2026**, presented in class |
| Slides | Submit slides by email (soja@ethz.ch, shumao@ethz.ch) |
| Duration | **15 min talk** + 10 min discussion |
| Slide count | About 1 slide per minute, so **12 to 15 content slides** plus title and backup slides |
| Weight | Presentation = 25% of the project grade |

## 3. Required structure

Cover these parts, in this order:

1. **Introduction / scientific background**
2. **Research question / problem**
3. **Data**
4. **Methods**
5. **Results**
6. **Discussion** (include: was the research plan kept, challenges faced)
7. **Summary & outlook**

Suggested slide plan (about 15 min):

| # | Slide | Time |
|---|---|---|
| 1 | Title (project title, team names, date, course) | 0.5 min |
| 2 | Motivation: Reykjanes eruptions since 2021, why monitor Svartsengi | 1 min |
| 3 | Background: GNSS and InSAR for volcano deformation | 1 min |
| 4 | Research question (one sentence, large font) | 0.5 min |
| 5 | Study area map with GNSS stations and InSAR frames | 1 min |
| 6 | Data overview (stations, frames, time spans, providers) | 1 min |
| 7 | Processing chain (flow diagram from download to results) | 1.5 min |
| 8 to 11 | Results: one key finding per slide (deformation map, GNSS time series with cycles, GNSS vs InSAR comparison, rates with uncertainties) | 5 min |
| 12 | Discussion: interpretation, error sources, limitations | 1.5 min |
| 13 | Research plan vs reality, challenges | 1 min |
| 14 | Summary & outlook (3 to 5 key points) | 1 min |
| 15 | Thank you / questions | |
| Backup | Extra figures, parameter settings, extra stations for the discussion | |

Adjust to the actual results in the repo; the number of results slides follows the number of key findings.

## 4. Best practices (from the course)

- **Start by defining 3 to 5 main points.** Write them down first; every slide must support one of them.
- **One idea per slide.** The slide title states the message as a short sentence ("Uplift resumes within days after each eruption"), not a topic label ("Results").
- **Consistent formats and style:** same fonts, colors, colormaps, axis styles and units on every slide.
- **Highlight key points:** one bold number or takeaway per results slide.
- **Readable graphics:** large axis labels and tick labels (at least 16 to 18 pt equivalent on the slide), thick lines, colorblind friendly colormaps, units on every axis, no tiny multi panel figures. Re-export figures for slides; do not reuse paper figures if labels become unreadable.
- **About 1 slide per minute.**

## 5. Slide style rules

- Little text: keywords and short phrases, no full paragraphs. Maximum about 5 bullets per slide.
- No first person in written slide text; use impersonal phrasing. (Speaking notes may use "we".)
- No hyphens or dashes as punctuation in slide text; professional but simple vocabulary.
- Numbers with units and uncertainties (e.g. "8.2 ± 0.4 mm/day").
- Every figure from external sources is credited on the slide (small source line). Data providers (COMET LiCSAR/LiCSBAS, NGL) credited on the data slide.
- Slide numbers on every slide (helps during the discussion).
- 16:9 format.
- Keep all numbers consistent with the final report.

## 6. Output and tooling

- If no format is specified in the repo, ask which tool to use (e.g. LaTeX Beamer with a flat structure: one `slides.tex`, one `figures/` folder; or PowerPoint).
- Export a PDF for submission.
- Write short speaker notes per slide (2 to 4 sentences, with timing) in a separate `speaker_notes.md`, so the talk can be split between team members.
- Plan who presents which part; mark the speaker per section in the notes.

## 7. Prepare for the 10 min discussion

List likely questions and short answers in `speaker_notes.md`, for example:
- How was the InSAR reference point chosen and does it move?
- How do GNSS and InSAR compare in the line of sight, and why do they differ?
- How were atmospheric delays and unwrapping errors handled?
- What limits the uncertainty of the estimated rates?
- What would be done with more time?

## 8. Before finishing

- [ ] 3 to 5 main points defined and each slide supports one
- [ ] All seven parts covered, in order
- [ ] Research plan vs reality and challenges addressed
- [ ] 12 to 15 content slides, rehearsed at 15 min or less
- [ ] All figures readable from the back of the room
- [ ] Consistent style, slide numbers, sources credited
- [ ] Numbers match the report
- [ ] PDF exported and ready to email
