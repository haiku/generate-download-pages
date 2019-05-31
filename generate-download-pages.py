import argparse
from collections import defaultdict, OrderedDict, namedtuple
import email.utils
import hvac
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

VAULT_ENGINE_NAME = "s3"
VAULT_OBJECT_PREFIX = "nightly"

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates/")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output/")

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
# Vault Cache
#
CACHE = {}

#
# Process data for the html
#

Image = namedtuple("Image", ['filename', 'revision', 'image_type'])
Row = type("Row", (object,), {})

def vault_get(client, name, key):
    result = client.read("{}/{}/{}".format(VAULT_ENGINE_NAME, VAULT_OBJECT_PREFIX, name))
    if result is None:
        print("Warning: {}/{}/{} is missing!".format(VAULT_ENGINE_NAME, VAULT_OBJECT_PREFIX, name))
        return None
    else:
        return result['data'][key]

def vault_list(client, name):
    if name == None:
        result = client.list('{}/{}'.format(VAULT_ENGINE_NAME, VAULT_OBJECT_PREFIX))
    else:
        result = client.list('{}/{}/{}'.format(VAULT_ENGINE_NAME, VAULT_OBJECT_PREFIX, name))
    if result == None:
        return None
    return result['data']['keys']

def connect_s3(endpoint, key, secret):
    url_object = urlparse(endpoint)
    try:
        return boto.connect_s3(
            aws_access_key_id = key,
            aws_secret_access_key = secret,
            host = url_object.hostname,
            port = url_object.port,
            is_secure = url_object.scheme.startswith('https'),
            calling_format = boto.s3.connection.OrdinaryCallingFormat(),
            )
    except:
        return None

def locate_images_arch(s3_connection, bucket, arch):
    try:
        bucket = s3_connection.get_bucket(bucket, validate=True)
    except:
        return None

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


def index_archives(options, variant):
    print("using vault at {}".format(options.vault_endpoint))
    client = hvac.Client(url=options.vault_endpoint)
    if not client.is_authenticated():
        print("Error: Unable to authenticate to Vault!")
        sys.exit()

    regions = vault_list(client, None)
    if regions == None:
        print("Error: No regions found in Vault! {}/{}".format(VAULT_ENGINE_NAME, VAULT_OBJECT_PREFIX))
        sys.exit()

    # sort the images into a table-like structure that will be used to create the table
    type_columns = imageTypes(variant)
    content = OrderedDict()

    # populate a dict with the newest entry for each image type
    currentImages = {}
    revisions = []

    for region in regions:
        images = {}
        endpoint = vault_get(client, region, "endpoint")
        bucket = vault_get(client, region, "bucket")
        key = vault_get(client, region, "key")
        secret = vault_get(client, region, "secret")
        public_url = vault_get(client, region, "public_url")

        if endpoint == None or bucket == None or key == None or secret == None:
            print("Skipping " + region + " region. Incomplete s3 info!")
            continue

        s3 = connect_s3(endpoint, key, secret)
        if s3 == None:
            print("Warning: {} region s3 is unavailable. Skipping.".format(region))
            continue

        images = locate_images_arch(s3, bucket, variant)
        if images == None:
            print("Warning: {} region s3 is unavailable. Skipping.".format(region))
            continue

        print("Probe s3 bucket in " + region + " for " + variant + "...")

        if region not in content.keys():
            content[region] = {}

        for image in images:
            if image.image_type not in type_columns:
                continue

            if image.revision not in content[region].keys():
                content[region][image.revision] = {}

            content[region][image.revision][image.image_type] = image.filename
            if image.revision not in revisions:
                revisions.append(image.revision)

            if image.image_type not in currentImages:
                currentImages[image.image_type] = image.filename

    # flatten into a table
    table = []
    for revision in revisions:
        # Each Row has a revision
        row = Row()
        row.revision = revision
        row.variants = []
        row.mtime = 0
        for imagetype in type_columns:
            # Each row has an image type
            urls = {}
            for region in regions:
                # Each row has a region
                if region not in content.keys():
                    continue
                local_info = content[region]
                if revision not in local_info.keys():
                    # Location doesn't have this revision
                    continue
                local_revision = local_info[revision]
                if imagetype not in local_revision.keys():
                    # Location doesn't have this imagetype
                    continue
                prefix = public_url + '/' + bucket + '/' + variant + '/'
                urls.update({region: prefix + local_revision[imagetype]})
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
parser.add_argument('--vault-endpoint', dest='vault_endpoint', default="http://127.0.0.1:8200", action='store',
    help='vault endpoint for credentials')
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
    if not os.path.isdir(os.path.join(OUTPUT_DIR, "nightly-images")):
        os.makedirs(os.path.join(OUTPUT_DIR, "nightly-images"))
    shutil.copy(os.path.join(TEMPLATE_DIR, "root", "index.html"), OUTPUT_DIR)

    if not os.path.isdir(os.path.join(OUTPUT_DIR, "style")):
        os.makedirs(os.path.join(OUTPUT_DIR, "style"))
    shutil.rmtree(os.path.join(OUTPUT_DIR, "style"))
    shutil.copytree(os.path.join(TEMPLATE_DIR, "style"), os.path.join(OUTPUT_DIR, "style"))


    for variant in variants:
        index_output = os.path.join(OUTPUT_DIR, "nightly-images", variant)
        rss_output = os.path.join(OUTPUT_DIR, "nightly-images", variant, "rss")

        # make result paths
        if not os.path.isdir(index_output):
            os.makedirs(index_output)
        if not os.path.isdir(rss_output):
            os.makedirs(rss_output)

        result = index_archives(args, variant)

        # index html
        template = template_lookup.get_template(variant + '.html')
        index_path = os.path.join(OUTPUT_DIR, "nightly-images", variant, "index.html")
        out_f = open(index_path + uniqueSuffix, "w")
        out_f.write(template.render(headers=headers(variant), arch=variant, imageTypes=imageTypes(variant), table=result['table']))
        out_f.close()
        os.rename(index_path + uniqueSuffix, index_path)

        # rss
        template = template_lookup.get_template("rss.xml")
        rss_path = os.path.join(OUTPUT_DIR, "nightly-images", variant, "rss", "atom.xml")
        out_f = open(rss_path + uniqueSuffix, "w")
        out_f.write(template.render(arch=variant,
                                    items=index_files_for_rss(os.path.join(OUTPUT_DIR, "nightly-images", variant)),
                                    variant=variant))
        out_f.close()
        os.rename(rss_path + uniqueSuffix, rss_path)
