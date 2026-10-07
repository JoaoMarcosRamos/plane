"""CI equivalence guard for structural kinds/config supported by backend and client."""
import ast
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / "apps/api/plane/radar/ontology/contracts.py"
registry = next(node.value for node in ast.parse(source.read_text()).body
    if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "PROPERTY_KINDS" for target in node.targets))
kinds = [ast.literal_eval(key) for key in registry.keys]
config = set().union(*(ast.literal_eval(value.args[0]) for value in registry.values))
client = (root / "apps/web/services/radar/types.ts").read_text()
section = re.search(r"RADAR_PROPERTY_KINDS\s*=\s*\[(.*?)\]\s*as const", client, re.S).group(1)
client_kinds = re.findall(r'"([a-z_]+)"', section)
client_config = re.search(r"config:\s*\{(.*?)\};", client, re.S).group(1)
config_keys = set(re.findall(r"(\w+)\?:", client_config))
assert kinds == client_kinds, (kinds, client_kinds)
assert config == config_keys, (config, config_keys)
cardinalities = next(ast.literal_eval(node.value) for node in ast.parse(source.read_text()).body
    if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "CARDINALITIES" for target in node.targets))
client_cardinalities = re.findall(r'"([01]\.\.[1n])"', re.search(r"cardinality:\s*(.*?);", client).group(1))
assert list(cardinalities) == client_cardinalities, (cardinalities, client_cardinalities)
print(f"RADAR contract parity: {len(kinds)} kinds and {len(config)} config keys and 3 cardinalities match.")

capabilities = root / "apps/api/plane/radar/commands/capabilities.py"
field_types = next(
    ast.literal_eval(node.value)
    for node in ast.parse(capabilities.read_text()).body
    if isinstance(node, ast.Assign)
    and any(isinstance(target, ast.Name) and target.id == "CAPABILITY_FIELD_TYPES" for target in node.targets)
)
client_section = re.search(r"RADAR_CAPABILITY_VALUE_TYPES\s*=\s*\[(.*?)\]\s*as const", client, re.S).group(1)
client_field_types = re.findall(r'"([a-z_]+)"', client_section)
assert list(field_types) == client_field_types, (field_types, client_field_types)
print(f"RADAR capability contract parity: {len(field_types)} field types match.")

identity_tree = ast.parse((root / "apps/api/plane/radar/runtime_identity.py").read_text())
strategies = next(
    node.value for node in identity_tree.body
    if isinstance(node, ast.Assign)
    and any(isinstance(target, ast.Name) and target.id == "IDENTITY_STRATEGIES" for target in node.targets)
)
strategy_names = [ast.literal_eval(key) for key in strategies.keys]
client_strategies = re.findall(r'"([a-z_0-9]+)"', re.search(r"identity: \{ strategy: (.*?);", client).group(1))
assert strategy_names == client_strategies, (strategy_names, client_strategies)
contexts = next(
    ast.literal_eval(node.value.args[0]) for node in identity_tree.body
    if isinstance(node, ast.Assign)
    and any(isinstance(target, ast.Name) and target.id == "CONTEXT_KINDS" for target in node.targets)
)
client_contexts = set(re.findall(r'"([a-z]+)"', re.search(r"contexts: \((.*?)\)\[\]", client).group(1)))
assert contexts == client_contexts, (contexts, client_contexts)
print(f"RADAR runtime contract parity: {len(strategy_names)} identity strategy and {len(contexts)} context kinds match.")
