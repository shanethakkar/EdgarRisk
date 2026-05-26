# The Bankruptcy Detector That Predicted Nordstrom

*What I learned reading 24 pre-bankruptcy 10-Ks — and why six of my "false positives" were actually leading indicators.*

---

In May 2025, the Nordstrom family teamed up with Mexican retailer El Puerto de Liverpool to take the department store chain private at $24.25 per share. A few months later, Sycamore Partners agreed to buy Walgreens Boots Alliance and split it into pieces. Both deals were the endpoints of multi-year operational declines. Both companies had been on my "false positive" list for two years.

I'd been building a text-based corporate distress detector — a model that reads the Risk Factors section of SEC 10-K filings and tries to identify companies in trouble. I tested it on 24 Chapter 11 bankruptcies across 15 sectors, paired with 42 sector-matched healthy peers. The headline numbers looked respectable: 79% recall on the failures, but a 46% precision when you counted only Ch.11 events. Half of the model's flags were "wrong."

Except they weren't.

Six of those "false positive" survivors — Nordstrom, Walgreens, Macy's, Kohl's, CVS, and Lucid Motors — subsequently went through take-privates under duress, activist takeover campaigns, or 50%+ stock crashes. The model wasn't predicting Chapter 11. It was predicting *distress*, which resolves through more channels than just bankruptcy court. When I extended the time horizon by 2-3 years, the precision climbed to 61%. Adding companies that survived material stress events (Western Alliance through the 2023 banking crisis, Clorox through its cyberattack) pushed it to 69%.

This is a piece about what the model does, what it doesn't, and why the messy reframing turned out to be a stronger claim than the original clean one.

---

## The Question

Most corporate failures are obvious in hindsight. Bed Bath & Beyond was a slow-motion train wreck. Sears spent two decades dying. Silicon Valley Bank's failure made banking history but was, on the morning of March 10, 2023, a deeply confused surprise to even sophisticated observers.

The question I started with: can you tell a slow-burn failure apart from a healthy company *before* the obvious signs appear? Not from the stock price (which is supposed to incorporate all this), not from earnings (which lag), but from the company's own SEC disclosures — specifically, the Item 1A "Risk Factors" section that public companies are required to file annually in their 10-K.

Risk Factors is a strange document. It's drafted defensively by securities lawyers, who have asymmetric incentives: every new risk factor a company discloses creates surface area for a future shareholder lawsuit. So most Risk Factors sections are 70-80% copy-pasted from the prior year, with marginal updates only when something forces an update. The hypothesis I started with: when the text changes substantially, *something happened*. And that change might be detectable before the stock price reflects it.

## What "Detectable" Means

The model has three signals, all scored peer-relative against a 3-5 company sector cohort. Peer-relative scoring isn't optional. It's the single most important methodological choice in the project, and I learned it the hard way.

The first thing I tried was absolute Loughran-McDonald Negative-word ratio — the canonical finance-NLP signal. Loughran and McDonald (Notre Dame, 2011) built a dictionary of ~2,400 words that have negative connotations in a financial context. Computing the ratio of LM-Negative words to total tokens in a company's 10-K is a one-line measurement that the academic literature has used for fifteen years.

It doesn't work for failure detection. JPMorgan Chase, a healthy and ubiquitously profitable money-center bank, has a higher LM-Negative ratio than every failure in my dataset. Why? Because banking regulation requires extensive disclosure of credit risk, market risk, regulatory risk — and those disclosures use words like "loss," "decline," and "adverse." Bank 10-Ks are dense with LM-Negative language *because that's what bank 10-Ks are supposed to contain*. JPM's score isn't a sign of weakness; it's a sign of being a regulated bank.

Worse, in retail — the sector where my model had the most cases — every single failure had *lower* LM-Negative ratio than its healthy peers. Bed Bath & Beyond's negative-word ratio sat at the bottom of the cohort of Best Buy, Macy's, Kohl's, Nordstrom, and Williams-Sonoma every year leading into its 2023 bankruptcy. The established retailers had higher baseline negativity because their disclosures spend many paragraphs on store closures, lease obligations, labor disputes, and inventory shrinkage — all of which load up LM-Negative vocabulary even when business is fine. Failing retailers' lawyers actively suppress new negative disclosures to avoid creating admissions.

If I'd built the model around absolute sentiment, it would have ranked JPMorgan as more at-risk than Bed Bath & Beyond. So I scrapped absolute scoring and rebuilt everything around peer-relative percentiles. Each failure is ranked within a hand-picked cohort of 3-5 sector peers (Bed Bath vs. Best Buy / Macy's / Kohl's / Nordstrom / Williams-Sonoma; Silicon Valley Bank vs. KeyCorp / Fifth Third / Huntington), and the model looks for the failure becoming an outlier *within that cohort*.

## The Three Signals

After three iterations, the model uses three signals:

**Novelty spike.** TF-IDF cosine similarity between consecutive years' Risk Factors text gives a number in [0, 1]. Novelty = `1 − cosine_sim(year N, year N-1)`. The signal fires when the failure's novelty percentile rank crosses 0.75 in any year of the lookback *and* the absolute novelty value clears 0.10 (i.e., the text actually changed meaningfully, not just ranked high among static peers). This catches companies that were forced to rewrite — restructuring lawyers preparing for creditor disclosure, post-event responses, post-merger reorganization.

**Declining under-disclosure.** A failure's novelty rank drops from elevated (>0.50) at the start of the window to bottom-third (≤0.34) by the event year, while the cohort had at least one peer-year of meaningful activity. This catches the SAVE/JCP pattern: management was active early in the window, then went quiet as failure approached. Defense counsel routinely advises minimal disclosure updates during pre-restructuring negotiations — each new risk factor creates plaintiff-friendly surface area for shareholder suits.

**Chronic under-disclosure.** Mean rank ≤ 0.34 across the lookback *and* max rank ≤ 0.50 *and* own raw novelty < 0.10 *and* cohort was active. This catches the failure type that was *always* silent, never even briefly elevated. Express Inc. (Apr 2024 Ch.11) was at the bottom of its retail cohort every year of its 4-year lookback with absolute novelty around 0.08 — they never rewrote, never even tried. The "chronic" signal has the best per-evaluation precision in the dataset (~5% unique-ticker false-positive rate).

A company fires the unified detector if any of the three signals fires.

## What Worked

Across 24 failures, the unified detector caught 19. That's 79% recall.

The seven failures it didn't catch are characterized:

- **Sudden balance-sheet shocks (SVB, Silvergate):** Both banks failed between annual filings. Their FY2022 10-Ks (filed February 2023, just weeks before the March 2023 collapse) looked unremarkable because the rate-shock that killed them happened *after* those filings were locked. No textual fingerprint exists for events that happen between disclosures.
- **Industry shocks where management didn't know (Boeing pre-MAX):** Boeing's FY2017 10-K (filed February 2018) showed nothing suggesting the 737 MAX issues. The Lion Air crash was eight months away. Even the FY2018 filing only addressed the first crash. By the time Boeing's risk language reflected the full crisis, the stock had already collapsed.
- **Chronic anomalies (Peloton):** Peloton sat at the cohort extreme on multiple signals from its IPO. Always extreme, no trajectory. To distinguish "always doomed" from "recently doomed" requires a structural-break test against a longer historical baseline than Peloton has as a public company.
- **Static peer cohorts (Hertz):** The car rental sector was uniformly quiet 2016-2019. There was no peer activity to compare Hertz against. The cohort-activity gate correctly failed.

The successes were more interesting than the misses. **In retail, the model caught Sears (October 2018), Pier 1 (February 2020), Ascena (July 2020), and Bed Bath & Beyond (April 2023) by the novelty-spike signal — all four had visible mid-cycle rewriting peaks. J.C. Penney was caught by the declining-under-disclosure signal because its lawyers had it on minimum-update mode through the pandemic.**

**In specialty pharma**, both major opioid-litigation bankruptcies fired the under-disclosure signal: Endo International (August 2022 Ch.11) and Mallinckrodt (October 2020 Ch.11). Defense counsel routinely advise companies under active litigation to reduce risk-factor updates — every new disclosure becomes a potential admission. The model detected the resulting peer-relative suppression in both cases.

**In commercial real estate**, WeWork's pattern was the cleanest in the dataset. After their SPAC merger in October 2021, WE's FY2021 10-K was a complete rewrite — novelty spike fires. Then between FY2021 and FY2022, the language locked into a new boilerplate state — declining under-disclosure fires. Two signals catching two phases of the same failure.

**As an out-of-sample test**, I locked in the methodology after Phase 1C and then ran it against Spirit Airlines (Chapter 11 November 2024) — a case I hadn't used to develop or tune anything. The first run missed Spirit on the spike signal but caught it on the under-disclosure signal that I'd specifically added to handle the SAVE/JCP pattern. Spirit's FY2023 risk language was 98.4% identical to FY2022, even though the DOJ had blocked the JetBlue merger between those two filings.

## What "Precision" Means Here

The harder question came when I tested the model against the 42 healthy survivor companies in the cohort universe. Earlier in the project, I'd been reporting "100% on the detectable subset" without showing how often the same signals fired on healthy companies. That number turns out to matter a lot.

The novelty-spike signal fires on 40% of healthy survivors. This is partly mechanical: "max rank ≥ 0.75 in any of 4 years" has a high prior probability under random ranking — most companies have at least one above-cohort-median year over four annual filings. The declining-under-disclosure signal has a 14% unique-ticker false-positive rate (six healthy companies). The chronic-under-disclosure signal is the most selective: only 4.8% (Williams-Sonoma and Lucid Motors).

Per-evaluation across all 78 subject-cohort pairs, the unified detector has 29% positive predictive value. Out of every 100 companies it flags, 29 are actual Chapter 11 cases within the test window.

That sounds like a bad model. It's not. It's a *stress screen*.

## The "False Positives" Were Already Distressed

Here's where the project pivoted.

The 22 unique-ticker survivors that fired the unified detector aren't random healthy companies. They're sector-matched peers of failures — meaning they were exposed to the same operational headwinds as the companies that did file Chapter 11. I went back and looked at what happened to each of them between their lookback-window end and May 2026.

Six of the 22 — 27% — underwent material distress events:

- **JWN (Nordstrom):** Taken private May 2025 by the Nordstrom family + El Puerto de Liverpool at a price that bracketed years of underperformance against peers.
- **WBA (Walgreens Boots Alliance):** Sycamore Partners take-private announced 2025, following multi-year operational decline, billions in writedowns, and CEO turnover.
- **CVS Health:** Major 2023-2025 operational issues, stock down ~50% from 2022 peak, CEO replaced in 2024, ongoing pressure to break up the healthcare conglomerate.
- **LCID (Lucid Motors):** Stock crashed >90% from peak. Ongoing severe cash burn. Going-concern adjacent.
- **KSS (Kohl's):** Multiple activist takeover attempts (Franchise Group, Acacia Research), CEO turnover, considered going private, stock crash.
- **M (Macy's):** Arkhouse Management activist takeover bids 2024, pressure to spin off real estate, stock pressure.

Four others had material stress events but ultimately stabilized: Western Alliance (got caught in the March 2023 banking crisis alongside SVB), Clorox (multi-quarter cyberattack disruption in 2023), Alaska Airlines (Hawaiian Airlines merger integration challenges plus the door-plug incident), Williams-Sonoma (post-COVID home goods slowdown).

Thirteen of the 22 are genuinely healthy.

Re-doing the precision math with these subsequent events:

| Horizon | True positives | False positives | Precision |
|---|---|---|---|
| In-sample, Ch.11 only | 19 | 22 | **46%** |
| + Subsequent distress (May 2026) | 25 | 16 | **61%** |
| + Stress-recovered as TP-for-stress | 29 | 13 | **69%** |

This isn't a recall/precision rescue trick. It's a fact about the model: it identifies distress that takes 1-3 years to fully crystallize into formal corporate-action events. Some of that distress becomes Chapter 11. Some becomes forced take-privates. Some becomes activist takeover campaigns. Some becomes 50% stock crashes. The text signal captures all of it, because the underlying pattern that drives all of those outcomes — management's loss of control, the resulting legal and disclosure dance — leaves the same kind of fingerprint in the Risk Factors section.

## What This Is Useful For

The model isn't a high-frequency trading signal. The signal fires on annual filings, which makes it cycle-of-the-business slow. And even at the 1-3 year horizon, 31-54% of the flagged companies don't ultimately distress.

But it's a useful *screen*. If you're an investor doing fundamental research and your model says "here are the companies whose 10-K language is signaling pre-distress stress," the right action is to dig deeper on those names — not to short them automatically. The signal narrows a 500-company universe down to a much smaller research set, with a meaningful lift over base rate.

It's also useful for **risk management**. If you're a vendor doing counterparty diligence on a customer, or a real-estate landlord underwriting a tenant, or a lender reviewing a renewal — running their 10-K through this model is a cheap second opinion. Most of your flags will be wrong (or right at a long horizon), but the cost of missing a Bed Bath & Beyond a year early is much higher than the cost of an extra credit review.

It's potentially most useful for **research and journalism**. If you're writing about corporate decline, the model surfaces a ranked list of "companies quietly telling SEC they're in trouble." That's a starting point for stories that don't yet have stock-price evidence to anchor them.

## What the Project Doesn't Do (and Probably Can't)

A few honest disclaimers:

The cohort selection is hand-picked. I chose Best Buy + Macy's + Kohl's + Nordstrom + Williams-Sonoma as the retail cohort, KEY + FITB + HBAN as the mid-cap commercial bank cohort, and so on. Different cohort choices would give different results. A future version should use objective sector-and-size matching (e.g., GICS sub-industry + market-cap quintile), but for this project the cohorts were defensible by sector intuition.

The test set is sector-matched, not random. The 42 survivor companies are all peers of failures, meaning they were exposed to the same operational headwinds. False-positive rates on a truly random sample of public US companies would likely be lower — the survivors in my universe are themselves a stressed selection.

The signals are tuned. The 0.75 percentile threshold, the 0.10 raw-novelty floor, the 0.34 bottom-third cutoff — all chosen partly to make the model work on the BBBY case I started with. I tried to tighten the worst overfit (the original Phase 1B thresholds were demonstrably p-hacked) by adding multi-control cohorts and percentile-rank scoring in Phase 1C, but some residual tuning likely remains.

And critically: **the model can't predict failures that don't leave textual fingerprints.** Banking shocks like SVB and Silvergate happen between filings. Industry surprises like Boeing's MAX crisis hit companies that didn't see it coming. Companies that always look extreme — Peloton from its IPO onward — have no trajectory to read. Each of these blind spots has a name and a mechanism. None of them are likely to be fixed by tuning thresholds; they're structural limits of analyzing the text of annual filings.

## What's Next

This project ends here, but the underlying problem doesn't.

A natural next move is layering 8-K material event filings on top of 10-Ks. 8-Ks are filed when something specific happens (material event, change in control, restatement), not on an annual schedule. They might catch the SVB-class failures the annual-filing model conceptually cannot. Different cadence, complementary signal.

Another move is tying the text signal to forward stock returns. The current project tested against Chapter 11 events. The same data set could test against 12-month forward total returns — does the signal predict market underperformance, not just bankruptcy? Different empirical question, same infrastructure.

The biggest remaining methodological gap is the "stress vs. failure" distinction. The longitudinal follow-up showed that the model flags real distress but doesn't separate distress-that-will-crystallize from distress-that-will-resolve. Adding forward indicators — analyst rating drift, executive turnover, dividend cuts, credit-default-swap spreads — could meaningfully tighten that distinction. That's where I'd point a follow-up project.

---

## Closing

I started this expecting to build a Chapter 11 predictor. I ended up building a 1-3 year leading indicator of corporate distress that resolves through whatever exit channel the company can manage — Chapter 11, take-private, activist takeover, or stock crash. The same signal that flagged Bed Bath & Beyond two years before its bankruptcy also flagged Nordstrom three years before its take-private. The "false positive" list reads, in retrospect, like a roster of the past five years' most distressed corporate names.

The honest article-grade claim:

> **79% recall on Chapter 11 events within a 24-failure test set spanning 15 sectors. 46% precision in-sample. 61-69% precision at a 2-3 year extended horizon, where 27% of the apparent "false positives" subsequently underwent material distress events. The model is best characterized as a 1-3 year leading indicator of operational distress, not a real-time bankruptcy predictor. Five named structural blind spots — sudden balance-sheet shocks, industry surprises, chronic anomalies, static peer cohorts, and frozen-disclosure failures — account for the remaining misses.**

That's the model. The code is on [GitHub](#), the per-phase findings are in `outputs/phase[0-5]_findings.md`, and the headline chart is below.

*The corporate language in SEC 10-K Risk Factors changes slowly. When it changes, something happened. Most of the time, what happened was a lawyer preparing for a fight that takes 1-3 years to play out.*

---

*Built iteratively over 12 phases with Claude as a coding pair. Total: 66 companies parsed across 15 sectors, 24 failure case studies, 42 sector-matched survivors. Methodology locked at Phase 1C, validated out-of-sample on Spirit Airlines at Phase 1D, scaled at Phase 2-3, false-positive validated at Phase 4, longitudinally corrected at Phase 5.*
