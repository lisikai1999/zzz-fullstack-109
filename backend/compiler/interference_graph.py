from dataclasses import dataclass, field
from .parser import TACInstruction


@dataclass
class InterferenceGraph:
    variables: list[str] = field(default_factory=list)
    edges: set = field(default_factory=set)
    colors: dict = field(default_factory=dict)
    spilled: set = field(default_factory=set)

    def to_dict(self):
        nodes = []
        for v in self.variables:
            nodes.append({
                "name": v,
                "color": self.colors.get(v, -1),
                "spilled": v in self.spilled,
            })
        edge_list = [{"source": u, "target": v} for u, v in self.edges]
        return {"nodes": nodes, "edges": edge_list}


def build_interference_graph(
    instructions: list[TACInstruction],
    live_after: dict[int, set[str]],
) -> InterferenceGraph:
    """
    Build interference graph: two variables are connected if they are
    simultaneously live at the same program point.

    For each instruction with dest d, d interferes with every variable
    in live_after(instruction) except:
      - d itself
      - for copy (assign) x = y, don't add edge (x, y)

    Additionally, for each program point, all variables in the live set
    mutually interfere (captured by the def-based rule above since every
    live variable must have been defined somewhere with others live).
    """
    variables = set()
    for instr in instructions:
        variables |= instr.get_defs()
        variables |= instr.get_uses()

    edges = set()

    for instr in instructions:
        defs = instr.get_defs()
        if not defs:
            continue
        d = next(iter(defs))
        live_set = live_after.get(instr.index, set())

        for v in live_set:
            if v != d:
                if instr.op == "assign" and instr.arg1 == v:
                    continue
                edge = tuple(sorted((d, v)))
                edges.add(edge)

    # Also ensure all pairs of simultaneously-live variables at each point
    # are connected (handles cases where a variable is live-through without
    # being defined in the block)
    all_live_sets = list(live_after.values())
    for live_set in all_live_sets:
        vars_list = sorted(live_set)
        for i in range(len(vars_list)):
            for j in range(i + 1, len(vars_list)):
                edges.add((vars_list[i], vars_list[j]))

    return InterferenceGraph(variables=sorted(variables), edges=edges)
