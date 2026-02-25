import json
from pathlib import Path


def test_capability_pack_specs_have_required_fields():
    root = Path('/home/vito/vito-agent/capability_packs')
    required = {"name", "category", "inputs", "outputs", "version", "risk_score", "tests_coverage", "acceptance_status"}
    for spec in root.glob('*/spec.json'):
        data = json.loads(spec.read_text(encoding='utf-8'))
        missing = required - set(data.keys())
        assert not missing, f"Missing {missing} in {spec}"
