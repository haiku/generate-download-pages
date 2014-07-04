import os
from mako.template import Template
from mako.lookup import TemplateLookup

#
# Configuration
#

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates/")
FILE_DIR = ""
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "OUTPUT/")

#
# Variants
#

VARIANTS = (
    # ("arch name (nice)", "html template", "location")
    ("Nightly Images", "gcc2-hybrid.html", "x86_gcc2_hybrid"),
)

#
# Process
#

if __name__ == "__main__":
    template_lookup = TemplateLookup(directories=[TEMPLATE_DIR])

    for variant in VARIANTS:
        template = template_lookup.get_template(variant[1])
        print template.render()
