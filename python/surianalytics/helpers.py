"""
Reusable helper functions used by other widgets
"""

import subprocess


def escape(string):
    '''
    Escape other elasticsearch reserved characters
    '''
    return string. \
        replace('=', r'\='). \
        replace('+', r'\+'). \
        replace('-', r'\-'). \
        replace('&', r'\&'). \
        replace('|', r'\|'). \
        replace('!', r'\!'). \
        replace('(', r'\('). \
        replace(')', r'\)'). \
        replace('{', r'\{'). \
        replace('}', r'\}'). \
        replace('[', r'\['). \
        replace(']', r'\]'). \
        replace('^', r'\^'). \
        replace('"', r'\"'). \
        replace('~', r'\~'). \
        replace(':', r'\:'). \
        replace('/', r'\/'). \
        replace('\\', r'\\')


def check_str_bool(val: str) -> bool:
    if val in ("y", "yes", "t", "true", "on", "1", "enabled", "enable"):
        return True
    elif val in ("n", "no", "f", "false", "off", "0", "disabled", "disable"):
        return False
    else:
        raise ValueError("invalid truth value {}".format(val))


def get_git_root():
    return subprocess.Popen(['git', 'rev-parse', '--show-toplevel'],
                            stdout=subprocess.PIPE).communicate()[0].rstrip().decode('utf-8')


def escape_special_chars(text, characters):
    for character in characters:
        text = text.replace(character, '\\' + character)
    return text


def generate_aggs_terms(terms: dict | list | str, size: int) -> dict:
    agg = {}
    if isinstance(terms, dict):
        for term, values in terms.items():
            agg[term] = agg_term(term, size)
            agg[term]["aggs"] = generate_aggs_terms(values, size)
    elif isinstance(terms, list):
        for term in terms:
            agg[term] = agg_term(term, size)
    elif isinstance(terms, str):
        agg[terms] = agg_term(terms, size)

    return agg


def agg_term(term: str, size: int) -> dict:
    return {"terms": {"field": term, "size": size}}
