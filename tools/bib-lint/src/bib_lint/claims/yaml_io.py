"""Read agent-authored YAML without allowing duplicate keys or executable tags."""

from pathlib import Path

import yaml


class UniqueLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                raise ValueError("YAML mappings require unique string keys")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def read_yaml(path: Path):
    if path.is_symlink():
        raise ValueError(f"Refusing a symlinked YAML file: {path}")
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("Claims YAML exceeds the 64 MiB input limit")
    try:
        return yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader)
    except yaml.YAMLError as error:
        raise ValueError(f"Invalid YAML: {path.name}") from error


def fields(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f"{label} must contain exactly: {', '.join(expected)}")
