#!/usr/bin/python
# Span algorithm

def span(spans):
    """Merge adjacent spans with the same omit/don't omit
    status. spans is a list of (omit, start_time) tuples.
    Note the last span won't include the end of the file."""
    i = iter(spans)
    last = i.next()
    for s in i:
        if s[0] != last[0]:
            yield (last[0], last[1], s[1])
            last = s
        else:
            pass
    try:
        yield (last[0], last[1], s[1])
    except NameError:
        pass

if __name__ == "__main__":
    import utterances
    import pprint
    pprint.pprint(list(span(utterances.utterances)))
