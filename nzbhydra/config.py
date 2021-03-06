from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import copy

from builtins import open
from builtins import range
from builtins import str
from builtins import super
from future import standard_library


standard_library.install_aliases()
from builtins import *
from enum import Enum
import json
import logging
import os
import collections
import random
import string
from furl import furl

logger = logging.getLogger('root')


class Category(object):
    def __init__(self, parent, name, title=None):
        if not title:
            title = name
        self.parent = parent
        self.title = title
        self.categoryname = name
        self.children = []
        self.parent.add_category(self)

    @property
    def path(self):
        return "%s%s." % (self.parent.path, self.categoryname)  # Parent path already includes a dot (or not in case of the category root) 

    def get(self):
        return self.parent.get_category(self)

    def add_category(self, category):
        self.parent.get_category(self)[category.categoryname] = {}
        self.children.append(category)

    def add_setting(self, setting):
        self.parent.get_category(self)[setting.settingname] = setting.default
        if setting not in self.children:
            self.children.append(setting)

    def get_category(self, category):
        return self.get()[category.categoryname]

    def get_setting(self, setting):
        return self.get()[setting.settingname]

    def set_setting(self, setting, value):
        self.get()[setting.settingname] = value

    def __setattr__(self, key, value):
        if key != "children" and hasattr(self, "children") and key in [x.settingname for x in self.children if isinstance(x, Setting)] and not isinstance(value, Setting):
            # Allow setting a setting's value directly instead of using set(value)
            self.get()[key] = value
        else:
            return super(Category, self).__setattr__(key, value)

    def __getattribute__(self, *args, **kwargs):
        key = args[0]
        # todo maybe, only works with direct subsettings
        # if key != "children" and hasattr(self, "children") and key in [x.settingname for x in self.children if isinstance(x, Setting)]:
        #    return self.get()[key]

        return super(Category, self).__getattribute__(*args, **kwargs)


cfg = {}
config_file = None


class CategoryRoot(Category):
    def __init__(self):
        self.children = []
        pass

    @property
    def path(self):
        return ""

    def add_category(self, category):
        cfg[category.categoryname] = {}
        self.children.append(category)

    def add_setting(self, setting):
        cfg[setting.settingname] = setting
        self.children.append(setting)

    def get(self):
        return cfg

    def get_category(self, category):
        return cfg[category.categoryname]


config_root = CategoryRoot()


class SettingType(Enum):
    free = "free"
    password = "password"
    select = "select"
    multiselect = "multiselect"


class Setting(object):
    """
    A setting that has a category, name, a default value, a value type and a comment. These will be delegated to profig to read and set the actual config.
    This structure allows us indexed access to the settings anywhere in the code without having to use dictionaries with potentially wrong string keys.
    It also allows us to collect all settings and create a dict with all settings which can be serialized and sent to the GUI.
    """

    def __init__(self, parent, name, default, valuetype, title=None, description=None, setting_type=SettingType.free):
        self.parent = parent
        self.settingname = name
        self.default = default
        self.valuetype = valuetype
        self.description = description
        self.setting_type = setting_type
        self.title = title
        self.parent.add_setting(self)

    @property
    def path(self):
        return "%s%s" % (self.parent.path, self.settingname)  # Parent path already includes a trailing dot

    def get(self):
        # We delegate the getting of the actual value to the parent
        return self.parent.get_setting(self)

    def get_with_default(self, default):
        return self.get() if not None else default

    def set(self, value):
        self.parent.set_setting(self, value)

    def isSetting(self, value):
        return self.get() == value or self.get() == getattr(value, "name")

    def __str__(self):
        return "%s: %s" % (self.settingname, self.get())

    def __eq__(self, other):
        if not isinstance(other, Setting):
            return False
        return self.parent == other.parent and self.settingname == other.settingname


class SelectOption(object):
    def __init__(self, name, title):
        super(SelectOption, self).__init__()
        self.name = name
        self.title = title

    def __eq__(self, other):
        if isinstance(other, SelectOption):
            return self.name == other.name
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return self.name

    def __str__(self):
        return self.name


class SelectionSetting(Setting):
    def __init__(self, parent, name, default, valuetype, options, title=None, description=None, setting_type=SettingType.select):  # Warning is a mistake by PyCharm
        super(SelectionSetting, self).__init__(parent, name, default, valuetype, title, description, setting_type)
        self.options = options
        self.parent.get()[self.settingname] = self.default.name

    def get(self):
        return super(SelectionSetting, self).get()


class MultiSelectionSetting(Setting):
    def __init__(self, parent, name, default, valuetype, options, title=None, description=None, setting_type=SettingType.select):  # Warning is a mistake by PyCharm
        super(MultiSelectionSetting, self).__init__(parent, name, default, valuetype, title, description, setting_type)
        self.options = options
        self.parent.get()[self.settingname] = [x.name for x in self.default]

    def get(self):
        return super(MultiSelectionSetting, self).get()


class OrderedMultiSelectionSetting(Setting):
    def __init__(self, parent, name, default, valuetype, options, title=None, description=None, setting_type=SettingType.select):  # Warning is a mistake by PyCharm
        super(OrderedMultiSelectionSetting, self).__init__(parent, name, default, valuetype, title, description, setting_type)
        self.options = options
        self.parent.get()[self.settingname] = [x.name for x in self.default]

    def get(self):
        return super(OrderedMultiSelectionSetting, self).get()


logMessages = []


def addLogMessage(level, message):
    """
        Adds a log message to a list which can be logged after the logger was initialized 
    """
    global logMessages
    logMessages.append({"level": level, "message": message})


def logLogMessages():
    """
        Logs the messages that were created before the logger was initialized and then removes them from the list 
    """
    global logMessages
    for x in logMessages:
        logger.log(x["level"], x["message"])
    logMessages = []


def update(d, u, level):
    for k, v in u.items():

        if isinstance(v, collections.Mapping):
            r = update(d.get(k, {}), v, "%s.%s" % (level, k))
            d[k] = r
        else:
            if k in d.keys():
                d[k] = u[k]
            else:
                u.pop(k, None)
                addLogMessage(20, "Found obsolete setting %s.%s and will remove it" % (level, k))
    return d


def migrate(cfg):
    version = cfg["main"]["configVersion"]
    if version == 1:
        addLogMessage(20, "Migrating config to version 2")
        #Migrate sabnzbd setting
        sabnzbd = cfg["downloader"]["sabnzbd"]
        if sabnzbd["host"] and sabnzbd["port"]:
            addLogMessage(20, "Migrating sabnzbd settings")
            f = furl()
            f.host = sabnzbd["host"]
            f.port = sabnzbd["port"]
            f.scheme = "https" if sabnzbd["ssl"] else "http"
            f.path = "/sabnzbd/"
            cfg["downloader"]["sabnzbd"]["url"] = f.url
            addLogMessage(20, "Built sabnzbd URL: %s" % f.url)
        elif cfg["downloader"]["downloader"] == "sabnzbd":
            addLogMessage(30, "Unable to migrate from incomplete sabnzbd settings. Please set the sabnzbd URL manually")
        addLogMessage(20, "Migration of config to version 2 finished")
        cfg["main"]["configVersion"] = 2
        

def load(filename):
    global cfg
    global config_file
    config_file = filename
    if os.path.exists(filename):
        with open(filename) as f:
            loaded_config = json.load(f)
            migrate(loaded_config)
            cfg = update(cfg, loaded_config, level="root")
            pass


def import_config_data(data):
    global cfg
    global config_file
    cfg = data
    save(config_file)


def save(filename):
    global cfg
    with open(filename, "w", encoding="utf-8") as f:
        # json.dump(cfg, f, indent=4)
        f.write(unicode(json.dumps(cfg, ensure_ascii=False, indent=4)))


def get(setting):
    """
    Just a legacy way to access the setting 
    """
    return setting.get()


def set(setting, value):
    """
    Just a legacy way to set the setting 
    """
    setting.set(value)


class LoglevelSelection(object):
    critical = SelectOption("CRITICAL", "Critical")
    error = SelectOption("ERROR", "Error")
    warning = SelectOption("WARNING", "Warning")
    info = SelectOption("INFO", "Info")
    debug = SelectOption("DEBUG", "Debug")

    options = [critical, error, warning, info, debug]


class LoggingSettings(Category):
    def __init__(self, parent):
        super(LoggingSettings, self).__init__(parent, "logging", "Logging")
        self.logfilename = Setting(self, name="logfile-filename", default="nzbhydra.log", valuetype=str)
        self.logfilelevel = SelectionSetting(self, name="logfile-level", default=LoglevelSelection.info, valuetype=str, options=LoglevelSelection.options)
        self.consolelevel = SelectionSetting(self, name="consolelevel", default=LoglevelSelection.info, valuetype=str, options=LoglevelSelection.options)


class CacheTypeSelection(object):
    file = SelectOption("file", "Cache on the file system")
    memory = SelectOption("memory", "Cache in the memory during runtime")


class MainSettings(Category):
    """
    The main settings of our program.
    """

    def __init__(self):
        super(MainSettings, self).__init__(config_root, "main", "Main")
        self.host = Setting(self, name="host", default="0.0.0.0", valuetype=str)
        self.port = Setting(self, name="port", default=5075, valuetype=int)
        self.baseUrl = Setting(self, name="baseUrl", default=None, valuetype=str)
        self.startup_browser = Setting(self, name="startupBrowser", default=True, valuetype=bool)

        self.enableAuth = Setting(self, name="enableAuth", default=False, valuetype=bool)
        self.username = Setting(self, name="username", default="", valuetype=str)
        self.password = Setting(self, name="password", default="", valuetype=str)
        self.enableAdminAuth = Setting(self, name="enableAdminAuth", default=False, valuetype=bool)
        self.adminUsername = Setting(self, name="adminUsername", default="", valuetype=str)
        self.adminPassword = Setting(self, name="adminPassword", default="", valuetype=str)
        self.apikey = Setting(self, name="apikey", default=''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(30)), valuetype=str)
        self.enableAdminAuthForStats = Setting(self, name="enableAdminAuthForStats", default=False, valuetype=bool)

        self.ssl = Setting(self, name="ssl", default=False, valuetype=bool)
        self.sslcert = Setting(self, name="sslcert", default="nzbhydra.crt", valuetype=str)
        self.sslkey = Setting(self, name="sslkey", default="nzbhydra.key", valuetype=str)

        self.debug = Setting(self, name="debug", default=False, valuetype=bool)
        self.cache_enabled = Setting(self, name="enableCache", default=True, valuetype=bool)
        self.cache_type = SelectionSetting(self, name="cacheType", default=CacheTypeSelection.memory, valuetype=str, options=[CacheTypeSelection.memory, CacheTypeSelection.file])
        self.cache_timeout = Setting(self, name="cacheTimeout", default=30, valuetype=int)
        self.cache_threshold = Setting(self, name="cachethreshold", default=25, valuetype=int)
        self.cache_folder = Setting(self, name="cacheFolder", default="cache", valuetype=str)

        self.logging = LoggingSettings(self)

        # Not a config setting but the version of the config file. Useful when we may need to migrate the config later and want
        # to find out which version is used.
        self.configVersion = Setting(self, name="configVersion", default=1, valuetype=int)


mainSettings = MainSettings()


class HtmlParserSelection(object):
    html = SelectOption("html.parser", "Default BS (slow)")
    lxml = SelectOption("lxml", "LXML (faster, needs to be installed separately)")

    options = [html, lxml]


class InternalExternalSelection(object):
    internal = SelectOption("internal", "Internal searches")
    external = SelectOption("external", "API searches")
    options = [internal, external]


class CategorySizeSettings(Category):
    def __init__(self, parent):
        super(CategorySizeSettings, self).__init__(parent, "categorysizes", "Category sizes")
        self.enable_category_sizes = Setting(self, name="enable_category_sizes", default=True, valuetype=bool)

        self.movieMin = Setting(self, name="moviesmin", default=500, valuetype=int)
        self.movieMax = Setting(self, name="moviesmax", default=20000, valuetype=int)

        self.moviehdMin = Setting(self, name="movieshdmin", default=2000, valuetype=int)
        self.moviehdMax = Setting(self, name="movieshdmax", default=20000, valuetype=int)

        self.moviesdMin = Setting(self, name="moviessdmin", default=500, valuetype=int)
        self.moviesdMax = Setting(self, name="movieshdmin", default=3000, valuetype=int)

        self.tvMin = Setting(self, name="tvmin", default=50, valuetype=int)
        self.tvMax = Setting(self, name="tvmax", default=5000, valuetype=int)

        self.tvhdMin = Setting(self, name="tvhdmin", default=300, valuetype=int)
        self.tvhdMax = Setting(self, name="tvhdmax", default=3000, valuetype=int)

        self.tvsdMin = Setting(self, name="tvsdmin", default=50, valuetype=int)
        self.tvsdMax = Setting(self, name="tvsdmax", default=1000, valuetype=int)

        self.audioMin = Setting(self, name="audiomin", default=1, valuetype=int)
        self.audioMax = Setting(self, name="audiomax", default=2000, valuetype=int)

        self.audioflacmin = Setting(self, name="flacmin", default=10, valuetype=int)
        self.audioflacmax = Setting(self, name="flacmax", default=2000, valuetype=int)

        self.audiomp3min = Setting(self, name="mp3min", default=1, valuetype=int)
        self.audiomp3max = Setting(self, name="mp3max", default=500, valuetype=int)

        self.consolemin = Setting(self, name="consolemin", default=100, valuetype=int)
        self.consolemax = Setting(self, name="consolemax", default=40000, valuetype=int)

        self.pcmin = Setting(self, name="pcmin", default=100, valuetype=int)
        self.pcmax = Setting(self, name="pcmax", default=50000, valuetype=int)

        self.xxxmin = Setting(self, name="xxxmin", default=100, valuetype=int)
        self.xxxmax = Setting(self, name="xxxmax", default=10000, valuetype=int)

        self.ebookmin = Setting(self, name="ebookmin", default=None, valuetype=int)
        self.ebookmax = Setting(self, name="ebookmax", default=100, valuetype=int)


class SearchingSettings(Category):
    """
    How searching is executed.
    """

    def __init__(self):
        super(SearchingSettings, self).__init__(config_root, "searching", "Searching")
        self.timeout = Setting(self, name="timeout", default=20, valuetype=int)
        self.ignore_disabled = Setting(self, name="ignoreTemporarilyDisabled", default=False, valuetype=bool)
        self.generate_queries = MultiSelectionSetting(self, name="generate_queries", default=[InternalExternalSelection.internal], options=InternalExternalSelection.options, valuetype=str, setting_type=SettingType.multiselect)
        self.user_agent = Setting(self, name="userAgent", default="NZBHydra", valuetype=str)

        self.duplicateSizeThresholdInPercent = Setting(self, name="duplicateSizeThresholdInPercent", default=0.1, valuetype=float)
        self.duplicateAgeThreshold = Setting(self, name="duplicateAgeThreshold", default=3600, valuetype=int)
        self.removeDuplicatesExternal = Setting(self, name="removeDuplicatesExternal", default=True, valuetype=bool)
        self.htmlParser = SelectionSetting(self, name="htmlParser", default=HtmlParserSelection.html, valuetype=str, options=HtmlParserSelection.options)

        self.category_sizes = CategorySizeSettings(self)


searchingSettings = SearchingSettings()


class NzbAccessTypeSelection(object):
    serve = SelectOption("serve", "Proxy the NZBs from the indexer")
    redirect = SelectOption("redirect", "Redirect to the indexer")
    direct = SelectOption("direct", "Use direct links to the indexer")


class NzbAddingTypeSelection(object):
    link = SelectOption("link", "Send link to NZB")
    nzb = SelectOption("nzb", "Upload NZB")


class DownloaderSelection(object):
    none = SelectOption("none", "None")
    sabnzbd = SelectOption("sabnzbd", "SabNZBd")
    nzbget = SelectOption("nzbget", "NZBGet")


class DownloaderSettings(Category):
    def __init__(self):
        super(DownloaderSettings, self).__init__(config_root, "downloader", "Downloader")
        self.nzbaccesstype = SelectionSetting(self, name="nzbaccesstype", default=NzbAccessTypeSelection.serve, valuetype=str, options=[NzbAccessTypeSelection.direct, NzbAccessTypeSelection.redirect, NzbAccessTypeSelection.serve])
        self.nzbAddingType = SelectionSetting(self, name="nzbAddingType", default=NzbAddingTypeSelection.nzb, valuetype=str, options=[NzbAddingTypeSelection.link, NzbAddingTypeSelection.nzb])
        self.downloader = SelectionSetting(self, name="downloader", default=DownloaderSelection.none, valuetype=str, options=[DownloaderSelection.nzbget, DownloaderSelection.sabnzbd])


downloaderSettings = DownloaderSettings()


class SabnzbdSettings(Category):
    def __init__(self):
        super(SabnzbdSettings, self).__init__(downloaderSettings, "sabnzbd", "SabNZBD")
        #self.host = Setting(self, name="host", default="127.0.0.1", valuetype=str)
        #self.port = Setting(self, name="port", default=8080, valuetype=int)
        #self.ssl = Setting(self, name="ssl", default=False, valuetype=bool)
        self.url = Setting(self, name="url", default="http://localhost:8080/sabnzbd/", valuetype=str)
        self.apikey = Setting(self, name="apikey", default=None, valuetype=str)
        self.username = Setting(self, name="username", default=None, valuetype=str)
        self.password = Setting(self, name="password", default=None, valuetype=str)
        self.default_category = Setting(self, name="defaultCategory", default=None, valuetype=str)


sabnzbdSettings = SabnzbdSettings()


class NzbgetSettings(Category):
    def __init__(self, parent):
        super(NzbgetSettings, self).__init__(parent, "nzbget", "NZBGet")
        self.host = Setting(self, name="host", default="127.0.0.1", valuetype=str)
        self.port = Setting(self, name="port", default=6789, valuetype=int)
        self.ssl = Setting(self, name="ssl", default=False, valuetype=bool)
        self.username = Setting(self, name="username", default="nzbget", valuetype=str)
        self.password = Setting(self, name="password", default="tegbzn6789", valuetype=str)
        self.default_category = Setting(self, name="defaultCategory", default=None, valuetype=str)


nzbgetSettings = NzbgetSettings(downloaderSettings)


class SearchIdSelection(object):
    rid = SelectOption("rid", "TvRage ID")
    tvdbid = SelectOption("tvdbid", "TVDB ID")
    imdbid = SelectOption("imdbid", "IMDB ID")


class IndexerSettingsAbstract(Category):
    def __init__(self, parent, name, title):
        super(IndexerSettingsAbstract, self).__init__(parent, name, title)
        self.name = Setting(self, name="name", default=None, valuetype=str)
        self.host = Setting(self, name="host", default=None, valuetype=str)
        self.enabled = Setting(self, name="enabled", default=True, valuetype=bool)
        self.search_ids = MultiSelectionSetting(self, name="search_ids", default=[], valuetype=list,
                                                options=[SearchIdSelection.imdbid, SearchIdSelection.rid, SearchIdSelection.tvdbid],
                                                setting_type=SettingType.multiselect)
        self.score = Setting(self, name="score", default=0, valuetype=str)
        self.timeout = Setting(self, name="timeout", default=None, valuetype=int)
        self.show_on_search = Setting(self, name="showOnSearch", default=True, valuetype=bool)
        self.preselect = Setting(self, name="preselect", default=True, valuetype=bool)


class IndexerBinsearchSettings(IndexerSettingsAbstract):
    def __init__(self, parent):
        super(IndexerBinsearchSettings, self).__init__(parent, "Binsearch", "Binsearch")
        self.host = Setting(self, name="host", default="https://binsearch.info", valuetype=str)
        self.name = Setting(self, name="name", default="Binsearch", valuetype=str)


class IndexerOmgWtfSettings(IndexerSettingsAbstract):
    def __init__(self, parent):
        super(IndexerOmgWtfSettings, self).__init__(parent, "omgwtfnzbs", "omgwtfnzbs.org")
        self.host = Setting(self, name="host", default="https://api.omgwtfnzbs.org", valuetype=str)
        self.name = Setting(self, name="name", default="omgwtfnzbs.org", valuetype=str)
        self.username = Setting(self, name="username", default="", valuetype=str)
        self.apikey = Setting(self, name="apikey", default="", valuetype=str)
        self.enabled = Setting(self, name="enabled", default=False, valuetype=bool)


class IndexerNewznabSettings(IndexerSettingsAbstract):
    def __init__(self, parent, name, title):
        super(IndexerNewznabSettings, self).__init__(parent, name, title)
        self.apikey = Setting(self, name="apikey", default=None, valuetype=str)
        self.search_ids = MultiSelectionSetting(self, name="search_ids", default=[SearchIdSelection.imdbid, SearchIdSelection.rid, SearchIdSelection.tvdbid], valuetype=list,
                                                options=[SearchIdSelection.imdbid, SearchIdSelection.rid, SearchIdSelection.tvdbid],
                                                setting_type=SettingType.multiselect)
        self.enabled = Setting(self, name="enabled", default=False, valuetype=bool)  # Disable by default because we have no meaningful initial data


class IndexerNzbclubSettings(IndexerSettingsAbstract):
    def __init__(self, parent):
        super(IndexerNzbclubSettings, self).__init__(parent, "NZBClub", "NZBClub")
        self.host = Setting(self, name="host", default="https://nzbclub.com", valuetype=str)
        self.name = Setting(self, name="name", default="NZBClub", valuetype=str)


class IndexerNzbindexSettings(IndexerSettingsAbstract):
    def __init__(self, parent):
        super(IndexerNzbindexSettings, self).__init__(parent, "NZBIndex", "NZBIndex")
        self.host = Setting(self, name="host", default="https://nzbindex.com", valuetype=str)
        self.name = Setting(self, name="name", default="NZBIndex", valuetype=str)
        self.general_min_size = Setting(self, name="generalMinSize", default=1, valuetype=int)


class IndexerWombleSettings(IndexerSettingsAbstract):
    def __init__(self, parent):
        super(IndexerWombleSettings, self).__init__(parent, "Womble", "Womble")
        self.host = Setting(self, name="host", default="https://newshost.co.za", valuetype=str)
        self.name = Setting(self, name="name", default="Womble", valuetype=str)
        self.show_on_search = Setting(self, name="showOnSearch", default=False, valuetype=bool)


class IndexerSettings(Category):
    def __init__(self):
        super(IndexerSettings, self).__init__(config_root, "indexers", "Indexer")
        self.binsearch = IndexerBinsearchSettings(self)
        self.nzbclub = IndexerNzbclubSettings(self)
        self.nzbindex = IndexerNzbindexSettings(self)
        self.omgwtf = IndexerOmgWtfSettings(self)
        self.womble = IndexerWombleSettings(self)
        self.newznab1 = IndexerNewznabSettings(self, "newznab1", "Newznab 1")
        self.newznab2 = IndexerNewznabSettings(self, "newznab2", "Newznab 2")
        self.newznab3 = IndexerNewznabSettings(self, "newznab3", "Newznab 3")
        self.newznab4 = IndexerNewznabSettings(self, "newznab4", "Newznab 4")
        self.newznab5 = IndexerNewznabSettings(self, "newznab5", "Newznab 5")
        self.newznab6 = IndexerNewznabSettings(self, "newznab6", "Newznab 6")
        self.newznab7 = IndexerNewznabSettings(self, "newznab7", "Newznab 7")
        self.newznab8 = IndexerNewznabSettings(self, "newznab8", "Newznab 8")
        self.newznab9 = IndexerNewznabSettings(self, "newznab9", "Newznab 9")
        self.newznab10 = IndexerNewznabSettings(self, "newznab10", "Newznab 10")
        self.newznab11 = IndexerNewznabSettings(self, "newznab11", "Newznab 11")
        self.newznab12 = IndexerNewznabSettings(self, "newznab12", "Newznab 12")
        self.newznab13 = IndexerNewznabSettings(self, "newznab13", "Newznab 13")
        self.newznab14 = IndexerNewznabSettings(self, "newznab14", "Newznab 14")
        self.newznab15 = IndexerNewznabSettings(self, "newznab15", "Newznab 15")
        self.newznab16 = IndexerNewznabSettings(self, "newznab16", "Newznab 16")
        self.newznab17 = IndexerNewznabSettings(self, "newznab17", "Newznab 17")
        self.newznab18 = IndexerNewznabSettings(self, "newznab18", "Newznab 18")
        self.newznab19 = IndexerNewznabSettings(self, "newznab19", "Newznab 19")
        self.newznab20 = IndexerNewznabSettings(self, "newznab20", "Newznab 20")


# TODO: this is horrible

indexerSettings = IndexerSettings()


def get_newznab_setting_by_id(id):
    id = str(id)
    return {
        "1": indexerSettings.newznab1,
        "2": indexerSettings.newznab2,
        "3": indexerSettings.newznab3,
        "4": indexerSettings.newznab4,
        "5": indexerSettings.newznab5,
        "6": indexerSettings.newznab6,
        "7": indexerSettings.newznab7,
        "8": indexerSettings.newznab8,
        "9": indexerSettings.newznab9,
        "10": indexerSettings.newznab10,
        "11": indexerSettings.newznab11,
        "12": indexerSettings.newznab12,
        "13": indexerSettings.newznab13,
        "14": indexerSettings.newznab14,
        "15": indexerSettings.newznab15,
        "16": indexerSettings.newznab16,
        "17": indexerSettings.newznab17,
        "18": indexerSettings.newznab18,
        "19": indexerSettings.newznab19,
        "20": indexerSettings.newznab20

    }[id]


def getSafeConfig():
    return {
        "indexers": [{"name": x["name"], "preselect": x["preselect"], "enabled": x["enabled"], "showOnSearch": x["showOnSearch"]} for x in cfg["indexers"].values()],
        "searching": {"categorysizes": cfg["searching"]["categorysizes"]},
        "downloader": {"downloader": cfg["downloader"]["downloader"], "nzbget": {"defaultCategory": cfg["downloader"]["nzbget"]["defaultCategory"]}, "sabnzbd": {"defaultCategory": cfg["downloader"]["sabnzbd"]["defaultCategory"]}}
    }
