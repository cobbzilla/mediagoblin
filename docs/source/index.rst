.. MediaGoblin Documentation

   Written in 2011, 2012 by MediaGoblin contributors

   To the extent possible under law, the author(s) have dedicated all
   copyright and related and neighboring rights to this software to
   the public domain worldwide. This software is distributed without
   any warranty.

   You should have received a copy of the CC0 Public Domain
   Dedication along with this software. If not, see
   <http://creativecommons.org/publicdomain/zero/1.0/>.


===========================================
Welcome to GNU MediaGoblin's documentation!
===========================================

GNU MediaGoblin is a platform for sharing photos, video and other media
in an environment that respects our freedom and independence.

This is a Free Software project. It is built by contributors for all
to use and enjoy. If you're interested in contributing, see `the wiki
<https://web.archive.org/web/20200817190402/https://wiki.mediagoblin.org/>`_ which has pages that talk about the
ways someone can contribute.


Part 1: Site Administrator's Guide
==================================

This guide covers installing, configuring, deploying and running a GNU
MediaGoblin website.  It is written for site administrators.

.. toctree::
   :maxdepth: 1

   siteadmin/foreword
   siteadmin/about
   siteadmin/deploying
   siteadmin/production-deployments
   siteadmin/configuration
   siteadmin/upgrading
   siteadmin/media-types
   siteadmin/help
   siteadmin/relnotes
   siteadmin/theming
   siteadmin/plugins
   siteadmin/commandline-upload


.. _core-plugin-section:

Part 2: Core plugin documentation
=================================

.. toctree::
   :maxdepth: 1

   plugindocs/basic_auth
   plugindocs/flatpagesfile
   plugindocs/ldap
   plugindocs/openid
   plugindocs/persona
   plugindocs/raven
   plugindocs/sampleplugin
   plugindocs/subtitles
   plugindocs/trim_whitespace


Part 3: Plugin Writer's Guide
=============================

This guide covers writing new GNU MediaGoblin plugins.

.. toctree::
   :maxdepth: 1

   pluginwriter/foreward
   pluginwriter/quickstart
   pluginwriter/database
   pluginwriter/api
   pluginwriter/tests
   pluginwriter/hooks
   pluginwriter/media_type_hooks
   pluginwriter/authhooks


Part 4: Developer's Zone
========================

This chapter contains various information for developers.

.. toctree::
   :maxdepth: 1

   devel/codebase
   devel/storage
   devel/release
   devel/originaldesigndecisions
   devel/migrations


Part 5: Pump API
================

This chapter covers MediaGoblin's `Pump API
<https://github.com/e14n/pump.io/blob/master/API.md>`_ support.  (A
work in progress; full federation is not supported at the moment, but
media uploading works!  You can use something like
`PyPump <http://pypump.org>`_
to write MediaGoblin applications.)

.. toctree::
   :maxdepth: 1

   api/authentication
   api/activities
   api/objects



Indices and tables
==================

* :ref:`search`
* :ref:`genindex`

.. * :ref:`modindex`

This guide was built on |today|.
