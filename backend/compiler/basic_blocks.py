from dataclasses import dataclass, field
from .parser import TACInstruction


@dataclass
class BasicBlock:
    id: int
    instructions: list[TACInstruction] = field(default_factory=list)
    successors: list[int] = field(default_factory=list)
    predecessors: list[int] = field(default_factory=list)
    live_in: set = field(default_factory=set)
    live_out: set = field(default_factory=set)

    def to_dict(self):
        return {
            "id": self.id,
            "instruction_indices": [i.index for i in self.instructions],
            "instructions_text": [_instr_text(i) for i in self.instructions],
            "successors": self.successors,
            "predecessors": self.predecessors,
            "live_in": sorted(self.live_in),
            "live_out": sorted(self.live_out),
        }


def _instr_text(instr: TACInstruction) -> str:
    if instr.op == "label":
        return f"{instr.label}:"
    if instr.op == "goto":
        return f"goto {instr.label}"
    if instr.op == "ifgoto":
        cmp_sym = instr.cmp_op or "cmp"
        return f"if {instr.arg1} {cmp_sym} {instr.arg2} goto {instr.label}"
    if instr.op == "return":
        return f"return {instr.arg1}"
    if instr.op == "param":
        return f"param {instr.arg1}"
    if instr.op == "call":
        return f"{instr.dest} = call {instr.arg1} {instr.arg2}"
    if instr.op == "assign":
        return f"{instr.dest} = {instr.arg1}"
    op_sym = {"add": "+", "sub": "-", "mul": "*", "div": "/",
              "lt": "<", "gt": ">", "eq": "==", "ne": "!=",
              "le": "<=", "ge": ">="}.get(instr.op, instr.op)
    return f"{instr.dest} = {instr.arg1} {op_sym} {instr.arg2}"


def build_basic_blocks(instructions: list[TACInstruction]) -> list[BasicBlock]:
    if not instructions:
        return []

    label_to_index = {}
    for instr in instructions:
        if instr.op == "label":
            label_to_index[instr.label] = instr.index

    leaders = {0}
    for instr in instructions:
        if instr.op in ("goto", "ifgoto"):
            target_idx = label_to_index.get(instr.label)
            if target_idx is not None:
                leaders.add(target_idx)
            next_idx = instr.index + 1
            if next_idx < len(instructions):
                leaders.add(next_idx)

    sorted_leaders = sorted(leaders)
    blocks = []

    for i, leader_idx in enumerate(sorted_leaders):
        end_idx = sorted_leaders[i + 1] if i + 1 < len(sorted_leaders) else len(instructions)
        block = BasicBlock(id=i)
        block.instructions = instructions[leader_idx:end_idx]
        for instr in block.instructions:
            instr.block_id = i
        blocks.append(block)

    idx_to_block = {}
    for block in blocks:
        for instr in block.instructions:
            idx_to_block[instr.index] = block.id

    for block in blocks:
        last = block.instructions[-1]
        if last.op == "goto":
            target_idx = label_to_index.get(last.label)
            if target_idx is not None and target_idx in idx_to_block:
                block.successors.append(idx_to_block[target_idx])
        elif last.op == "ifgoto":
            target_idx = label_to_index.get(last.label)
            if target_idx is not None and target_idx in idx_to_block:
                block.successors.append(idx_to_block[target_idx])
            next_idx = last.index + 1
            if next_idx in idx_to_block:
                block.successors.append(idx_to_block[next_idx])
        else:
            next_idx = last.index + 1
            if next_idx in idx_to_block:
                block.successors.append(idx_to_block[next_idx])

    for block in blocks:
        for succ_id in block.successors:
            blocks[succ_id].predecessors.append(block.id)

    return blocks


def build_cfg(blocks: list[BasicBlock]) -> list[dict]:
    edges = []
    for block in blocks:
        for succ_id in block.successors:
            edge_type = "sequential"
            last = block.instructions[-1]
            if last.op == "goto":
                edge_type = "jump"
            elif last.op == "ifgoto":
                label_target = last.label
                target_block = blocks[succ_id]
                if target_block.instructions and target_block.instructions[0].op == "label" and target_block.instructions[0].label == label_target:
                    edge_type = "branch"
                else:
                    edge_type = "fallthrough"
            edges.append({"from": block.id, "to": succ_id, "type": edge_type})
    return edges
