Script to generate index files for nightly images
=================================================

The script `generate-download-pages.py` can be used to generate index pages of nightly build directories for
download.haiku-os.org.

This is a script that should be run after each file upload to the nightly-images directories.

Requirements
------------

The requirements are python, the Mako_ library, and boto (for s3)

Config
------------

The script `generate-download-pages.py` reads a toml configuration to gain insight about s3 buckets that
contain nightly images. A sample is provided in `config-sample.toml`.

Each section gets deposited as a location in the index.html (europe, US, etc)

Bucket Layout
------------

The nightly images in the s3 buckets are generally laid out as follows:

(bucket)/(variant)/haiku-nightly-(hrevtag)-(variant)-(type).(zip|tar.xz)

.. _Mako: http://www.makotemplates.org
