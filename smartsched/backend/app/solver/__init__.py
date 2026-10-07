"""SmartSched solver: pure functions over the dataclasses in :mod:`app.solver.model`.

* :func:`app.solver.cpsat.solve` — CP-SAT timetabling / room assignment.
* :func:`app.solver.repair.repair` / :func:`app.solver.repair.validate` — LNS repair, validation.
* :mod:`app.solver.diagnose` — infeasibility explanation.
* :mod:`app.solver.generators` — synthetic instances.
"""

from app.solver.cpsat import solve
from app.solver.model import Assignment, Block, Constraint, Diagnosis, Event, Room, SolverInput, SolverResult
from app.solver.repair import Violation, repair, score, validate

__all__ = [
    "Assignment",
    "Block",
    "Constraint",
    "Diagnosis",
    "Event",
    "Room",
    "SolverInput",
    "SolverResult",
    "Violation",
    "repair",
    "score",
    "solve",
    "validate",
]
