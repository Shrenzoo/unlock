"""Deterministic lexicographic uniform-cost search; no geometry rules live here."""

from dataclasses import dataclass
import heapq
import itertools
import time

from .contracts import SearchStats, State
from .state import add_cost, advance, make_step


@dataclass(frozen=True)
class SearchOutcome:
    steps: tuple
    complete: bool
    optimal: bool
    cancelled: bool
    expanded: int
    elapsed_ms: float
    unresolved: int
    rejections: tuple
    certificates: tuple
    stats: SearchStats


def search(problem, validator, *, cancel=None, clock=time.monotonic, progress=None):
    started = clock()
    initial = State()
    serial = itertools.count()
    frontier = [((0, 0, 0, 0), next(serial), initial)]
    best = {initial: (0, 0, 0, 0)}
    parents = {}
    expanded = generated = admitted = rejected = unresolved = 0
    peak = 1
    rejections, certificates = [], {}
    goal = None
    complete = optimal = cancelled = False
    termination = "searching"

    def route(state):
        steps = []
        while state != initial:
            before, step = parents[state]
            steps.append(step)
            state = before
        return tuple(reversed(steps))

    def snapshot():
        stats = SearchStats(
            generated_actions=generated,
            admitted_transitions=admitted,
            rejected_transitions=rejected,
            unknown_transitions=unresolved,
            cache_hits=validator.hits,
            cache_misses=validator.misses,
            geometry_validation_calls=validator.geometry_calls,
            peak_frontier=peak,
            frontier_size=len(frontier),
            frontier_status="exhausted"
            if termination == "frontier_exhausted"
            else "goal_settled"
            if termination.startswith("goal_")
            else "interrupted"
            if termination in ("state_limit", "time_limit", "cancelled")
            else "open",
            termination=termination,
        )
        return SearchOutcome(
            route(goal[1]) if goal and not cancelled else (),
            complete,
            optimal,
            cancelled,
            expanded,
            (clock() - started) * 1000,
            unresolved,
            tuple(rejections),
            tuple(certificates[k] for k in sorted(certificates)),
            stats,
        )

    def stopped():
        nonlocal termination, cancelled
        if cancel is not None and cancel.is_set():
            cancelled, termination = True, "cancelled"
            return True
        if clock() - started >= problem.policy.max_seconds:
            termination = "time_limit"
            return True
        return False

    while frontier:
        if stopped():
            break
        cost, _, state = heapq.heappop(frontier)
        if best.get(state) != cost:
            continue
        if problem.target_id in state.removed:
            goal = (cost, state)
            optimal = complete = unresolved == 0
            termination = (
                "goal_settled" if complete else "goal_with_unresolved_alternatives"
            )
            break
        if expanded >= problem.policy.max_expanded_states:
            heapq.heappush(frontier, (cost, next(serial), state))
            termination = "state_limit"
            break
        expanded += 1
        for action in problem.actions(state):
            if stopped():
                break
            generated += 1
            result = validator.evaluate(state, action)
            if result.certificate:
                certificates[result.certificate.id] = result.certificate
            if result.status != "clear":
                rejected += 1
                unresolved += int(result.status == "unknown")
                rejections.append(result.rejection)
                continue
            admitted += 1
            after = advance(state, action)
            next_cost = add_cost(cost, state, action, problem.target_id)
            if after in best and best[after] <= next_cost:
                continue
            best[after] = next_cost
            parents[after] = (
                state,
                make_step(problem, state, action, result.certificate),
            )
            heapq.heappush(frontier, (next_cost, next(serial), after))
            peak = max(peak, len(frontier))
            if problem.target_id in after.removed and (
                goal is None or next_cost < goal[0]
            ):
                goal = (next_cost, after)
        if progress:
            progress(snapshot())
        if stopped():
            break
    else:
        complete = unresolved == 0
        termination = "frontier_exhausted" if complete else "unresolved_transitions"
    return snapshot()
