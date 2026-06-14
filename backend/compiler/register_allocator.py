from collections import defaultdict
from .interference_graph import InterferenceGraph, build_interference_graph
from .parser import TACInstruction


MAX_SPILL_ITERATIONS = 5


def allocate_registers_iterative(
    instructions: list[TACInstruction],
    blocks_builder,
    liveness_analyzer,
    k: int,
) -> tuple[list[TACInstruction], "list", InterferenceGraph, "LivenessResult"]:
    """
    Full iterative register allocation with spill-rerun convergence.

    1. Build basic blocks and CFG
    2. Analyze liveness
    3. Build interference graph
    4. Try K-coloring
    5. If spill needed: rewrite IR with spill loads/stores, goto step 1
    6. Repeat until no spills or MAX_SPILL_ITERATIONS

    Returns: (final_instructions, final_blocks, final_ig, final_liveness)
    """
    from .basic_blocks import build_basic_blocks
    from .liveness import analyze_liveness

    current_instructions = instructions
    spill_offset_map = {}
    next_spill_offset = 0
    all_spilled = set()

    for iteration in range(MAX_SPILL_ITERATIONS):
        blocks = build_basic_blocks(current_instructions)
        liveness_result = analyze_liveness(blocks)
        ig = build_interference_graph(current_instructions, liveness_result.live_after)
        ig = _color_graph(ig, k, current_instructions)

        if not ig.spilled:
            return current_instructions, blocks, ig, liveness_result

        for v in ig.spilled:
            if v not in spill_offset_map:
                spill_offset_map[v] = next_spill_offset
                next_spill_offset += 4
            all_spilled.add(v)

        current_instructions = _rewrite_with_spills(
            current_instructions, ig.spilled, spill_offset_map
        )

    # Final attempt after max iterations: run one more time,
    # remaining uncolorable vars stay spilled
    blocks = build_basic_blocks(current_instructions)
    liveness_result = analyze_liveness(blocks)
    ig = build_interference_graph(current_instructions, liveness_result.live_after)
    ig = _color_graph(ig, k, current_instructions)
    ig.spilled |= all_spilled

    return current_instructions, blocks, ig, liveness_result


def _color_graph(
    ig: InterferenceGraph,
    k: int,
    instructions: list[TACInstruction],
) -> InterferenceGraph:
    """Chaitin's simplify-select graph coloring."""
    adj = defaultdict(set)
    for u, v in ig.edges:
        adj[u].add(v)
        adj[v].add(u)

    use_count = defaultdict(int)
    def_count = defaultdict(int)
    for instr in instructions:
        for v in instr.get_uses():
            use_count[v] += 1
        for v in instr.get_defs():
            def_count[v] += 1

    def spill_cost(v):
        return (use_count[v] + def_count[v]) / max(1, len(adj[v]))

    nodes = set(ig.variables)
    removed = set()
    stack = []
    potential_spills = set()

    # Simplify phase
    while nodes - removed:
        found = False
        for n in sorted(nodes - removed):
            degree = len(adj[n] - removed)
            if degree < k:
                stack.append(n)
                removed.add(n)
                found = True
                break
        if not found:
            # Optimistic spill: pick minimum cost node
            best = min(
                (nodes - removed),
                key=lambda n: spill_cost(n),
            )
            stack.append(best)
            removed.add(best)
            potential_spills.add(best)

    # Select phase
    colors = {}
    spilled = set()
    while stack:
        n = stack.pop()
        neighbor_colors = {colors[m] for m in adj[n] if m in colors}
        color = None
        for c in range(k):
            if c not in neighbor_colors:
                color = c
                break
        if color is not None:
            colors[n] = color
        else:
            spilled.add(n)

    ig.colors = colors
    ig.spilled = spilled
    return ig


def _rewrite_with_spills(
    instructions: list[TACInstruction],
    spilled: set[str],
    spill_offset_map: dict[str, int],
) -> list[TACInstruction]:
    """
    Insert load/store instructions for spilled variables.
    - Before each USE of a spilled var: insert a load from stack
    - After each DEF of a spilled var: insert a store to stack
    New temporary names are used (e.g., _spill_v_3) to avoid re-interference.
    """
    new_instructions = []
    idx = 0
    temp_counter = 0

    for instr in instructions:
        uses = instr.get_uses()
        defs = instr.get_defs()

        spilled_uses = uses & spilled
        spilled_defs = defs & spilled

        rename_map = {}

        # Insert loads before uses
        for v in sorted(spilled_uses):
            temp_name = f"_spill_{v}_{temp_counter}"
            temp_counter += 1
            rename_map[v] = temp_name
            load_instr = TACInstruction(
                index=idx,
                op="load_spill",
                dest=temp_name,
                arg1=str(spill_offset_map[v]),
            )
            new_instructions.append(load_instr)
            idx += 1

        # Rewrite instruction with renamed temps
        new_instr = TACInstruction(
            index=idx,
            op=instr.op,
            dest=instr.dest,
            arg1=rename_map.get(instr.arg1, instr.arg1) if instr.arg1 else None,
            arg2=rename_map.get(instr.arg2, instr.arg2) if instr.arg2 else None,
            label=instr.label,
            cmp_op=instr.cmp_op,
        )

        # If dest is spilled, rename it to a temp
        dest_temp = None
        if instr.dest in spilled:
            dest_temp = f"_spill_{instr.dest}_{temp_counter}"
            temp_counter += 1
            new_instr.dest = dest_temp

        new_instructions.append(new_instr)
        idx += 1

        # Insert store after def
        if dest_temp and instr.dest in spilled:
            store_instr = TACInstruction(
                index=idx,
                op="store_spill",
                arg1=dest_temp,
                arg2=str(spill_offset_map[instr.dest]),
            )
            new_instructions.append(store_instr)
            idx += 1

    return new_instructions


# Keep the old simple API for backward compat (used by app.py now through iterative version)
def allocate_registers(
    ig: InterferenceGraph,
    k: int,
    instructions: list[TACInstruction],
) -> InterferenceGraph:
    return _color_graph(ig, k, instructions)
