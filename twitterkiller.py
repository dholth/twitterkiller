#!/usr/bin/python
#
# Copyright (c) 2009 Daniel Holth <dholth@fastmail.fm>
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.

import gobject
gobject.threads_init()

import sys
import os.path

import pygtk
pygtk.require('2.0')
import gtk
import gtk.glade
import pygst
pygst.require('0.10')
import gst

class Main(object):
    def __init__(self):
        self.state = "START"
        self.keyword = "TWITTER"
        self.media = Media()
        self.setupWindow()
        self.window.show_all()

        self.aboutTree = None

    def about(self, widget):
        self.aboutDialog.show_all()

    def about_hide(self, widget):
        print "bye about"
        self.aboutDialog.hide()

    def setupWindow(self):
        self.wTree = gtk.glade.XML("twitterkiller.glade")
        self.window = self.wTree.get_widget("mainwindow")
        self.aboutDialog = self.wTree.get_widget("aboutdialog")
        self.window.connect("destroy", self.destroy)
        self.textview = self.wTree.get_widget("textview")
        self.textbuf = self.textview.get_buffer()
        self.statusbar = self.wTree.get_widget("statusbar")
        signals = { "on_file_activated": self.file_set,
                    "on_mainwindow_destroy": self.destroy,
                    "on_aboutmenu_activate": self.about, 
                    "on_aboutdialog_response": self.about_hide,
                    "on_file_open": self.file_open }
        self.wTree.signal_autoconnect(signals)
       
    def file_open(self, widget):
        """'Open' from the menu bar"""
        self.wTree.get_widget("filechooserbutton").activate()

    def file_set(self, widget):
        self.wTree.get_widget("file_open").set_sensitive(False)
        widget.set_sensitive(False)
        filenames = widget.get_filenames()
        c2w = self.media.convertToWav(filenames[0])
        pipeline, destination = c2w
        self.filename = filenames[0]
        self.intermediate = destination
        # if pipeline is None then we already have a .wav file
        if pipeline is None:
            self.find_keywords(destination)
            return
        bus = pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_wav_message, destination)
        self.pipeline = pipeline
        self.state = "TRANSCODE"
        self.statusbar.push(0, "Transcoding to .wav ...")
        pipeline.set_state(gst.STATE_PLAYING)

    def find_keywords(self, wavfile):
        """Find keywords from a .wav file."""
        print "Analyzing", wavfile
        pipeline = self.media.findKeywords(wavfile)
        self.state = "ANALYZE"
        self.statusbar.push(0, "Finding keywords in audio ...")
        bus = pipeline.get_bus()
        bus.connect("message", self.on_keywords_message)
        pipeline.set_state(gst.STATE_PLAYING)

    def on_wav_message(self, bus, message, data=None):
        t = message.type
        if t == gst.MESSAGE_APPLICATION:
            return
        elif t == gst.MESSAGE_ASYNC_DONE:
            print message
        elif t == gst.MESSAGE_EOS:
            print "Done transcoding to .wav"
            self.statusbar.pop(0)
            self.find_keywords(data)
        elif t == gst.MESSAGE_ERROR:
            print message

    def on_keywords_message(self, bus, message):
        t = message.type
        if t == gst.MESSAGE_APPLICATION:
            msgtype = message.structure.get_name()
            if msgtype == "result":
                hyp = message.structure['hyp']
                uttid = message.structure['uttid']
                self.textbuf.begin_user_action()
                i = self.textbuf.get_start_iter()
                if self.keyword not in hyp:
                    hyp = hyp.lower()                 
                self.textbuf.insert(i, "%s %s\n" % (uttid, hyp, ))
                self.textbuf.end_user_action()
        elif t == gst.MESSAGE_EOS:
            print "Done analyzing text"
            self.statusbar.pop(0)
            self.redact()

    def redact(self):
        """Output edited podcast"""
        pipeline = self.media.redact(self.intermediate)
        bus = pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_redact_message)
        self.statusbar.push(0, "Redacting keywords from original ...")
        pipeline.set_state(gst.STATE_PLAYING)
        self.redact_pipeline = pipeline        

    def on_redact_message(self, bus, message, data=None):
        t = message.type
        if t == gst.MESSAGE_EOS:
            print "Done editing."
            self.statusbar.pop(0)
            self.statusbar.push(0, "Finished!")
            self.redact_pipeline.set_state(gst.STATE_NULL)
            # self.destroy(self.window)
        else:
            print "Redact Message", t

    def destroy(self, widget, data=None):
        print "Goodbye"
        gtk.main_quit()

class Media(object):
    def __init__(self):
        self.utterances = []
    
    def convertToWav(self, filename):
        """Return (pipeline, destination_file_name) to convert filename to .wav
        Caller must start the pipeline. If filename is already .wav, return
        (None, filename).

        gstreamer cannot always seek MP3 depending on the installed
        plugins.  Probably using .wav for our many gnlfilesource also
        reduces overhead in the final gnonlin step. (needs mp3parse from
        -ugly to seek mp3)"""

        destination = os.path.extsep.join((os.path.splitext(filename)[0], "wav"))
        if os.path.exists(destination) and os.path.samefile(filename, destination):
            return (None, destination)
        else:
            pipeline = gst.parse_launch("filesrc name=mp3src ! decodebin ! audioconvert ! wavenc ! filesink name=wavsink")
            source = pipeline.get_by_name("mp3src")
            sink = pipeline.get_by_name("wavsink")
            source.set_property("location", filename)
            sink.set_property("location", destination)
            return (pipeline, destination)

    def findKeywords(self, filename, keyword="TWITTER"):
        """Locate spoken occurrences of keyword (always uppercase)
        in filename."""
        self.utterances = []
        self.bufferutts = []
        self.last_vs = 0
        self.last_ve = 0
        self.last_alt_position = 0
        self.last_hyp = ""
        self.last_uttid = ""
        self.keyword = keyword
      
        self.pipeline = gst.parse_launch(
                'filesrc name=input ! decodebin ! audioconvert '
              + '! audioresample '
              + '! vader name=vad auto-threshold=true '
              + '! pocketsphinx name=asr ! appsink sync=false name=appsink')
       
        src = self.pipeline.get_by_name("input")
        src.set_property("location", filename)

        self.appsink = self.pipeline.get_by_name("appsink")
        self.appsink.set_property("emit-signals", True)
        self.appsink.connect("new-buffer", self.new_buffer)

        vad = self.pipeline.get_by_name("vad")
        vad.connect("vader-start", self.vader_start)
        vad.connect("vader-stop", self.vader_end)

        asr = self.pipeline.get_by_name('asr')
        asr.connect('result', self.asr_result)
        asr.props.dict = '3286/3286.dic'
        asr.props.lm = '3286/3286.lm'
        # put additional information about each utterance, one file per
        # utterance, in latdir:
        # asr.props.latdir = '/tmp/lattice'
        asr.props.configured = True

        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        self.pipeline.set_state(gst.STATE_PAUSED) 
        return self.pipeline

    # The vader (voice activity detector) turned out to be the most
    # reliable way to find the start and end time of each utterance:
    def vader_start(self, vader, *args):
        self.last_vs = args[0]

    def vader_end(self, vader, *args):
        self.last_ve = args[0]

    def new_buffer(self, appsink):
        text = appsink.props.last_buffer.data
        timestamp = appsink.props.last_buffer.timestamp
        self.bufferutts.append((self.last_vs, text))

    def asr_partial_result(self, asr, text, uttid):
        """Forward partial result signals on the bus to the main thread."""
        struct = gst.Structure('partial_result')
        struct.set_value('hyp', text)
        struct.set_value('uttid', uttid)
        asr.post_message(gst.message_new_application(asr, struct))

    def asr_result(self, asr, text, uttid):
        """Forward result signals on the bus to the main thread."""
        struct = gst.Structure('result')
        struct.set_value('hyp', text)
        struct.set_value('uttid', uttid)
        asr.post_message(gst.message_new_application(asr, struct))

    def redact(self, source_file, editlist=None):
        butts = [(False, 0)] + [(self.keyword in text, timestamp) for timestamp, text in self.bufferutts]
        import spanner
        return self.edit(list(spanner.span(butts)))

    def edit(self, source_file, editlist=[]):
        """Edit source_file to include only segments from editlist,
        a list of (start, end) tuples.
        
        Return a paused gstreamer pipeline."""

        # identity single-segment=true ! " # buggy. should go right
        # before vorbisenc.
        pipeline = gst.parse_launch("gnlcomposition name=compo " 
            + " audioconvert name=landing ! wavenc ! " 
            + " filesink name=redacted")

        product = pipeline.get_by_name("redacted")
        product.set_property("location", os.path.splitext(source_file)[0] + ".redacted.wav")

        compo = pipeline.get_by_name("compo")
        self.landing_pad = pipeline.get_by_name("landing")

        elapsed = 0
        for span in editlist:
            start, end = span
                chunk_length = end - start
                if chunk_length == 0:
                    continue
                filesrc = gst.element_factory_make("gnlfilesource")
                filesrc.props.location = source_file
                filesrc.props.start = elapsed
                filesrc.props.duration = chunk_length
                filesrc.props.media_start = start
                filesrc.props.media_duration, chunk_length
                compo.add(filesrc)
                elapsed += chunk_length
  
        # Hangs if there are no spans.
        
        compo.props.start = 0
        compo.props.duration = elapsed 
        compo.props.media_start = 0
        compo.props.media_duration = elapsed

        compo.connect("pad-added", self.on_pad)
        pipeline.set_state(gst.STATE_PAUSED)
        return pipeline


    def on_pad(self, comp, pad):
        convpad = self.landing_pad.get_compatible_pad(pad, pad.get_caps())
        pad.link(convpad)

if __name__ == "__main__":
    start = Main()
    gtk.gdk.threads_enter()
    gtk.main()
    gtk.gdk.threads_leave()
