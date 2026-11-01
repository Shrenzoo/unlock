"""Bundled fixture names and pre-registered outcomes. Importable without CAD libraries.

Gallery outcomes were written from each fixture's geometry and the template
domains before any run, and are never derived from a model response. A
publication guard compares recorded runs against them.
"""

NAMES = dict(
    B01="Accessible cartridge",
    B02="Trapped service component",
    B03="Tool-access conflict",
)

GALLERY = dict(
    B04=dict(
        name="Pump cartridge under a crossbar",
        description="Tall crossbar spans the pump bay; a centred relief opens the lift",
        expected="VERIFIED_IMPROVEMENT_FOUND",
        explanation="Web z=44..48 blocks target x[-10,10] y[-5,5]. T01 at (0,0) 24x8 leaves no Y gap; 24x12 clears it by 1-2 mm.",
    ),
    B05=dict(
        name="Battery pack under a strap",
        description="Narrow retaining strap over the pack; the strap moves, nothing is cut",
        expected="VERIFIED_IMPROVEMENT_FOUND",
        explanation="Strap y[-12,12] z=30..34 blocks pack y[4,26]. Only T02 is bound; the first offset tried, -12, moves the strap to y[-24,0], 4 mm clear of the pack.",
    ),
    B06=dict(
        name="Sensor pod under a light bracket",
        description="Low bracket with a tight material budget; only a minimal relief is allowed",
        expected="VERIFIED_IMPROVEMENT_FOUND",
        explanation="Web z=28..32 blocks pod x[-7,7] y[-22,-18]. Cut volume <=1200 mm3 admits only 24 mm wide reliefs; 24x8 at (0,-20) clears it by 2 mm.",
    ),
    B07=dict(
        name="Service hatch behind a shield",
        description="Hatch screw sits under a fixed shield; no permitted edit can free it",
        expected="INCOMPLETE_ANALYSIS",
        explanation="screw1 retains the hatch; the driver axis above it crosses the 0.2 mm top of the fixed shield can at z=35. The bridge is the only editable part and is not in the way, so the verifier rejects each bracket edit with screw1 TOOL_ACCESS_BLOCKED. First registered as NO_VERIFIED_IMPROVEMENT; the first run showed the controller's 6-turn budget leaves the third constructed candidate unchecked, so the honest recorded outcome is INCOMPLETE_ANALYSIS.",
    ),
    B08=dict(
        name="Filter cartridge, already serviceable",
        description="Two screws then a straight lift; nothing to redesign",
        expected="NO_SUPPORTED_CANDIDATE",
        explanation="Both screw drivers and the cartridge lift are unobstructed: remove screw1, screw2, then lift Z+. No bracket binding; nothing to redesign. Screws sit at x=+-32 so the driver handle's conservative box clears the cartridge; at x=+-26 it overlapped and the move was reported unknown.",
    ),
)

# B02 is the original licensed demonstration; it must find a verified improvement.
EXPECTED = dict(B02="VERIFIED_IMPROVEMENT_FOUND") | {
    code: f["expected"] for code, f in GALLERY.items()
}
PROJECTS = [(code, name, None) for code, name in NAMES.items()] + [
    (code, f["name"], f["description"]) for code, f in GALLERY.items()
]
