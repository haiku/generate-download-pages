Script to generate index files for nightly images
=================================================

The script `generate-download-pages.py` can be used to generate index pages of nightly build directories for
download.haiku-os.org.

This is a script that should be run after each file upload to the nightly-images directories.

Requirements
------------

The requirements are python, the Mako_ library, boto (for s3), and hvac (for vault)

Config
------------

The script `generate-download-pages.py` connects to Hasicorp Vault and reads the
available s3 buckets containing our official nightly image mirrors.

Each section gets deposited as a location in the index.html (europe, US, etc)

Vault Layout
------------

Generate download pages obtains its secure list of s3 buckets from a deplpoyed
vault instance.

The format for the vault entries:

s3/nightly/(region)/...
  - bucket
  - endpoint (API URL)
  - public_url (User Access URL)
  - key
  - secret

Bucket Layout
------------

The nightly images in the s3 buckets are generally laid out as follows:

(bucket)/(variant)/haiku-nightly-(hrevtag)-(variant)-(type).(zip|tar.xz)

.. _Mako: http://www.makotemplates.org
