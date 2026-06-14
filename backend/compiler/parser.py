import re
from dataclasses import dataclass, field


@dataclass
class TACInstruction:
    index: int
    op: str
    dest: str | None = None
    arg1: str | None = None
    arg2: str | None = None
    label: str | None = None
    block_id: int | None = None
    cmp_op: str | None = None

    def to_dict(self):
        return {
            "index": self.index,
            "op": self.op,
            "dest": self.dest,
            "arg1": self.arg1,
            "arg2": self.arg2,
            "label": self.label,
            "block_id": self.block_id,
            "cmp_op": self.cmp_op,
        }

    def get_defs(self) -> set:
        if self.dest and not self.dest.startswith("#"):
            return {self.dest}
        return set()

    def get_uses(self) -> set:
        uses = set()
        for arg in (self.arg1, self.arg2):
            if arg and not _is_constant(arg):
                uses.add(arg)
        return uses


def _is_constant(s: str) -> bool:
    if s is None:
        return True
    try:
        int(s)
        return True
    except ValueError:
        try:
            float(s)
            return True
        except ValueError:
            return False


_OP_MAP = {
    "+": "add",
    "-": "sub",
    "*": "mul",
    "/": "div",
    "<": "lt",
    ">": "gt",
    "==": "eq",
    "!=": "ne",
    "<=": "le",
    ">=": "ge",
}


def parse_tac(code: str) -> list[TACInstruction]:
    lines = code.strip().split("\n")
    instructions = []
    idx = 0

    for line_num, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line or line.startswith("//") or line.startswith("#"):
            continue

        instr = _parse_line(line, idx)
        if instr is None:
            raise ValueError(f"Parse error at line {line_num + 1}: '{raw_line}'")
        instructions.append(instr)
        idx += 1

    return instructions


def _parse_line(line: str, idx: int) -> TACInstruction | None:
    # Label: "L1:"
    m = re.match(r"^(\w+):$", line)
    if m:
        return TACInstruction(index=idx, op="label", label=m.group(1))

    # goto L
    m = re.match(r"^goto\s+(\w+)$", line)
    if m:
        return TACInstruction(index=idx, op="goto", label=m.group(1))

    # if arg1 relop arg2 goto L
    m = re.match(r"^if\s+(\w+)\s*(==|!=|<=|>=|<|>)\s*(\w+)\s+goto\s+(\w+)$", line)
    if m:
        return TACInstruction(
            index=idx,
            op="ifgoto",
            arg1=m.group(1),
            arg2=m.group(3),
            label=m.group(4),
            dest=None,
            cmp_op=m.group(2),
        )

    # return arg
    m = re.match(r"^return\s+(\w+)$", line)
    if m:
        return TACInstruction(index=idx, op="return", arg1=m.group(1))

    # param arg
    m = re.match(r"^param\s+(\w+)$", line)
    if m:
        return TACInstruction(index=idx, op="param", arg1=m.group(1))

    # x = call f n
    m = re.match(r"^(\w+)\s*=\s*call\s+(\w+)\s+(\d+)$", line)
    if m:
        return TACInstruction(
            index=idx, op="call", dest=m.group(1), arg1=m.group(2), arg2=m.group(3)
        )

    # x = arg1 op arg2
    m = re.match(r"^(\w+)\s*=\s*(\w+)\s*([\+\-\*\/]|==|!=|<=|>=|<|>)\s*(\w+)$", line)
    if m:
        op_sym = m.group(3)
        op_name = _OP_MAP.get(op_sym, op_sym)
        return TACInstruction(
            index=idx, op=op_name, dest=m.group(1), arg1=m.group(2), arg2=m.group(4)
        )

    # x = arg (copy or constant assign)
    m = re.match(r"^(\w+)\s*=\s*(\w+)$", line)
    if m:
        return TACInstruction(
            index=idx, op="assign", dest=m.group(1), arg1=m.group(2)
        )

    return None
