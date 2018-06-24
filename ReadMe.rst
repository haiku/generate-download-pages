Script to generate index files for nightly images
=================================================

The script `generate-download-pages.py` can be used to generate index pages of nightly build directories for
download.haiku-os.org.

This is a script that should be run after each file upload to the nightly-images directories.

Requirements
------------

The requirements are python, the Mako_ library, and boto (for s3)

Assumptions
-----------

This script makes many assumptions on the directory layout of the images, and the requested output. Best would be to
follow the contents of `generate-download-pages.py` to see which assumptions are made.


.. _Mako: http://www.makotemplates.org
