Sauce Buildbot Integration
==========================

We were really excited to start using Saucelabs and set out to integrate it into
our standard CI. We initially used a manually backgrounded sauceconnect which we
killed at the end. However a lot of projects would need this so we decided to
package it up.

The package provides buildbot steps for using the Saucelabs service, including
a wrapper for sauce_connect and a test runner for summarising the test results.


Starting a Sauce Tunnel
-----------------------

As well as providing a simple wrapper around the sauce_connect script this step
will block until a tunnel has been correctly established. It will also transfer
sauce_connect to the slave if its not available. We try to avoid duplicating
support scripts to project repositories or adding manual setup steps to slave
setup.

To start a tunnel you use the StartSauceTunnel step::

    from isotoma.buildbot.sauceconnect import StartSauceTunnel
    f.addStep(StartSauceTunnel(
        username="your_username",
        api_key="your-api-key",
        host="127.0.0.1",
        domains="www.foo.com",
        ports=['80'],
        ))


Running Tests
-------------

You can run tests however you like, but if you want to make the test results available
from buildbot and available to people without your master saucelabs password you will
need some integration machinery.

The SauceTests step processes the logs from the test run and attaches a HTML summary
with access to images and videos of the test run. You can use it like so::

    from isotoma.buildbot.sauceconnect import SauceTests
    f.addStep(SauceTests(
        username="username",
        api_key="password",
        command="./bin/test",
        logfiles={"sauce.log": "sauce.log"},
        ))

It's expected that sauce.log will contain a list of tests, saucelab session ids
and the outcome of the test run. The relevant logs are fetched from saucelabs
and parsed. A summary with swishy ajax screenshot browsing and embedded videos is
generated and attached to the buildbot log.

This process is currently very limited: because it relies on saucelabs to host the
media it leaks your username/api-key and violates security restrictions in firefox.
To get around this we'll need to store the output images and videos ourselves. This
is coming in the near future, but until then it works just fine with Google Chrome.


Stopping a Sauce Tunnel
-----------------------

You'll want to stop the tunnel at the end of a build. Here's how::

    from isotoma.buildbot.sauceconnect import StopSauceTunnel
    f.addStep(StopSauceTunnel())

It will run even if there are failures earlier in the build to make sure there are no
stale tunnels left.


Using With Buildbot
-------------------

If you want to use these buildbot steps in a buildbot managed with buildout
you can just add it to the eggs list::

    [mymaster]
    recipe = isotoma.recipe.buildbot
    cfgfile = master.cfg
    eggs =
        isotoma.buildbot.sauceconnect


Repository
----------

This software is available from our `repository`_ on github.

.. _`repository`: http://github.com/isotoma/isotoma.buildbot.sauceconnect


License
-------

Copyright 2010 Isotoma Limited

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
