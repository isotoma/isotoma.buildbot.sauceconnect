# Copyright 2010 Isotoma Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Authors:
#  Tom Wardill <tom.wardill@isotoma.com>
#  John Carr <john.carr@isotoma.com>

import os
import base64
import StringIO

from twisted.internet import defer, reactor
from twisted.web.client import getPage
from twisted.python import log

from buildbot.process.buildstep import RemoteCommand, LoggingBuildStep, RemoteShellCommand
from buildbot.steps.shell import ShellCommand
from buildbot.steps.transfer import _FileReader, StatusRemoteCommand
from buildbot.interfaces import BuildSlaveTooOldError
from buildbot.status.builder import SUCCESS, WARNINGS, FAILURE, SKIPPED, \
     EXCEPTION, RETRY

from jinja2 import Template

def sibpath(path):
    return os.path.join(os.path.split(__file__)[0], path)


class StartSauceTunnel(LoggingBuildStep):

    """
    Download's support files needed to start a sauce tunnel to the slave then initiate
    a tunnel to saucelabs.com. This step completes when the tunnel is ready to use.

    Arguments::

     ['username'] saucelabs.com username
     ['api_key']  saucelabs.com api key
     ['host']     Host to forward requests to, default (=localhost).
     ['domains']   List of domains you want saucelabs to contact this build for, default (=None).
     ['ports']     List of ports to tunnel, default (=['80']).
    """

    name = "start-sauce-tunnel"
    description = "start-sauce-tunnel"
    flunkOnFailure = True
    haltOnFailure = True

    def __init__(self, username, api_key, host=None, domains=None, ports=None, **buildstep_kwargs):
        LoggingBuildStep.__init__(self, **buildstep_kwargs)
        self.addFactoryArguments(username=username,
            api_key=api_key,
            host=host,
            domains=domains,
            ports=ports,
            )

        # Load all the sauce_tunnel commands into a dict
        # We'll run this through properties.render() when they are needed
        self._sauce_args = a = {}
        a['u'] = username
        a['k'] = api_key
        if host:
            a['s'] = host
        if domains:
            a['d'] = domains
        if ports:
            a['p'] = ports

        self.full_workdir_path = ""

    def start(self):
        # Our slave must support at least downloadFile to work
        # FIXME: Should probably check for shell too, especially if upstream
        #   end up with multiple slave versions
        version = self.slaveVersion("downloadFile")
        if not version:
            m = "slave is too old, does not know about downloadFile"
            raise BuildSlaveTooOldError(m)

        # Download support files to slave
        d = self._push_sauce_tunnel()
        d.addCallback(self._push_sauce_tunnel_check)

        # Get the directory we are running in (start-stop-daemon expects a full path)
        d.addCallback(self._pwd)

        # Start a tunnel
        d.addCallback(self._start_sauce_tunnel)

        # If there was no fail, wait for it to come up
        def _proceed(res):
            if res == SUCCESS:
                return self._wait_for_sauce()
            return res
        d.addCallback(_proceed)

        # Deal with success or failure
        d.addCallback(self.finished).addErrback(self.failed)

    def startCommand(self, cmdname, cmd):
        self.cmd = cmd

        # Monitor stdio
        self.stdio_log = stdio_log = self.addLog("stdio")
        cmd.useLog(stdio_log, True)

        # Setup other logs files
        self.setupLogfiles(cmd, {"sauce_tunnel.log": "sauce_tunnel.log"})

        d = self.runCommand(cmd) # might raise ConnectionLost

        def _evaluate(cmd):
            if cmd.rc != 0:
                return FAILURE
            return SUCCESS
        d.addCallback(lambda res: _evaluate(cmd))

        return d

    def _transfer_file(self, path, mode):
        """ push a file to root of build area (i.e. outside of any checkout) """
        args = {
            "slavedest": os.path.split(path)[1],
            "maxsize": None,
            "reader": _FileReader(open(path, "rb")),
            "blocksize": 16*1024,
            "workdir": "",
            "mode": mode,
            }

        cmd = StatusRemoteCommand('downloadFile', args)
        d = self.runCommand(cmd)
        return d

    def _push_sauce_tunnel(self):
        return self._transfer_file(sibpath("sauce_tunnel"), 0755)

    def _push_sauce_tunnel_check(self, result):
        return self._transfer_file(sibpath("check.py"), 0755)

    def _pwd(self, res):
        cmd = RemoteShellCommand(".", "/bin/pwd")
        d = self.startCommand("pwd", cmd)
        def _get_stdio(res):
            self.full_workdir_path = cmd.logs['stdio'].getText().strip()
            return res
        d.addCallback(_get_stdio)
        return d

    def _start_sauce_tunnel(self, result):
        """ use start-stop-daemon to start sauce_tunnel """

        # start-stop-daemon until sauce_tunnel can self-background
        command = ["/sbin/start-stop-daemon", "--background", "--make-pidfile", "--start", "--quiet",
                   "--pidfile", "sauce_tunnel.pid", "--exec", "%s/sauce_tunnel" % self.full_workdir_path, "--"]

        # Maybe one day sauce_tunnel will self daemonize
        # command = ["./sauce_tunnel"]

        # 'render' the properties and assemble the shell command
        properties = self.build.getProperties()
        for key, val in self._sauce_args.iteritems():
            keyname = "-%s" % key
            if isinstance(val, (list, tuple)):
                for v in val:
                    command.extend([keyname, properties.render(v)])
            else:
                command.extend([keyname, properties.render(val)])

        # Set path to ready-file
        self.logfile = os.path.join(self.full_workdir_path, "sauce_tunnel.log")
        command.extend(["--logfile", self.logfile])

        # Set path to log file
        self.readyfile = os.path.join(self.full_workdir_path, "sauce_tunnel.ready")
        command.extend(["--readyfile", self.readyfile])

        cmd = RemoteShellCommand(".", command)
        return self.startCommand("start-tunnel", cmd)

    def _wait_for_sauce(self):
        command = ["./check.py"]
        cmd = RemoteShellCommand(".", command)
        return self.startCommand("wait-for-tunnel", cmd)


class StopSauceTunnel(LoggingBuildStep):

    """
    If you start a tunnel with StartSauceTunnel, you must close it with this.
    """

    name = "stop-sauce-tunnel"
    description = "stop-sauce-tunnel"
    flunkOnFailure = True
    haltOnFailure = True

    pidfile = "sauce_tunnel.pid"

    def start(self):
        command = ["/sbin/start-stop-daemon", "--stop", "--retry", "QUIT/10/QUIT/10/QUIT/10/KILL/10", "--pidfile", self.pidfile]
        cmd = RemoteShellCommand(".", command)
        d = self.runCommand(cmd)

        def _evaluate(cmd):
            if cmd.rc != 0:
                return FAILURE
            return SUCCESS
        d.addCallback(lambda res: _evaluate(cmd))
        d.addCallback(self.finished)
        d.addErrback(self.failed)


class SauceTests(ShellCommand):

    flunkOnFailure = True
    haltOnFailure = True

    def __init__(self, username, api_key, **kwargs):
        kwargs.setdefault('logfiles', {})['sauce.log'] = 'sauce.log'
        ShellCommand.__init__(self, **kwargs)
        self.addFactoryArguments(username=username,
            api_key=api_key,
            )

        self.username = username
        self.api_key = api_key

    def createSummary(self, log):
        d = self.process()
        def _add_summary(summary):
            self.addHTMLLog('summary', summary.encode("utf-8"))
        d.addCallback(_add_summary)
        return d

    @defer.inlineCallbacks
    def process(self):
        tests = []
        for id, line in enumerate(self.getLog("sauce.log").getText().strip().split("\n")):
            test, session, error = line.split("|")
            test = yield self.process_result(id, test, session, error)
            tests.append(test)

        # Map tracebacks from nose to logs, screenshots and videos from sauce
        tracebacks = self.parse_tracebacks()
        for test in tests:
           if test["test"] in tracebacks:
               test["traceback"] = tracebacks[test["test"]]

        template = Template(open(sibpath("summary.tmpl"),"r").read())
        summary = template.render(username=self.username, key=self.api_key, tests=tests)

        defer.returnValue(summary)

    @defer.inlineCallbacks
    def process_result(self, id, test, session, error):
        baseurl = "https://saucelabs.com/rest/%(u)s/jobs/%(s)s/results/" % {
            "u": self.username,
            "s": session,
            }
        baseurl_withauth = "https://%(u)s:%(k)s@saucelabs.com/rest/%(u)s/jobs/%(s)s/results/" % {
            "u": self.username,
            "k": self.api_key,
            "s": session,
            }

        selenium_log = baseurl_withauth + "selenium-server.log"
        video_flv = baseurl + "video.flv"

        headers = {
            "Authorization": "Basic " + base64.encodestring("%s:%s" % (self.username, self.api_key)).strip(),
            }

        log = yield getPage(baseurl + "selenium-server.log", headers=headers)

        fp = StringIO.StringIO(log)

        results = []

        line = fp.readline()[20:]
        while line:
            line, command, result, retval = self.parse_command(line, fp)

            line, shot = self.get_command(line, fp)

            # Might have one of these, might not:
            #17:08:04.280 INFO - Command request: captureScreenshot[shot_35.png, ] on session f53271cfce714e0080612387ada6fa7e

            screenshot = None
            if shot.startswith("captureScreenshot"):
                screenshot_num = shot[shot.find("[shot_")+6:shot.find(".png, ] on session ")-6]
                screenshot = "%s%sscreenshot.png" % (baseurl_withauth, screenshot_num.rjust(4, "0"))
                line, result, retval = self.get_result(line, fp)

            results.append(dict(command=command, result=result, retval=retval, screenshot=screenshot))

        screenshots = [x['screenshot'] for x in results if x['screenshot']]
        last_screenshot = ""
        if screenshots:
            last_screenshot = screenshots[-1]

        defer.returnValue(dict(id=id, test=test, session=session, error=error, results=results,
            last_screenshot=last_screenshot, video_flv=video_flv, selenium_log=selenium_log))

    def get_command(self, line, fp):
        while line and not line.startswith("Command request"):
            line = fp.readline()[20:]

        # Have a line that looks something like this:
        #17:08:04.248 INFO - Command request: click[//dl[@id='plone-contentmenu-workflow']/dt/a/span[3], ] on session f53271cfce714e0080612387ada6fa7e

        if line.startswith("Command request"):
            return line, line[17:line.find(" on session ")]

        return line, ""

    def get_result(self, line, fp):
        while line and not line.startswith("Got result"):
            line = fp.readline()[20:]

        # Have a line that looks something like this:
        #17:08:04.670 INFO - Got result: OK on session f53271cfce714e0080612387ada6fa7e

        result = line[12:line.find(" on session ")].strip()
        retval = None

        if result.startswith("OK,"):
            retval = result[3:]
            result = "OK"

        return line, result, retval

    def parse_command(self, line, fp):
        line, command = self.get_command(line, fp)
        line, result, retval = self.get_result(line, fp)

        return line, command, result, retval

    def parse_tracebacks(self):
        data = StringIO.StringIO(self.getLog("stdio").getText())

        start_marker = "======================================================================\n"
        eof_marker = "----------------------------------------------------------------------\n"

        # Find the first test
        line = data.readline()
        while line and line != start_marker:
            line = data.readline()

        tests = {}

        # Loop until end of stream
        while line:
            test_id = data.readline()
            test_id = test_id[test_id.find(":")+2:-1]

            traceback = []

            # skip a line (it should be -------------)
            data.readline()

            # Read until the next ====== (read until next test..)
            line = data.readline()
            while line and line != start_marker:
                # Nasty check for '-----------\nRan x tests in x seconds'
                if line == eof_marker:
                    line = data.readline()
                    if line.startswith("Ran "):
                        line = None
                        break
                    else:
                        traceback.append(eof_marker)

                traceback.append(line)
                line = data.readline()

            tests[test_id] = "".join(traceback)

        return tests

