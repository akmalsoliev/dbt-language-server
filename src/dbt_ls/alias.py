import re


def parse_aliases(text: str) -> dict[str, str]:
    aliases = {}
    for match in re.finditer(r"""\{{\s*ref\((['"])(\w+)\1\)\s*}}\s+(\w+)""", text):
        aliases[match.group(3)] = match.group(2)
    for match in re.finditer(
        r"""\{{\s*source\((['"])(\w+)\1,\s*(['"])(\w+)\3\)\s*}}\s+(\w+)""", text
    ):
        aliases[match.group(5)] = match.group(4)
    return aliases
