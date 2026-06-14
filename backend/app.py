from flask import Flask, request, jsonify, send_from_directory
import os

from compiler.parser import parse_tac
from compiler.basic_blocks import build_basic_blocks, build_cfg
from compiler.liveness import analyze_liveness
from compiler.interference_graph import build_interference_graph
from compiler.register_allocator import allocate_registers_iterative
from compiler.code_generator import generate_assembly

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), '..', 'frontend'))


@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/api/compile', methods=['POST'])
def compile_code():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body provided"}), 400

    code = data.get('code', '')
    k = data.get('num_registers', 4)

    if k not in (4, 8):
        return jsonify({"error": "num_registers must be 4 or 8"}), 400

    if not code.strip():
        return jsonify({"error": "No code provided"}), 400

    try:
        instructions = parse_tac(code)

        # Iterative register allocation with spill-rerun convergence
        final_instructions, blocks, ig, liveness_result = allocate_registers_iterative(
            instructions,
            build_basic_blocks,
            analyze_liveness,
            k,
        )

        cfg_edges = build_cfg(blocks)
        asm = generate_assembly(final_instructions, ig.colors, ig.spilled, k)

        register_map = {v: f"r{c}" for v, c in ig.colors.items()}
        for v in ig.spilled:
            register_map[v] = "spilled"

        # Filter out internal _spill_ temps from public-facing data
        public_ig = ig.to_dict()
        public_ig["nodes"] = [
            n for n in public_ig["nodes"] if not n["name"].startswith("_spill_")
        ]
        public_ig["edges"] = [
            e for e in public_ig["edges"]
            if not e["source"].startswith("_spill_") and not e["target"].startswith("_spill_")
        ]

        # Filter register_map
        public_reg_map = {
            v: r for v, r in register_map.items() if not v.startswith("_spill_")
        }

        return jsonify({
            "tac_instructions": [instr.to_dict() for instr in instructions],
            "final_instructions": [instr.to_dict() for instr in final_instructions],
            "basic_blocks": [block.to_dict() for block in blocks],
            "cfg_edges": cfg_edges,
            "interference_graph": public_ig,
            "register_map": public_reg_map,
            "assembly": asm,
            "num_registers": k,
            "spill_count": len(ig.spilled),
            "liveness": liveness_result.to_dict(),
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Internal error: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)
