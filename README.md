<p align="center">
  <a href="https://unlock-labs.pages.dev">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="assets/readme/brand-dark.svg">
      <source media="(prefers-color-scheme: light)" srcset="assets/readme/brand-light.svg">
      <img src="assets/readme/brand-light.svg" width="760" alt="UNLOCK. Design for the day it breaks. AI-assisted redesign for mechanical repairability.">
    </picture>
  </a>
</p>

<p align="center">
  <strong>A broken part shouldn't make a product disposable.</strong><br>
  UNLOCK reads a CAD assembly, finds exactly what stops a failed part from coming out, lets Meta's Muse Spark 1.3 propose a constrained design change, builds that change in real CAD, and checks the result with a verifier the model cannot influence.
</p>

<p align="center">
  <a href="https://unlock-labs.pages.dev"><strong>Open the live demo</strong></a>
  &nbsp;·&nbsp;
  <a href="#05--the-ai-agent">How the agent works</a>
  &nbsp;·&nbsp;
  <a href="#10--measured-evidence">Evidence</a>
  &nbsp;·&nbsp;
  <a href="docs/README.md">Technical docs</a>
</p>
<!-- A link to the demo film goes in the row above once the final video has a public URL. -->

<p align="center">
  <sub>A research prototype on synthetic CAD fixtures, built for the Meta Global AI Developer Hackathon 2026, Indie Developer track, Push the Frontier theme. Not affiliated with or endorsed by Meta.</sub>
</p>

<p align="center">
  <sub>
    <a href="#01--the-problem">Problem</a> ·
    <a href="#02--the-idea">Idea</a> ·
    <a href="#03--see-it-work">See it work</a> ·
    <a href="#04--the-trust-boundary">Trust boundary</a> ·
    <a href="#05--the-ai-agent">Agent</a> ·
    <a href="#06--the-engineering-engine">Engine</a> ·
    <a href="#07--independent-verification">Verification</a> ·
    <a href="#08--real-results">Results</a> ·
    <a href="#09--engineering-architecture">Architecture</a> ·
    <a href="#10--measured-evidence">Evidence</a> ·
    <a href="#11--try-unlock">Try it</a> ·
    <a href="#12--reproducibility">Reproduce</a> ·
    <a href="#13--scope-and-limitations">Limits</a> ·
    <a href="#14--future-direction">Next</a> ·
    <a href="#15--credits-and-licenses">Credits</a>
  </sub>
</p>

## 01 · The problem

Most products are designed to be built. Far fewer are designed to be taken apart.

A part that is meant to be replaced can still be impossible to reach. A strap runs across the battery. A bracket spans the module. A screw head sits under a shield. Each of those parts has a reason to be there, and together they can turn a routine replacement into a teardown, an expensive service job, or a product in the bin.

The world generated a record 62 million tonnes of e-waste in 2022, and 22.3% of it was documented as formally collected and recycled ([Global E-waste Monitor 2024](https://www.unitar.org/about/news-stories/press/global-e-waste-monitor-2024-electronic-waste-rising-five-times-faster-documented-e-waste-recycling)). Repair is one part of that picture, and geometry is one part of repair: spare parts, documentation, connectors and adhesives matter too. But geometry is the part decided in CAD, long before anyone holds a screwdriver, when changing it is still cheap.

UNLOCK works on one question: **can this part come out, and if it can't, what is the smallest supported change that lets it?**

## 02 · The idea

A failed part is trapped. UNLOCK works through the problem the way an engineer would, with a hard line between what may be guessed and what must be measured.

1. **Inspect.** Import a STEP assembly and its manifest. Freeze the revision, the target and every constraint under a hash.
2. **Explain.** A deterministic planner searches for a removal route. If there is none, it reports what blocks the part, with exact BRep evidence.
3. **Investigate.** Muse Spark 1.3 reads that evidence through eight tools and proposes an edit from a finite list, citing the evidence it responds to.
4. **Construct.** A trusted CAD constructor builds the edit. The model writes no code and no geometry.
5. **Verify.** A fresh worker rebuilds the design, measures the material, searches for a route again, replays it forward and reverses it.
6. **Export.** A person accepts the result. The STEP file is written, reimported and rechecked, and every artifact is addressed by SHA-256.

What comes out is an inspectable engineering record. The model's own opinion of that record is stored alongside it, marked as carrying no authority.
