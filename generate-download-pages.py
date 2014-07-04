import os
from mako.template import Template
from mako.lookup import TemplateLookup

#
# Configuration
#

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates/")
ARCHIVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "FILES", "nightly-images")

#
# Variants
#

VARIANTS = (
    # ("html template", "archives_location")
    ("gcc2-hybrid.html", "x86_gcc2_hybrid"),
)

#
# Process
#

if __name__ == "__main__":
    template_lookup = TemplateLookup(directories=[TEMPLATE_DIR])

    for variant in VARIANTS:
        template = template_lookup.get_template(variant[0])
        out_f = open(os.path.join(ARCHIVE_DIR, variant[1], "index.html"), "w")
        out_f.write(template.render())
