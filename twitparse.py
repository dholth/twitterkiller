#!/usr/bin/env python
# -*- encoding: utf-8 -*-

speaker = []

for line in file("twit192transcript.txt"):
    line = line.strip().decode('utf-8').replace(u'’', u"'")
    if line.startswith(u'*'):
        line = line[1:].split(u'*', 1)[-1]
    if not line.strip():
        for sentence in u' '.join(speaker).split(u'.'):
            s = sentence.strip().replace('*', '')
            if s:
                print s.encode('latin-1', 'replace')
        speaker = []
    else:
        speaker.append(line.strip())
