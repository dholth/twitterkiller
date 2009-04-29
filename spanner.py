#!/usr/bin/python
# Span algorithm

def span(spans):
    """Note the last span won't include the end of the file."""
    i = iter(spans)
    last = i.next()
    for s in i:
        if s[0] != last[0]:
            yield (last[0], last[1], s[1])
            last = s
        else:
            pass
    # breaks if i is empty
    yield (last[0], last[1], s[1])

if __name__ == "__main__":
    import utterances
    import pprint
    pprint.pprint(list(span(utterances.utterances)))
