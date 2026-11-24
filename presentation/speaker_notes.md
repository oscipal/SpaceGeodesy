# Speaker notes: Svartsengi InSAR and GNSS (15 min talk + 10 min discussion)

Presentation on 15.12.2026. Slides: `svartsengi_presentation.pptx` / `.pdf`.
Rebuild: `python presentation/build_slides.py` (figures: `python scripts/make_slide_figures.py`).
The same notes are stored in the notes field of each slide. All numbers are the ones in the report
(`report/main.tex`, Table 1) and in `results/cycles/` (Stage 7, `scripts/cycles.py`).

## Main points (one answer per research question)

1. **Uplift rate:** it fell in steps, from 11.4 ± 1.2 mm/day (HS02, November 2023) to about 4 mm/day in 2024 and 2.6 mm/day in 2025. Since the last eruption it has declined continuously, to 0.39 ± 0.05 mm/day at SENG in August to October 2026.
2. **InSAR and GNSS:** during inflation they agree within 15 to 20 mm per period and 0.18 mm/day in rate. InSAR is about 5 to 7 % lower. Across the dike intrusions InSAR fails next to the dikes (350 to 760 mm misfit).
3. **Uplift pattern:** since March 2024, including the pause, the uplift centre moved by less than 90 m. The extent (3.5 × 2.6 km) and the shape (correlation 0.97 to 0.98) are unchanged.

No source model and no volumes: these would need assumptions (source depth, shape, elastic parameters) that the data do not constrain.

## Speaker split

| Part | Slides | Speaker | Time |
|---|---|---|---|
| Title, motivation, background, questions | 1 to 4 | [Speaker 1] | 3 min |
| Study area, data, methods | 5 to 7 | [Speaker 2] | 3.5 min |
| Question 1: uplift rate | 8 to 10 | [Speaker 3] | 2.5 min |
| Question 2: InSAR and GNSS | 11 to 13 | [Speaker 4] | 2.5 min |
| Question 3: pattern; plan vs reality; summary | 14 to 19 | [Speaker 5] | 3.5 min |

Slides 20 to 22 are backup (rates table, SKSH series, LiCSBAS settings).

## Slide by slide

1. **Title** (0.5 min). Introduce the team and the topic: the inflation cycles at Svartsengi since 2023 and the current pause, measured with Sentinel-1 InSAR and GNSS.
2. **Eleven dike intrusions since November 2023, but no eruption since August 2025** (1 min).
   - Svartsengi already inflated in 2020 and 2022 without erupting.
   - Since November 2023: magma collects, the ground rises, a dike breaks out towards Sundhnúkur, and the ground drops within hours.
   - 11 intrusions and 9 eruptions until July 2025; since August 2025 none, although the ground keeps rising.
   - Possible explanations: a declining supply or a changed stress state. Both would show in the rate and the pattern.
3. **GNSS and InSAR complement each other** (1 min). GNSS: daily, 3D, but at points only. InSAR: the whole area, but along the line of sight and every 6 or 12 days. Two geometries give vertical and east.
4. **Three questions from the research plan** (0.5 min). Read the three questions. The results follow in this order.
5. **Study area** (1 min). The two frames, the processed area, and the InSAR reference at Straumsvík (11 km from REYK). The GNSS stations around the centre: only SKSH and SENG cover 2020 to 2026.
6. **Data** (1 min). The descending frame ends on 3 February 2026, the last LiCSAR product, so vertical and east end there. Ascending continues to September 2026. GNSS: most stations to May 2026, SENG to October 2026.
7. **Processing chain** (1.5 min).
   - InSAR: LiCSBAS (GACOS, quality and loop checks, inversion, mask), then decomposition.
   - GNSS: relative to REYK, antenna offsets removed. Outliers are removed against a 15 day running median (5 robust σ, not in the first 10 days after an event).
   - Rates: a line per inflation period, with σ corrected for autocorrelated residuals.
   - Pattern: an elliptical Gaussian fitted to each cycle's uplift map.
8. **Divider: question 1.**
9. **Saw tooth at the centre** (1 min).
   - Small uplift in 2020 and 2022.
   - From November 2023: steady uplift, then a drop at every event. Each cycle from March 2024 added 235 to 325 mm.
   - After July 2025 there is no drop any more: +325 ± 20 mm until February 2026.
10. **The uplift rate fell in steps, and keeps falling during the pause** (1.5 min).
    - About 11 mm/day right after the first intrusion, about 6 in early 2024, about 4 through 2024, and about 2.6 in 2025.
    - In the pause the rate no longer stays constant. It falls window by window: 2.5 → 1.6 → 1.0 → 0.76 mm/day at HS02, and 0.39 ± 0.05 at SENG in autumn 2026.
    - InSAR shows the same decline.
    - HS02 (0.8 km) rises up to 27 % faster than SENG (2.2 km), so compare rates only at the same point.
11. **Divider: question 2.**
12. **During inflation InSAR agrees with GNSS within 15 to 20 mm** (1 min).
    - 1:1 scatter: RMS 16 mm ascending, 15 mm descending, 20 mm vertical, 80 to 86 pairs.
    - Rates per period: InSAR is 0.18 mm/day (5 to 7 %) lower at HS02 and SENG. The largest difference is 0.74 ± 0.37 mm/day (HS02, May to August 2024).
13. **Across the dike intrusions InSAR fails near the dikes** (1.5 min).
    - Metre scale gradients cannot be unwrapped over 50 to 110 m pixels, and new lava removes coherence.
    - The 10 November 2023 step is wrong by 350 to 760 mm at 5 stations. The RMS over all events is 57 to 93 mm.
    - The loop closure fix reduced the descending misfit from 87 to 20 mm.
    - The 12 day revisit was too coarse for the short cycles of late 2023 and early 2024, so GNSS is needed there.
14. **Divider: question 3.**
15. **Same pattern in 2020 and 2024, ten times larger** (1 min). Note the two colour scales. Grey pixels are masked (new lava).
16. **Since March 2024 the uplift centre has not moved by more than 90 m** (1.5 min).
    - Since March 2024, including the pause to February 2026: all centres lie within 89 m of their mean (1σ of 50 to 90 m). Axes are 3.41 to 3.53 by 2.56 to 2.76 km, azimuth 58 to 62°, shape correlation 0.97 to 0.98.
    - 2020 and 2022 lie 0.3 to 0.9 km away, mostly to the south west. But the uplift was ten times smaller, so these fits are more sensitive to noise.
    - Open symbols: November 2023 (24 days directly after the first dike) and April 2025 (starts 2 days after a dike that propagated north east).
    - A stable surface pattern is necessary, but not sufficient, for a stable source.
17. **Plan vs reality** (1 min).
    - No dedicated Sentinel-1 processing.
    - Descending loop threshold changed.
    - Reference at least 24 km away, with the processed area extended.
    - The descending frame ends in February 2026.
    - Uplift centre taken from the data.
    - Challenges: unwrapping, revisit, memory, no local tools (Docker).
18. **Summary** (1 min). One answer per question (see the main points). Outlook: descending data after February 2026, offset tracking at the dikes, and source modelling to test whether the source itself is stable.
19. **Thank you.**

## Likely questions

**Why do you not compare with the published magma volumes?**
Converting uplift into volume needs a source model: depth, shape and Poisson's ratio. The plan excludes source modelling, and these parameters cannot be determined from our data. So rates are compared only qualitatively with Parks et al. (2025): their inflow also decreased with time.

**Does the declining rate mean the magma supply is declining?**
Not necessarily. Two explanations fit the data equally well:
- If the inflow depends on the pressure difference to a deeper region, the rate falls by itself while the pressure beneath Svartsengi keeps rising without an eruption.
- A declining deep supply would look the same.

Surface rates alone cannot separate the two.

**How are the rate uncertainties computed?**
The standard error of the line slope, from the residuals, multiplied by sqrt((1+ρ)/(1−ρ)). Here ρ is the lag one autocorrelation of the residuals, because daily GNSS noise is correlated and the uplift within a period is not exactly linear. Motion of the reference station REYK (vertical scatter 6.8 mm) is not included.

**Why are some periods missing in InSAR?**
Periods shorter than 20 days, or with fewer than four InSAR epochs, get no rate. In late 2023 and early 2024 the 12 day revisit gave only two or three epochs per cycle.

**How reliable is the centre of the uplift?**
- The Gaussian fit errors are scaled for spatially correlated noise. The correlation length is measured from each residual map (0.8 to 1.6 km), and the number of independent pixels is area / (πL²). This gives 1σ of 50 to 90 m.
- The centre depends on the fitted surface shape. That shape is the same for all cycles, so the comparison between cycles is fair.

**How was the InSAR reference chosen, and does it move?**
It was chosen automatically: the most coherent 5 × 5 pixel window at least 24 km from the uplift centre, outside the active areas. The result is Straumsvík, 27 km from the centre. GNSS is referenced to REYK, 11 km away, which shows 6.8 mm vertical scatter and steps below 6 mm at the events.

**How were GNSS outliers handled?**
- Each day is compared with a 15 day running median. A day is removed if it lies more than five robust standard deviations away (1.4826 × MAD).
- The series is split at every dike and eruption, and the first 10 days after each event are not tested, so that real fast motion is kept.
- This removed 0.1 to 5 % of the days per station and component.

**Why neglect the north component?**
Two near polar geometries are almost insensitive to north motion. It matters mostly near the dikes, where the horizontal motion is large.

**What would be done with more time?**
- Descending data after February 2026, which would give vertical rates for the whole pause.
- Dedicated processing or offset tracking for the dike steps.
- Source modelling to test whether the source itself stayed the same.
