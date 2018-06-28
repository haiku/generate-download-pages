import argparse
from collections import defaultdict, OrderedDict, namedtuple
import email.utils
import os
import re
import sys
import shutil
import time

try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

import boto
import boto.s3.connection

from mako.lookup import TemplateLookup

#
# Configuration
#

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates/")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output/")
S3_BUCKET = "nightly"
S3_PATH = "/"
S3_PUBLIC = "https://cdn.haiku-os.org"
S3_ENDPOINT = ""

ARM_IMAGE_TYPES = (
    ("mmc", "SD Card Image"),
)

PPC_IMAGE_TYPES = (
    ("raw", "Raw Image"),
    ("boot_cd", "Boot CD"),
)

IMAGE_TYPES = (
    # ("filename_type", "pretty type")
    ("anyboot", "Anyboot ISO"),
    ("raw", "Raw Image"),
    # ("cd", "Plain ISO"),
)

VARIANTS = (
    "arm",
    "m68k",
    "ppc",
#    "x86",
    "x86_64",
    "x86_gcc2_hybrid",
#    "x86_gcc2",
#    "x86_hybrid",
)

#
# Common constants
#

RE_IMAGE_PATTERN = re.compile(r'.*(hrev[0-9]*)-([^-]*)-([^\.]*)\.(zip|tar\.xz)$')

#
# S3 Connection
#

#
# Process data for the html
#

Image = namedtuple("Image", ['filename', 'revision', 'image_type'])
Row = type("Row", (object,), {})

def connect_s3(endpoint, key, secret):
    url_object = urlparse(endpoint)
    return boto.connect_s3(
        aws_access_key_id = key,
        aws_secret_access_key = secret,
        host = url_object.netloc,
        is_secure = url_object.scheme.startswith('https'),
        calling_format = boto.s3.connection.OrdinaryCallingFormat(),
        )

def locate_images_arch(s3_connection, arch):
    bucket = s3_connection.get_bucket(S3_BUCKET, validate=True)
    # Expected storage: <arch>/nighty-image.zip
    s3files = [item.name for item in bucket.list()]
    s3files.sort(reverse=True)

    images = []
    for s3file in s3files:
        path_arch, filename = os.path.split(s3file)
        if path_arch.lower() != arch.lower():
            continue
        m = RE_IMAGE_PATTERN.match(filename)
        if m:
            images.append(Image(filename, m.group(1), m.group(3)))
    return images


def natural_sort_key(s, _nsre=re.compile('([0-9]+)')):
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(_nsre, s)]

def headers(variant):
    if variant == "arm":
        return list(q for _,q in ARM_IMAGE_TYPES)
    if variant == "ppc":
        return list(q for _,q in PPC_IMAGE_TYPES)
    return list(q for _,q in IMAGE_TYPES)


def imageTypes(variant):
    if variant == "arm":
        return list(q for q,_ in ARM_IMAGE_TYPES)
    if variant == "ppc":
        return list(q for q,_ in PPC_IMAGE_TYPES)
    return list(q for q,_ in IMAGE_TYPES)


def index_archives(images, variant):

    # sort the images into a table-like structure that will be used to create the table
    variant_columns = imageTypes(variant)
    content = OrderedDict()

    # populate a dict with the newest entry for each image type
    currentImages = {}

    for image in images:
        if image.image_type not in variant_columns:
            continue

        if image.revision not in content.keys():
            content[image.revision] = defaultdict(str)

        content[image.revision][image.image_type] = image.filename

        if image.image_type not in currentImages:
            currentImages[image.image_type] = image.filename

    url = S3_PUBLIC + "/" + S3_BUCKET + "/" + variant + "/"
    # flatten into a table
    table = []
    for revision, links in content.items():
        row = Row()
        row.revision = revision
        row.variants = []
        row.mtime = 0
        for variant in variant_columns:
            urls = {"europe": url + links[variant]}
            row.variants.append(urls)
        table.append(row)

    return {
#        'table' : filteredTable,
        'table' : table,
        'currentImages' : currentImages,
    }


#
# Process data for the rss
#

Entry = namedtuple("Entry", ['filename', 'date', 'size'])

def index_files_for_rss(archive_dir, limit=20):
    # reverse sort because we want the newest first
    # use natural sorting from when we switch from 5 digit hrev to 6 digits
    entries = sorted(os.listdir(archive_dir), key=natural_sort_key, reverse=True)
    rss_output = []
    for entry in entries:
        if not RE_IMAGE_PATTERN.match(entry):
            continue
        if len(rss_output) == limit:
            break
        path = os.path.join(archive_dir, entry)
        size = os.path.getsize(path) >> 20L
        date = email.utils.formatdate(os.path.getmtime(path))
        rss_output.append(Entry(entry, date, size))
    return rss_output

#
# Main program
#

parser = argparse.ArgumentParser(description="Generate index files for Haiku Nightly Images hosting")
parser.add_argument('--s3_endpoint', dest='s3endpoint', default=S3_ENDPOINT, action='store',
    help='S3 endpoint holding nightly images')
parser.add_argument('--s3_key', dest='s3key', default="", action='store', help='S3 key')
parser.add_argument('--s3_secret', dest='s3secret', default="", action='store', help='S3 secret')
parser.add_argument('variant', nargs="*", help="build the pages for the specified variants")

if __name__ == "__main__":
    args = parser.parse_args()

    uniqueSuffix = '.' + str(os.getpid())

    # check what to build
    if len(args.variant) == 0:
        variants = VARIANTS
    else:
        variants = []
        for variant in VARIANTS:
            if variant in args.variant:
                variants.append(variant)
        if len(variants) != len(args.variant):
            print "WARNING: cannot find all supplied variants. Only building the known variants. Please check your input"

    template_lookup = TemplateLookup(directories=[TEMPLATE_DIR])

    # Populate static assets
    if not os.path.isdir(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    shutil.copy(os.path.join(TEMPLATE_DIR, "root", "index.html"), OUTPUT_DIR)

    if not os.path.isdir(os.path.join(OUTPUT_DIR, "style")):
        os.makedirs(os.path.join(OUTPUT_DIR, "style"))
    shutil.rmtree(os.path.join(OUTPUT_DIR, "style"))
    shutil.copytree(os.path.join(TEMPLATE_DIR, "style"), os.path.join(OUTPUT_DIR, "style"))

    s3 = connect_s3(args.s3endpoint, args.s3key, args.s3secret)

    for variant in variants:
        # locate images in s3 bucket
        images = locate_images_arch(s3, variant)
        result = index_archives(images, variant)

        index_output = os.path.join(OUTPUT_DIR, variant)
        rss_output = os.path.join(OUTPUT_DIR, variant, "rss")

        # make result paths
        if not os.path.isdir(index_output):
            os.makedirs(index_output)
        if not os.path.isdir(rss_output):
            os.makedirs(rss_output)

        # index html
        template = template_lookup.get_template(variant + '.html')
        index_path = os.path.join(OUTPUT_DIR, variant, "index.html")
        out_f = open(index_path + uniqueSuffix, "w")
        out_f.write(template.render(headers=headers(variant), arch=variant, imageTypes=imageTypes(variant), table=result['table']))
        out_f.close()
        os.rename(index_path + uniqueSuffix, index_path)

        # rss
        template = template_lookup.get_template("rss.xml")
        rss_path = os.path.join(OUTPUT_DIR, variant, "rss", "atom.xml")
        out_f = open(rss_path + uniqueSuffix, "w")
        out_f.write(template.render(arch=variant,
                                    items=index_files_for_rss(os.path.join(OUTPUT_DIR, variant)),
                                    variant=variant))
        out_f.close()
        os.rename(rss_path + uniqueSuffix, rss_path)

        # write apache rewrite map file for current images
        map_path = os.path.join(OUTPUT_DIR, variant, "currentImages.map.fragment")
        out_f = open(map_path + uniqueSuffix, "w")
        for key, value in result['currentImages'].iteritems():
            out_f.write('%s/current-%s %s/%s\n' % (variant, key, variant, value))
            out_f.write('%s/current-%s.sha256 %s/%s.sha256\n' % (variant, key, variant, value))
        out_f.close()
        os.rename(map_path + uniqueSuffix, map_path)

        # write nginx rewrite map file for current images (has trailing semicolon)
        map_path = os.path.join(OUTPUT_DIR, variant, "currentImages.map.nginx.fragment")
        out_f = open(map_path + uniqueSuffix, "w")
        for key, value in result['currentImages'].iteritems():
            out_f.write('/nightly-images/%s/current-%s /nightly-images/%s/%s;\n' % (variant, key, variant, value))
            out_f.write('/nightly-images/%s/current-%s.sha256 /nightly-images/%s/%s.sha256;\n' % (variant, key, variant, value))
        out_f.close()
        os.rename(map_path + uniqueSuffix, map_path)

    # concatenate all fragments to full map file
    map_path = os.path.join(OUTPUT_DIR, "currentImages.map")
    os.system('cd "%s"; cat */currentImages.map.fragment >%s' % (OUTPUT_DIR, map_path + uniqueSuffix))
    os.rename(map_path + uniqueSuffix, map_path)
    # same for nginx
    map_path = os.path.join(OUTPUT_DIR, "currentImages.map.nginx")
    os.system('cd "%s"; cat */currentImages.map.nginx.fragment >%s' % (OUTPUT_DIR, map_path + uniqueSuffix))
    os.rename(map_path + uniqueSuffix, map_path)
