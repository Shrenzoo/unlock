<p align="center">
  <img src="assets/readme/logo-mark.svg" width="76" height="76" alt="UNLOCK mark" />
</p>

<h1 align="center">UNLOCK</h1>

<p align="center">
  <em>Design for the day it breaks.</em>
</p>

<p align="center">
  An AI agent that redesigns a physical product so its failed part can actually be replaced —<br/>
  then proves the redesign is safe with a CAD kernel <strong>before anyone cuts metal.</strong>
</p>

<p align="center">
  <a href="https://github.com/Shrenzoo/unlock/assets/readme/hero-trapped-part.svg"><img src="assets/readme/hero-trapped-part.svg" width="100%" alt="A fan module trapped behind a bridge bracket; a relief is cut so it lifts out" /></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/track-Push%20the%20Frontier-3268f5?style=for-the-badge&labelColor=151719" alt="Track: Push the Frontier" />
  <img src="https://img.shields.io/badge/model-Muse%20Spark%201.3-34866b?style=for-the-badge&labelColor=151719" alt="Model: Muse Spark 1.3" />
  <img src="https://img.shields.io/badge/tests-327%20passed-34866b?style=for-the-badge&labelColor=151719" alt="327 tests passed" />
  <img src="https://img.shields.io/badge/live%20run-VERIFIED__IMPROVEMENT-e4602f?style=for-the-badge&labelColor=151719" alt="Live run: verified improvement found" />
  <img src="https://img.shields.io/badge/Meta%20Global%20AI%20Developer%20Hackathon-2026-17191b?style=for-the-badge&labelColor=151719" alt="Meta Global AI Developer Hackathon 2026" />
</p>

---

## Contents

<table>
<tr>
<td width="50%">

**The argument**
1. [The problem](#the-problem)
2. [What UNLOCK does](#what-unlock-does)
3. [Why this pushes the frontier](#why-this-pushes-the-frontier)
4. [Why nothing like this exists](#why-nothing-like-this-exists)

</td>
<td width="50%">

**The substance**
5. [How it works](#how-it-works)
6. [The trust boundary](#the-trust-boundary)
7. [The eight tools](#the-eight-tools)
8. [The live run](#the-live-run)
9. [Verification](#verification)

</td>
</tr>
<tr>
<td>

10. [Architecture](#architecture)
11. [Getting started](#getting-started)
12. [The API surface](#the-api-surface)

</td>
<td>

13. [Evidence & reproducibility](#evidence--reproducibility)
14. [Scope, honestly](#scope-honestly)
15. [Built during the hackathon](#built-during-the-hackathon)

</td>
</tr>
</table>

---

## The problem

Every product is designed for the factory. Almost none are designed for the day it breaks.

A fan module dies inside a sealed enclosure. A bracket — never meant to be removed — sits directly above it. The service manual says *replace the fan*. Geometry says *the fan cannot leave*. So the enclosure goes in a skip, and a €200 part failure becomes a €2,000 replacement plus the embodied carbon of an entirely new machine.

This is not a rounding error in the waste stream. It is the waste stream. Right-to-repair legislation keeps trying to mandate an answer, and keeps discovering that the answer cannot be legislated into existence — because the obstruction is not a policy decision. **It is a shape.**

Fixing the shape requires someone to reason about geometry, motion, tool access and constraint compliance together, and then to be *certain* they got it right. That combination is exactly what has been missing.

<p align="center">
  <img src="assets/readme/before-after-path.svg" width="100%" alt="Before: no supported removal route. After: a verified Z-plus translation of 80mm" />
</p>

<sub><code>fixture B02</code> — the baseline search returns <code>no_path_supported</code> with two confirmed geometric obstructions and an actual BRep witness. After the relief, the route is a single verified translation. Both halves of this diagram are computed, not illustrated.</sub>
