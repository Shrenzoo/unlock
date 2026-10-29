"""Independent exhaustive oracle vs production UCS on finite algorithmic graphs.

These tests isolate search, not geometry. Real CAD integration lives separately.
The reference enumerator uses no heap, production transition or cost function.
"""

from dataclasses import dataclass
from types import SimpleNamespace
import threading

import pytest

from unlock_engine.contracts import Transform, digest
from unlock_engine.planning.actions import Evaluation
from unlock_engine.planning.contracts import (
    Action,
    Certificate,
    Rejection,
    SearchPolicy,
    State,
)
from unlock_engine.planning.search import search


@dataclass(frozen=True)
class Edge:
    part: str
    tool: str | None = None
    axis: str = "Z+"
    requires: tuple = ()
    blockers: tuple = ()
    unknown: bool = False

    def action(self):
        return Action(
            kind="REMOVE_FASTENER" if self.tool else "TRANSLATE_PART",
            component_id=self.part,
            tool_id=self.tool,
            axis=self.axis,
            distance_mm=10,
        )


class Graph:
    """Exact, inspectable finite graph fixture, with no pretend CAD evidence."""

    target_id = "target"
    input_hash = "abstract-search-test"

    def __init__(self, edges, policy=SearchPolicy()):
        self.edges, self.policy = edges, policy
        self.placements = {e.part: Transform() for e in edges}

    def actions(self, state):
        return [
            e.action()
            for e in sorted(self.edges, key=lambda e: (e.part, e.axis, e.tool or ""))
            if e.part not in state.removed
        ]

    def prerequisites(self, k):
        return ()


class ExactEdges:
    def __init__(self, graph, hook=None):
        self.graph, self.hook = graph, hook
        self.hits = self.misses = self.geometry_calls = 0

    def evaluate(self, state, action):
        self.misses += 1
        if self.hook:
            self.hook(action)
        e = next(e for e in self.graph.edges if e.action() == action)
        allowed = (
            set(e.requires) <= state.removed and not set(e.blockers) - state.removed
        )
        data = dict(
            revision_id="abstract",
            input_hash=self.graph.input_hash,
            geometry_hash="abstract",
            constraint_hash="abstract",
            tool_hash="abstract",
            policy_hash="abstract",
            before_state_hash=state.identity(self.graph.input_hash),
            action=action,
            mode="removal",
            status="unknown" if e.unknown else "clear",
            paths=(),
            subchecks=(),
        )
        cert = Certificate(id=digest(data), **data)
        if allowed and not e.unknown:
            return Evaluation("clear", cert)
        data = dict(
            revision_id="abstract",
            state_hash=state.identity(self.graph.input_hash),
            removed_ids=tuple(sorted(state.removed)),
            action=action,
            remaining_obstacle_ids=(),
            constraint_ids=(),
            reason="unknown edge" if e.unknown and allowed else "prerequisites",
            category="UNKNOWN_GEOMETRY"
            if e.unknown and allowed
            else "SEMANTICALLY_BLOCKED",
            geometry_evidence_level="abstract",
        )
        return Evaluation(
            "unknown" if e.unknown and allowed else "rejected",
            None,
            Rejection(id=digest(data), **data),
        )


def exhaustive(edges):
    """Enumerate every legal sequence, calculate costs directly from its actions."""
    solutions = []

    def visit(removed, sequence):
        if "target" in removed:
            nonfasteners = {
                e.part for e in sequence if e.tool is None and e.part != "target"
            }
            fasteners = {e.part for e in sequence if e.tool is not None}
            tools = [e.tool for e in sequence if e.tool is not None]
            changes = sum(a != b for a, b in zip(tools, tools[1:]))
            solutions.append(
                (
                    (len(nonfasteners), len(fasteners), changes, len(sequence)),
                    sequence,
                    removed,
                )
            )
            return
        for edge in edges:
            if (
                edge.part in removed
                or not set(edge.requires) <= removed
                or set(edge.blockers) - removed
                or edge.unknown
            ):
                continue
            visit(removed | {edge.part}, sequence + (edge,))

    visit(frozenset(), ())
    return min(solutions, key=lambda s: s[0]) if solutions else None


CASES = [
    (Edge("target"),),
    (Edge("cover"), Edge("target", requires=("cover",))),
    (Edge("s1", "A"), Edge("s2", "A"), Edge("target", requires=("s1", "s2"))),
    (
        Edge("s1", "A"),
        Edge("s2", "B"),
        Edge("s3", "A"),
        Edge("target", requires=("s1", "s2", "s3")),
    ),
    (
        Edge("s1", "A"),
        Edge("cover", requires=("s1",)),
        Edge("s2", "B", requires=("cover",)),
        Edge("target", requires=("s2",)),
    ),
    (
        Edge("cover"),
        Edge("s1", "A"),
        Edge("s2", "A"),
        Edge("target", axis="X+", requires=("s1", "s2")),
        Edge("target", axis="Y+", requires=("cover",)),
    ),
    (
        Edge("s1", "A"),
        Edge("s2", "B"),
        Edge("target", axis="X+", requires=("s1",)),
        Edge("target", axis="Y+", requires=("s1", "s2")),
    ),
    (Edge("unnecessary", "A"), Edge("target")),
    (Edge("target", blockers=("fixed",)),),
    (Edge("cover", requires=("missing",)), Edge("target", requires=("cover",))),
    (
        Edge("a"),
        Edge("b"),
        Edge("target", axis="X+", requires=("a",)),
        Edge("target", axis="Y+", requires=("b",)),
    ),
]


@pytest.mark.parametrize("edges", CASES)
def test_uniform_cost_matches_independent_exhaustive_oracle(edges):
    graph = Graph(edges)
    result = search(graph, ExactEdges(graph))
    expected = exhaustive(edges)
    assert result.complete and result.unresolved == 0
    if expected is None:
        assert not result.steps and not result.optimal
    else:
        sequence = tuple(
            next(e for e in edges if e.action() == s.action()) for s in result.steps
        )
        tools = [e.tool for e in sequence if e.tool]
        actual = (
            len({e.part for e in sequence if not e.tool and e.part != "target"}),
            len({e.part for e in sequence if e.tool}),
            sum(a != b for a, b in zip(tools, tools[1:])),
            len(sequence),
        )
        assert actual == expected[0]
        assert result.steps[-1].component_id == "target" and result.optimal
        removed = set()
        for e in sequence:
            assert set(e.requires) <= removed and not set(e.blockers) - removed
            assert e.part not in removed
            removed.add(e.part)


def test_lexicographic_route_can_have_more_operations_than_shortest_route():
    edges = CASES[5]
    graph = Graph(edges)
    result = search(graph, ExactEdges(graph))
    assert [s.component_id for s in result.steps] == ["s1", "s2", "target"]
    assert (
        len(result.steps) == 3
    )  # cover+target takes two, but removes an unrelated part


def test_tool_state_and_hand_translation_do_not_reset_last_tool():
    graph = Graph(CASES[4])
    result = search(graph, ExactEdges(graph))
    assert [s.tool_id for s in result.steps if s.tool_id] == ["A", "B"]
    assert exhaustive(graph.edges)[0] == (1, 2, 1, 4)
    assert State(frozenset({"s1"}), "A") != State(frozenset({"s1"}), "B")


def test_tool_grouping_and_equal_cost_tie_are_deterministic():
    graph = Graph(CASES[3])
    outcomes = [search(graph, ExactEdges(graph)) for _ in range(3)]
    assert all(o.steps == outcomes[0].steps for o in outcomes)
    assert [s.tool_id for s in outcomes[0].steps[:-1]] == ["A", "A", "B"]


def test_unknown_edge_prevents_exhaustive_no_path_and_optimality():
    for edges in (
        (Edge("target", unknown=True),),
        (Edge("a", unknown=True), Edge("target")),
    ):
        graph = Graph(edges)
        r = search(graph, ExactEdges(graph))
        assert r.unresolved == 1 and not r.complete and not r.optimal
        assert bool(r.steps) == (len(edges) == 2)


def test_state_limit_and_deadline_are_distinct():
    graph = Graph(CASES[1], SearchPolicy(max_expanded_states=1))
    result = search(graph, ExactEdges(graph))
    assert (
        not result.complete
        and result.stats.termination == "state_limit"
        and result.expanded == 1
    )
    ticks = iter((0, 31, 31, 31, 31, 31))
    result = search(
        Graph(CASES[1]), ExactEdges(Graph(CASES[1])), clock=lambda: next(ticks)
    )
    assert result.stats.termination == "time_limit" and not result.complete


def test_checked_goal_found_before_timeout_is_preserved_without_optimality():
    graph = Graph((Edge("target"),))
    clock = SimpleNamespace(value=0)
    validator = ExactEdges(graph, hook=lambda _: setattr(clock, "value", 31))
    result = search(graph, validator, clock=lambda: clock.value)
    assert result.steps and not result.complete and not result.optimal


def test_cancellation_discards_uncommitted_goal():
    event = threading.Event()
    graph = Graph((Edge("target"),))
    result = search(graph, ExactEdges(graph, hook=lambda _: event.set()), cancel=event)
    assert result.cancelled and not result.steps and not result.complete


def test_state_identity_is_order_independent_and_tool_sensitive():
    a = State(frozenset(("occ2", "occ1")), "A")
    b = State(frozenset(("occ1", "occ2")), "A")
    assert hash(a) == hash(b) and a.identity("revision") == b.identity("revision")
    assert a.identity("revision") != a.identity("other revision")
    assert a.identity("revision") != State(a.removed, "B").identity("revision")
