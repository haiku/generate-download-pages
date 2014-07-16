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
ARCHIVE_DIR = "/srv/www/haikufiles/files/nightly-images"
IMAGE_TYPES = (
    # ("filename_type", "pretty type")
    ("anyboot", "Anyboot"),
    ("vmware", "VMDK"),
    ("raw", "Raw"),
    ("cd", "ISO"),
)

VARIANTS = (
    # ("html template", "archives_location")
    ("gcc2-hybrid.html", "x86_gcc2_hybrid"),
    ("gcc2.html", "x86_gcc2"),
    ("gcc4.html", "x86"),
    ("gcc4-hybrid.html", "x86_hybrid"),
    ("x86_64.html", "x86_64"),
    ("arm.html", "arm"),
    ("m68k.html", "m68k"),
    ("ppc.html", "ppc"),
)

#
# Common constants
#

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


def imageTypes():
    return list(q for q,_ in IMAGE_TYPES)


def index_archives(archive_dir):
    # reverse sort because we want the newest first
    # use natural sorting from when we switch from 5 digit hrev to 6 digits
    entries = sorted(os.listdir(archive_dir), key=natural_sort_key, reverse=True)

    images = []
    for entry in entries:
        m = RE_IMAGE_PATTERN.match(entry)
        if m:
            images.append(Image(entry, m.group(1), m.group(3)))

    # sort the images into a table-like structure that will be used to create the table
    variant_columns = list(q for q,_ in IMAGE_TYPES)
    content = OrderedDict()

    # populate a dict with the newest entry for each image type
    currentImages = {}

    for image in images:
        if image.image_type not in variant_columns:
            print "Unknown image type for " + image.filename
            continue

        if image.revision not in content.keys():
            content[image.revision] = defaultdict(str)

        content[image.revision][image.image_type] = image.filename

        if image.image_type not in currentImages:
            currentImages[image.image_type] = image.filename

    # flatten into a table
    table = []
    for revision, links in content.items():
        row = Row()
        row.revision = revision
        row.variants = []
        for variant in variant_columns:
            row.variants.append(links[variant])
        table.append(row)

    return {
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
parser.add_argument('--archive-dir', dest='archive_dir', default=ARCHIVE_DIR, action='store',
                    help="specify the directory with the images")
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
            if variant[1] in args.variant:
                variants.append(variant)
        if len(variants) != len(args.variant):
            print "WARNING: cannot find all supplied variants. Only building the known variants. Please check your input"

    template_lookup = TemplateLookup(directories=[TEMPLATE_DIR])

    for variant in variants:
        result = index_archives(os.path.join(args.archive_dir, variant[1]))

        # index html
        template = template_lookup.get_template(variant[0])
        index_path = os.path.join(args.archive_dir, variant[1], "index.html")
        out_f = open(index_path + uniqueSuffix, "w")
        out_f.write(template.render(headers=headers(), arch=variant[1], imageTypes=imageTypes(), table=result['table']))
        out_f.close()
        os.rename(index_path + uniqueSuffix, index_path)

        # rss
        template = template_lookup.get_template("rss.xml")
        rss_path = os.path.join(args.archive_dir, variant[1], "rss", "atom.xml")
        out_f = open(rss_path + uniqueSuffix, "w")
        out_f.write(template.render(arch=variant[1],
                                    items=index_files_for_rss(os.path.join(args.archive_dir, variant[1])),
                                    variant=variant[1]))
        out_f.close()
        os.rename(rss_path + uniqueSuffix, rss_path)

        # write apache rewrite map file for current images
        map_path = os.path.join(args.archive_dir, variant[1], "currentImages.map.fragment")
        out_f = open(map_path + uniqueSuffix, "w")
        for key, value in result['currentImages'].iteritems():
            out_f.write('%s/current-%s %s/%s\n' % (variant[1], key, variant[1], value))
        out_f.close()
        os.rename(map_path + uniqueSuffix, map_path)

    # concatenate all fragments to full map file
    map_path = os.path.join(args.archive_dir, "currentImages.map")
    os.system('cd "%s"; cat */currentImages.map.fragment >%s' % (args.archive_dir, map_path + uniqueSuffix))
    os.rename(map_path + uniqueSuffix, map_path)
