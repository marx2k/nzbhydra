from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from builtins import open
from future import standard_library
standard_library.install_aliases()
from builtins import *
import logging
from distutils.version import StrictVersion

import requests

version_txt_url = "https://raw.githubusercontent.com/theotherp/nzbhydra/master/version.txt"
repository_url = "https://github.com/theotherp/nzbhydra"

logger = logging.getLogger('root')


def check_for_new_version():
    if is_new_version_available():
        logger.info(("New version %s available at %s" % (get_current_version(), repository_url)))


def get_rep_version():
    try:
        r = requests.get(version_txt_url)
        r.raise_for_status()
        return StrictVersion(r.text)
    except requests.RequestException:
        logger.error("Error downloading version.txt from repository to check new updates")
        return None


def get_current_version():
    with open("version.txt", "r") as f:
        version = f.read()
    return StrictVersion(version)


def is_new_version_available():
    rep_version = get_rep_version()
    current_version = get_current_version()
    if rep_version is not None and current_version is not None:
        return rep_version > current_version
