import argparse
from collections import OrderedDict, namedtuple
import email.utils
import toml
import os
import re
import shutil
from urllib.parse import urlparse

import boto3

from mako.lookup import TemplateLookup

#
# Configuration
#

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates/")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output/")

S3_ENDPOINT_CONFIG = "nightly-s3.toml"

ARM_IMAGE_TYPES = (
    ("mmc", "SD Card Image"),
)

RISCV64_IMAGE_TYPES = (
    ("mmc", "SD Card Image"),
)

PPC_IMAGE_TYPES = (
    ("raw", "Raw Image"),
    ("boot_cd", "Boot CD"),
)

SPARC_IMAGE_TYPES = (
    ("raw", "Raw Image"),
)

IMAGE_TYPES = (
    # ("filename_type", "pretty type")
    ("anyboot", "Anyboot ISO"),
    #("raw", "Raw Image"),
    # ("cd", "Plain ISO"),
)

VARIANTS = (
    "arm",
    "m68k",
    "ppc",
    "riscv64",
    "sparc",
#    "x86",
    "x86_64",
    "x86_gcc2h",
#    "x86_gcc2",
#    "x86h",
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
    return boto3.client('s3',
        endpoint_url=endpoint,
        aws_access_key_id = key,
        aws_secret_access_key = secret)


def locate_images_arch(s3_connection, bucket, arch):
    objects = s3_connection.list_objects_v2(Bucket=bucket, Prefix=arch)
    if 'Contents' not in objects:
        return []

    # Expected storage: <arch>/nighty-image.zip
    s3files = [item['Key'] for item in objects['Contents']]
    while objects['IsTruncated'] == True:
        objects = s3_connection.list_objects_v2(Bucket=bucket, Prefix=arch, ContinuationToken=objects['NextContinuationToken'])
        if 'Contents' not in objects:
            break
        s3files += [item['Key'] for item in objects['Contents']]

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
    if variant == "riscv64":
        return list(q for _,q in RISCV64_IMAGE_TYPES)
    if variant == "sparc":
        return list(q for _,q in SPARC_IMAGE_TYPES)
    return list(q for _,q in IMAGE_TYPES)


def imageTypes(variant):
    if variant == "arm":
        return list(q for q,_ in ARM_IMAGE_TYPES)
    if variant == "ppc":
        return list(q for q,_ in PPC_IMAGE_TYPES)
    if variant == "riscv64":
        return list(q for q,_ in RISCV64_IMAGE_TYPES)
    if variant == "sparc":
        return list(q for q,_ in SPARC_IMAGE_TYPES)
    return list(q for q,_ in IMAGE_TYPES)


def index_archives(config, variant):

    # sort the images into a table-like structure that will be used to create the table
    type_columns = imageTypes(variant)
    content = OrderedDict()

    # populate a dict with the newest entry for each image type
    currentImages = {}
    locations = list(config.keys())
    revisions = []

    for location, info in config.items():
        images = {}

        if 's3_endpoint' in info:
            # locate images in s3 bucket
            print(("Probe s3 bucket in " + location + " for " + variant + "..."))
            s3 = connect_s3(info['s3_endpoint'], info['s3_key'], info['s3_secret'])
            images = locate_images_arch(s3, info['s3_bucket'], variant)
        # TODO: More endpoint types?

        if location not in list(content.keys()):
            content[location] = {}

        for image in images:
            if image.image_type not in type_columns:
                continue

            if image.revision not in list(content[location].keys()):
                content[location][image.revision] = {}

            content[location][image.revision][image.image_type] = image.filename
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
            for location in locations:
                # Each row has a location
                if location not in list(content.keys()):
                    continue
                local_config = config[location]
                local_info = content[location]
                if revision not in list(local_info.keys()):
                    # Location doesn't have this revision
                    continue
                local_revision = local_info[revision]
                if imagetype not in list(local_revision.keys()):
                    # Location doesn't have this imagetype
                    continue
                prefix = local_config['public_url'] + '/' + local_config['s3_bucket'] + '/' + variant + '/'
                if local_config['s3_vhost'] == True:
                    prefix = local_config['public_url'] + '/' + variant + '/'
                urls.update({location: prefix + local_revision[imagetype]})
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
        size = os.path.getsize(path) >> 20
        date = email.utils.formatdate(os.path.getmtime(path))
        rss_output.append(Entry(entry, date, size))
    return rss_output

#
# Main program
#

parser = argparse.ArgumentParser(description="Generate index files for Haiku Nightly Images hosting")
parser.add_argument('--config', dest='config_file', default=S3_ENDPOINT_CONFIG, action='store',
    help='toml document of known s3 buckets')
parser.add_argument('variant', nargs="*", help="build the pages for the specified variants")

if __name__ == "__main__":
    args = parser.parse_args()
    config = toml.load(args.config_file)

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
            print("WARNING: cannot find all supplied variants. Only building the known variants. Please check your input")

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

        result = index_archives(config, variant)

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
