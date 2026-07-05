# Viva Cheat Sheet — "Equal Suffering Is Not Fairness"
*A Systematic Survey of Starvation and Resource Allocation in CPU Scheduling*

## The 30-Second Pitch (memorize this)

We built a discrete-event simulator that ran 5 CPU scheduling algorithms — FCFS, SJF, Round Robin, Priority, and Priority+Aging — over 10 **real** historical HPC supercomputer traces (not synthetic data), sampling 564 jobs each, and measured 53 fairness/performance metrics. Our core finding: **no single algorithm can simultaneously minimize wait time, be perfectly fair, prevent starvation, AND treat all job sizes equally** — we formalize this as a Fairness-Efficiency Trade-off theorem. FCFS looks "fair" by Jain's Index but it's just equal suffering; SJF is fastest but starves big jobs; Round Robin is the best practical middle-ground for interactive systems; Priority+Aging is what production cloud systems need.

## The Numbers You MUST Retain

| Metric | FCFS | SJF | Round Robin | Priority | Priority+Aging |
|---|---|---|---|---|---|
| Mean AWT | 2.45M | 666K (3.7x better) | 1.59M | 2.02M | 2.10M |
| Mean Response Time | 2.45M | 666K | 570K (**4.29x faster than FCFS**) | 2.02M | 2.10M |
| Mean JFI (1=perfect) | **0.75** (highest, but "equal suffering") | 0.18 (worst) | 0.43 | 0.66 | 0.68 |
| Mean Starvation % | 98.9% | 43.7% (counterintuitive!) | 95.0% | 98.7% | 98.8% |
| Mean SFR (1=size-neutral) | 1.08 | 449 (extreme large-job bias) | 5.6 | 1.28 | 1.29 |

- **n = 564** jobs/trace, chosen via convergence analysis (metrics stabilize within 2% by n≈400–500).
- **10 traces**: SDSC-SP2, SDSC-BLUE, ANL-Intrepid, CTC-SP2, HPC2N, KTH-SP2, CEA-Curie, PIK-IPLEX, RICC, Lublin-1024 — all in Standard Workload Format (SWF), from Parallel Workloads Archive / Grid Workloads Archive.
- Quantum for RR = **0.5 x mean burst time**.
- Starvation threshold = wait time **> 3x mean burst time**.

## 20 Must-See Q&A

**1. Q: What's the paper's title and one-line thesis?**
A: "Equal Suffering Is Not Fairness" — high fairness scores (like FCFS's JFI) can just mean everyone waits equally badly, not that the system is actually fair.

**2. Q: Why use real HPC traces instead of synthetic workloads?**
A: Synthetic workloads (e.g., uniform/Poisson arrivals) don't capture real heavy-tailed job-size distributions and bursty arrivals. Real traces from decades of production supercomputers give empirical validity — this is literally listed as their contribution over prior work that used 1-3 metrics on synthetic data.

**3. Q: Why n=564 jobs specifically?**
A: Empirically justified via convergence sweep over n ∈ {50...1000}. JFI, WT CV, Starvation Rate, and NTT all stabilize (change <2%) by n≈400-500. 564 balances stability vs. compute cost — not an arbitrary number.

**4. Q: What is Jain's Fairness Index and what does it actually measure?**
A: JFI = (Σxᵢ)² / (n·Σxᵢ²), range [1/n, 1], where xᵢ = wait time of process i. It's scale-independent. High JFI just means wait times are *uniform* across jobs — it says nothing about whether that uniform wait is short or fair to job size.

**5. Q: Why does FCFS have the highest JFI but is called "unfair"?**
A: Because everyone suffers roughly equally long waits (the convoy effect hits short and long jobs proportionally similarly in aggregate) — "equal suffering," not genuine fairness. It's fair by uniformity, not by justice.

**6. Q: Why does SJF appear to have LOWER starvation rate than FCFS/RR, when SJF is famous for starving long jobs?**
A: Starvation is defined as wait > 3x *mean* burst time. Under SJF, short jobs finish almost immediately, pulling the mean burst time down and being counted as "not starved" — the few long jobs that do starve are a small fraction *by count*, even though they starve severely. This distinction is captured instead by the Size Fairness Ratio (SFR), where SJF's SFR hits 449 — showing brutal size discrimination that starvation-rate-by-count hides.

**7. Q: What is Size Fairness Ratio (SFR) and why do you need it alongside starvation rate?**
A: SFR = (avg wait of large jobs) / (avg wait of small jobs), split at median service time. SFR=1 is size-neutral. It's needed because starvation rate (a count-based, threshold metric) can mask severe systemic bias against large jobs — SFR directly measures that bias.

**8. Q: What is Bounded Slowdown and why the "+1" term?**
A: BS = (wait+service+1)/(service+1) — measures proportional unfairness (how many times longer than its own execution time a job effectively took). The +1 avoids division-by-zero/explosion for near-zero-length jobs.

**9. Q: State the Fairness-Efficiency Trade-off theorem.**
A: No algorithm can simultaneously (A) minimize average waiting time, (B) achieve perfect fairness (JFI=1), (C) prevent all starvation, and (D) maintain size neutrality (SFR≈1). Proof sketch: SJF gets (A) but fails B/C/D; FCFS gets high JFI via equal suffering; Priority+Aging gets (C) but sacrifices (A); RR balances B and D but sacrifices (A).

**10. Q: Why is Round Robin called the "practical synthesis"?**
A: It gives 4.29x faster response time than FCFS, cuts queue length by 1.86x, keeps moderate JFI (0.43) and bounded (not eliminated) tail latency — a workable middle ground for interactive/OLTP systems, without SJF's extreme unfairness or FCFS's poor responsiveness.

**11. Q: Why is Priority+Aging "essential" for cloud/multitenant environments specifically?**
A: It's the only variant designed to guarantee no *indefinite* starvation (via monotonic priority increase) while staying near size-neutral (SFR 1.29) — matches multitenant needs where you can't let any tenant's job wait forever, but you also don't want SJF-style size discrimination.

**12. Q: Then why does Priority+Aging's measured starvation RATE (98.8%) look just as bad as plain Priority (98.7%)? Isn't aging supposed to fix that?**
A: Key nuance — aging eliminates *indefinite* starvation (mathematically guaranteed bounded wait) but doesn't prevent jobs from crossing the fixed 3x-mean-burst threshold used in this study. Under bursty HPC arrival patterns, the aging rate isn't fast enough to pull priorities up before that threshold is crossed. It's "bounded but still slow," not "fast."

**13. Q: What real anomaly did you find in SDSC-BLUE, and what causes it?**
A: Priority scheduling produced average queue length of 340.54 — *worse* than FCFS's 283.80. Cause: SDSC-BLUE has bursts of high-priority jobs; without aging, low-priority jobs never drain and pile up, so aggregate queue depth exceeds even FCFS. This is a direct real-world illustration of the starvation pathology Priority+Aging is meant to fix.

**14. Q: What's the anomaly in CEA-Curie, and what does it show?**
A: Priority and Priority+Aging both get SFR=2.91 there (vs. typical 0.69–1.17 elsewhere) — because CEA-Curie has a high proportion of large, low-priority jobs, so priority-based dispatch disproportionately delays large jobs. Shows SFR outcomes depend on the *interaction* between job-size distribution and priority assignment, not the algorithm alone.

**15. Q: What is the convoy effect and which algorithm suffers most?**
A: Short jobs get stuck waiting behind one long-running job holding the CPU under non-preemptive scheduling. FCFS suffers most (mean convoy delay ~2.1M time units); RR cuts it to ~464K (4.6x lower); SJF nearly eliminates it (~28K) since short jobs jump the queue.

**16. Q: Why does Response Time = Wait Time for FCFS/Priority/Priority+Aging but not for RR/SJF?**
A: Those three are non-preemptive — a job can't start until everything ahead finishes, so "first execution" = "start of only execution." RR and SJF are preemptive/reorder-based, so a job can get its *first* CPU slice quickly even if its full completion is delayed later — breaking the wait=response symmetry.

**17. Q: What does WT CV (Waiting Time Coefficient of Variation) tell you that JFI doesn't?**
A: JFI measures relative equality of wait times; WT CV measures *predictability* (std/mean of wait time). SJF has very low JFI (0.18) but high WT CV (2.53) — erratic, unpredictable waits. It's possible to be "unfair" and "unpredictable" simultaneously, or fair-by-uniformity (FCFS) yet still not have the lowest variance.

**18. Q: What are the key limitations/threats to validity you should admit if asked?**
A: (1) Single-core model only — no multi-core, cache affinity, or NUMA effects modeled (explicitly flagged as future work). (2) Traces are CPU-bound HPC workloads — OLTP workloads with 30-50% I/O time would show less algorithm differentiation. (3) Quantum/aging-rate sensitivity was only partially swept. (4) Preemption overhead is modeled analytically (0.1-1%), not simulated directly.

**19. Q: What's your ethics statement, and why is it trivially satisfied?**
A: No human subjects, no PII — it's a computational simulation over historical system logs (job arrival/burst metadata), so no ethical approval was required.

**20. Q: If asked "what would you do differently / what's next" — what's your answer?**
A: Sensitivity analysis across a range of quantum sizes and aging rates (only partially done here), multicore scheduling with cache/NUMA effects, temporal/longitudinal fairness analysis, ML-based adaptive quantum selection, and energy-efficiency metrics — all explicitly named as future work in the conclusion.

---

**One thing to sort out with your teammates before you walk in:** the paper doesn't say who did what (5 co-authors). If your instructor asks "what part did *you* specifically work on," have that answer ready.
