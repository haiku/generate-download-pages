import argparse
from collections import defaultdict, OrderedDict, namedtuple
import email.utils
import os
import re

from mako.lookup import TemplateLookup

#
# Configuration
#

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates/")
ARCHIVE_DIR = "/srv/www/haikufiles/files/nightly-images/"
IMAGE_TYPES = (
    # ("filename_type", "pretty type")
    ("anyboot", "Anyboot"),
    ("vmware", "VMDK"),
    ("raw", "Raw"),
    ("cd", "ISO"),
)

#
# Common constants
#

VARIANTS = (
    # ("html template", "archives_location")
    ("gcc2-hybrid.html", "x86_gcc2_hybrid"),
    ("gcc2.html", "x86_gcc2"),
    ("gcc4.html", "x86_gcc4"),
    ("gcc4-hybrid.html", "x86_gcc4_hybrid"),
    ("x86_64.html", "x86_64"),
    ("arm.html", "arm"),
    ("m68k.html", "m68k"),
    ("ppc.html", "ppc"),
)

RE_IMAGE_PATTERN = re.compile(r'.*(hrev[0-9]*)-([^-]*)-([^\.]*)\.zip')

#
# Process data for the html
#

Image = namedtuple("Image", ['filename', 'revision', 'image_type'])
Row = type("Row", (object,), {})

def natural_sort_key(s, _nsre=re.compile('([0-9]+)')):
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(_nsre, s)]


def headers():
    return list(q for _,q in IMAGE_TYPES)


def index_archives(archive_dir):
    # reverse sort because we want the newest first
    # use natural sorting from when we switch from 5 digit hrev to 6 digits
    files = sorted(os.listdir(archive_dir), key=natural_sort_key, reverse=True)

    images = []
    for archive in files:
        m = RE_IMAGE_PATTERN.match(archive)
        if m:
            images.append(Image(archive, m.group(1), m.group(3)))

    # sort the images into a table-like structure that will be used to create the table
    variant_columns = list(q for q,_ in IMAGE_TYPES)
    content = OrderedDict()

    for image in images:
        if image.image_type not in variant_columns:
            print "Unknown image type for " + image.filename
            continue

        if image.revision not in content.keys():
            content[image.revision] = defaultdict(str)

        content[image.revision][image.image_type] = image.filename

    # flatten into a table
    table = []
    for revision, links in content.items():
        row = Row()
        row.revision = revision
        row.variants = []
        for variant in variant_columns:
            row.variants.append(links[variant])
        table.append(row)

    return table


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
parser.add_argument('--archive-dir', dest='archive_dir', default=ARCHIVE_DIR, action='store',
                    help="specify the directory with the images")

if __name__ == "__main__":
    args = parser.parse_args()

    template_lookup = TemplateLookup(directories=[TEMPLATE_DIR])

    for variant in VARIANTS:
        table = index_archives(os.path.join(args.archive_dir, variant[1]))

        # index html
        template = template_lookup.get_template(variant[0])
        out_f = open(os.path.join(args.archive_dir, variant[1], "index.html"), "w")
        out_f.write(template.render(headers=headers(), table=table))
        out_f.close()

        # rss
        template = template_lookup.get_template("rss.xml")
        out_f = open(os.path.join(args.archive_dir, variant[1], "rss", "atom.xml"), "w")
        out_f.write(template.render(arch=variant[1],
                                    items=index_files_for_rss(os.path.join(args.archive_dir, variant[1])),
                                    variant=variant[1]))
        out_f.close()