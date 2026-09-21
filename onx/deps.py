"""Conservative Gentoo dependency expression reader. Never execute ebuild text."""
import re

class Unsupported(ValueError):
    pass

def reduce(expression, flags, choices):
    # Tokens containing USE defaults '(+)' must remain intact.
    tokens = re.findall(r'\[[^\]]*\]|[^\s]+', expression)
    pos = 0

    def group(nested=False, active=True):
        nonlocal pos
        result = []
        while pos < len(tokens):
            token = tokens[pos]
            pos += 1
            if token == ')':
                if not nested:
                    raise Unsupported("unexpected closing parenthesis")
                return result
            if token in ('||', '^^', '??'):
                raise Unsupported("alternatives/cardinality require a reviewed upstream adapter: " + token)
            if token.endswith('?'):
                negate = token.startswith('!')
                flag = token[1:-1] if negate else token[:-1]
                if flag not in flags:
                    raise Unsupported("no explicit feature policy for " + flag)
                if pos == len(tokens) or tokens[pos] != '(':
                    raise Unsupported("missing conditional group")
                pos += 1
                enabled = bool(flags[flag]) != negate
                result += group(True, active and enabled)
            elif token == '(':
                raise Unsupported("unexpected opening parenthesis")
            elif active:
                result.append(token)
        if nested:
            raise Unsupported("unterminated dependency group")
        return result

    result = group()
    return result

def translate(atom, mapping):
    """Do not silently erase blockers, ABI slots, versions or USE requirements."""
    if '[' in atom or ':' in atom or atom.startswith(('!', '~')) or '*' in atom:
        raise Unsupported("dependency requires explicit translation: " + atom)
    m = re.fullmatch(r'(>=|<=|=|>|<)?([A-Za-z0-9+_.-]+/[A-Za-z0-9+_.-]+)', atom)
    if not m:
        raise Unsupported("unsupported dependency atom: " + atom)
    op, cp = m.groups()
    version = ''
    if op:
        match = re.fullmatch(r'(.+)-([0-9].*)', cp)
        if not match:
            raise Unsupported("versioned atom without version: " + atom)
        cp, version = match.groups()
    if cp not in mapping:
        raise Unsupported("missing Onlynux provider: " + cp)
    name = mapping[cp]
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9+_.-]*', name):
        raise Unsupported("invalid provider name")
    return name + (op + version if op else '')
