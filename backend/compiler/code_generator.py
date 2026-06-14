from .parser import TACInstruction, _is_constant


_OP_TO_ASM = {
    "add": "ADD",
    "sub": "SUB",
    "mul": "MUL",
    "div": "DIV",
}

_CMP_TO_BRANCH = {
    "lt": "BLT",
    "gt": "BGT",
    "eq": "BEQ",
    "ne": "BNE",
    "le": "BLE",
    "ge": "BGE",
}


def generate_assembly(
    instructions: list[TACInstruction],
    colors: dict[str, int],
    spilled: set[str],
    k: int,
) -> list[dict]:
    assembly = []

    def reg(var: str) -> str:
        if var in colors:
            return f"r{colors[var]}"
        return f"r{k - 1}"

    def emit(line: str, source_index: int, variables: list[str] = None):
        assembly.append({
            "line": line,
            "source_index": source_index,
            "variables": variables or [],
        })

    def operand(arg: str, source_index: int) -> str:
        if _is_constant(arg):
            return f"#{arg}"
        return reg(arg)

    for instr in instructions:
        si = instr.index
        involved = list((instr.get_defs() | instr.get_uses()) - {None})
        # Map _spill_X_N temp names back to original var for display
        orig_vars = []
        for v in involved:
            if v.startswith("_spill_"):
                parts = v.split("_")
                if len(parts) >= 3:
                    orig_vars.append(parts[2])
            else:
                orig_vars.append(v)
        involved = list(set(orig_vars))

        if instr.op == "load_spill":
            offset = instr.arg1
            dest_r = reg(instr.dest)
            emit(f"LDR {dest_r}, [sp, #{offset}]", si, involved)

        elif instr.op == "store_spill":
            src_r = reg(instr.arg1)
            offset = instr.arg2
            emit(f"STR {src_r}, [sp, #{offset}]", si, involved)

        elif instr.op == "label":
            emit(f"{instr.label}:", si, [])

        elif instr.op == "goto":
            emit(f"B {instr.label}", si, [])

        elif instr.op == "ifgoto":
            r1 = operand(instr.arg1, si)
            r2 = operand(instr.arg2, si)
            emit(f"CMP {r1}, {r2}", si, involved)
            cmp_map = {"<": "BLT", ">": "BGT", "==": "BEQ", "!=": "BNE", "<=": "BLE", ">=": "BGE"}
            branch = cmp_map.get(instr.cmp_op, "BNE")
            emit(f"{branch} {instr.label}", si, involved)

        elif instr.op == "return":
            src = operand(instr.arg1, si)
            if src != "r0":
                emit(f"MOV r0, {src}", si, involved)
            emit("RET", si, involved)

        elif instr.op == "param":
            src = operand(instr.arg1, si)
            emit(f"PUSH {src}", si, involved)

        elif instr.op == "call":
            emit(f"BL {instr.arg1}", si, involved)
            dest_reg = reg(instr.dest)
            if dest_reg != "r0":
                emit(f"MOV {dest_reg}, r0", si, involved)

        elif instr.op == "assign":
            src = operand(instr.arg1, si)
            dest_r = reg(instr.dest)
            if dest_r != src:
                emit(f"MOV {dest_r}, {src}", si, involved)

        elif instr.op in _OP_TO_ASM:
            r1 = operand(instr.arg1, si)
            r2 = operand(instr.arg2, si)
            dest_r = reg(instr.dest)
            emit(f"{_OP_TO_ASM[instr.op]} {dest_r}, {r1}, {r2}", si, involved)

        elif instr.op in _CMP_TO_BRANCH:
            r1 = operand(instr.arg1, si)
            r2 = operand(instr.arg2, si)
            dest_r = reg(instr.dest)
            emit(f"CMP {r1}, {r2}", si, involved)
            emit(f"MOV {dest_r}, #0", si, involved)
            emit(f"MOV{_CMP_TO_BRANCH[instr.op][1:]} {dest_r}, #1", si, involved)

    return assembly
