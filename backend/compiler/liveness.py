from dataclasses import dataclass, field
from collections import defaultdict
from .basic_blocks import BasicBlock
from .parser import TACInstruction


@dataclass
class LivenessResult:
    live_after: dict[int, set[str]] = field(default_factory=dict)
    live_before: dict[int, set[str]] = field(default_factory=dict)
    du_chains: dict[tuple[str, int], list[int]] = field(default_factory=dict)

    def to_dict(self):
        chains = []
        for (var, def_idx), use_indices in self.du_chains.items():
            chains.append({
                "variable": var,
                "def_index": def_idx,
                "use_indices": use_indices,
            })
        return {
            "du_chains": chains,
            "live_after": {str(k): sorted(v) for k, v in self.live_after.items()},
            "live_before": {str(k): sorted(v) for k, v in self.live_before.items()},
        }


def analyze_liveness(blocks: list[BasicBlock]) -> LivenessResult:
    """
    Iterative backward dataflow liveness analysis.
    Computes:
      - live_after: instruction index -> set of variables live AFTER that instruction
      - live_before: instruction index -> set of variables live BEFORE that instruction
      - du_chains: (variable, def_index) -> [use_indices] (def-use chains)
    Also updates each block's live_in and live_out.
    """
    for block in blocks:
        block.live_in = set()
        block.live_out = set()

    changed = True
    while changed:
        changed = False
        for block in reversed(blocks):
            old_in = block.live_in.copy()
            old_out = block.live_out.copy()

            block.live_out = set()
            for succ_id in block.successors:
                block.live_out |= blocks[succ_id].live_in

            live = block.live_out.copy()
            for instr in reversed(block.instructions):
                defs = instr.get_defs()
                uses = instr.get_uses()
                live = uses | (live - defs)

            block.live_in = live

            if block.live_in != old_in or block.live_out != old_out:
                changed = True

    live_after = {}
    live_before = {}
    for block in blocks:
        live = block.live_out.copy()
        for instr in reversed(block.instructions):
            live_after[instr.index] = live.copy()
            defs = instr.get_defs()
            uses = instr.get_uses()
            live = uses | (live - defs)
            live_before[instr.index] = live.copy()

    du_chains = _compute_du_chains(blocks)

    return LivenessResult(
        live_after=live_after,
        live_before=live_before,
        du_chains=du_chains,
    )


def _compute_du_chains(blocks: list[BasicBlock]) -> dict[tuple[str, int], list[int]]:
    """
    For each definition point (var, def_index), find all use points reachable
    without an intervening redefinition of that variable.
    Uses reaching-definitions style forward walk.
    """
    all_instructions = []
    for block in blocks:
        all_instructions.extend(block.instructions)
    all_instructions.sort(key=lambda i: i.index)

    defs_of = defaultdict(list)
    uses_of = defaultdict(list)
    for instr in all_instructions:
        for v in instr.get_defs():
            defs_of[v].append(instr.index)
        for v in instr.get_uses():
            uses_of[v].append(instr.index)

    du_chains: dict[tuple[str, int], list[int]] = {}

    for var in defs_of:
        for def_idx in defs_of[var]:
            reached_uses = []
            _find_uses_from_def(var, def_idx, blocks, reached_uses)
            du_chains[(var, def_idx)] = sorted(set(reached_uses))

    return du_chains


def _find_uses_from_def(
    var: str,
    def_idx: int,
    blocks: list[BasicBlock],
    reached_uses: list[int],
):
    """Walk forward from definition to find uses reached without redefinition."""
    idx_to_block = {}
    for block in blocks:
        for instr in block.instructions:
            idx_to_block[instr.index] = block

    start_block = idx_to_block[def_idx]

    in_start_block = False
    for instr in start_block.instructions:
        if instr.index == def_idx:
            in_start_block = True
            continue
        if not in_start_block:
            continue
        if var in instr.get_uses():
            reached_uses.append(instr.index)
        if var in instr.get_defs():
            return

    visited = set()
    worklist = list(start_block.successors)
    while worklist:
        bid = worklist.pop()
        if bid in visited:
            continue
        visited.add(bid)
        block = blocks[bid]
        killed = False
        for instr in block.instructions:
            if var in instr.get_uses():
                reached_uses.append(instr.index)
            if var in instr.get_defs():
                killed = True
                break
        if not killed:
            worklist.extend(block.successors)
