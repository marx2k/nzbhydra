from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from builtins import super
from future import standard_library
standard_library.install_aliases()
from builtins import *
from builtins import object
import json
import datetime
import logging
import arrow
from dateutil.tz import tzutc
from peewee import *

logger = logging.getLogger('root')

db = SqliteDatabase(None, threadlocals=True)

class JSONField(TextField):
    db_field = "text"

    def db_value(self, value):
        return json.dumps(value)

    def python_value(self, value):
        return json.loads(value)


class DateTimeUTCField(DateTimeField):
    db_field = "datetime"

    def db_value(self, value):
        return arrow.get(value).datetime if value is not None else None

    def python_value(self, value):
        return arrow.get(value, tzinfo=tzutc())


class Indexer(Model):
    name = CharField(unique=True)  # The name of the indexer. So if the user changes the name all references get lost (except we handle that if he does it in the GUI).

    class Meta(object):
        database = db


class Search(Model):
    internal = BooleanField()  # true if from our gui, false if via newznab api
    query = CharField(null=True)
    time = DateTimeField()
    identifier_key = CharField(null=True)
    identifier_value = CharField(null=True)
    category = TextField(null=True)
    season = IntegerField(null=True)
    episode = IntegerField(null=True)
    type = CharField(default="general")

    class Meta(object):
        database = db

    def save(self, *args, **kwargs):
        if self.time is None:
            self.time = datetime.datetime.utcnow()  # Otherwise the time of the first run of this code is taken
        super(Search, self).save(*args, **kwargs)


class IndexerSearch(Model):
    indexer = ForeignKeyField(Indexer, related_name="searches")
    search = ForeignKeyField(Search, related_name="indexer_searches", null=True)
    time = DateTimeField()

    successful = BooleanField(default=False)
    results = IntegerField(null=True)  # number of results returned

    class Meta(object):
        database = db

    def save(self, *args, **kwargs):
        if self.time is None:
            self.time = datetime.datetime.utcnow()  # Otherwise the time of the first run of this code is taken
        super(IndexerSearch, self).save(*args, **kwargs)


class IndexerApiAccess(Model):
    indexer = ForeignKeyField(Indexer)
    indexer_search = ForeignKeyField(IndexerSearch, related_name="api_accesses", null=True)
    time = DateTimeUTCField()
    type = CharField()  # search, nzb, comments, nfo?
    url = CharField()
    response_successful = BooleanField(default=False, null=True)
    response_time = IntegerField(null=True)
    error = CharField(null=True)

    class Meta(object):
        database = db

    def save(self, *args, **kwargs):
        if self.time is None:  # Otherwise the time of the first run of this code is taken
            self.time = datetime.datetime.utcnow()
        super(IndexerApiAccess, self).save(*args, **kwargs)


class IndexerNzbDownload(Model):
    indexer = ForeignKeyField(Indexer, related_name="downloads")
    indexer_search = ForeignKeyField(IndexerSearch, related_name="downloads", null=True)
    api_access = ForeignKeyField(IndexerApiAccess)
    title = CharField()
    time = DateTimeField()
    mode = CharField()  # "serve" or "redirect"
    guid = CharField()

    class Meta(object):
        database = db

    def save(self, *args, **kwargs):
        if self.time is None:
            self.time = datetime.datetime.utcnow()  # Otherwise the time at the first run of this code is taken
        super(IndexerNzbDownload, self).save(*args, **kwargs)


# class IndexerSearchApiAccess(Model):
#     search = ForeignKeyField(IndexerSearch, related_name="api_accesses")
#     api_access = ForeignKeyField(IndexerApiAccess, related_name="api_accesses")
# 
#     class Meta:
#         database = db


class IndexerStatus(Model):
    indexer = ForeignKeyField(Indexer, related_name="status")
    first_failure = DateTimeUTCField(default=datetime.datetime.utcnow(), null=True)
    latest_failure = DateTimeUTCField(default=datetime.datetime.utcnow(), null=True)
    disabled_until = DateTimeUTCField(default=datetime.datetime.utcnow(), null=True)
    level = IntegerField(default=0)
    reason = CharField(null=True)
    disabled_permanently = BooleanField(default=False)  # Set to true if an error occurred that probably won't fix itself (e.g. when the apikey is wrong) 

    def __repr__(self):
        return "%s in status %d. First failure: %s. Latest Failure: %s. Reason: %s. Disabled until: %s" % (self.indexer, self.level, self.first_failure, self.latest_failure, self.reason, self.disabled_until)

    class Meta(object):
        database = db
        
class VersionInfo(Model):
    version = IntegerField(default=1)

    class Meta(object):
        database = db
        
class TvIdCache(Model):
    tvdb = CharField()
    tvrage = CharField()

    class Meta(object):
        database = db

def init_db(dbfile):
    tables = [Indexer, IndexerNzbDownload, Search, IndexerSearch, IndexerApiAccess, IndexerStatus, VersionInfo, TvIdCache]
    db.init(dbfile)
    db.connect()

    logger.info("Initializing database and creating tables")
    for t in tables:
        try:
            db.create_table(t)
        except OperationalError:
            logger.exception("Error while creating table %s" % t)
    
    logger.info("Created new version info entry with database version 1")
    VersionInfo(version=1).create()
    
    db.close()

def update_db(dbfile):
    db.init(dbfile)
    db.connect()
    
    #Add version info if none exists
    try:
        db.create_table(VersionInfo)
        logger.info("Added new version info entry with database version 1 to existing database")
        VersionInfo(version=2).create()
    except OperationalError:
        logger.debug("Skipping creation of table VersionInfo because it already exists")
        pass

    vi = VersionInfo().get()
    if vi.version == 1:
        logger.info("Upgrading database to version 2")
        #Update from 1 to 2
        # Add tv id cache info 
        try:
            db.create_table(TvIdCache)
            logger.info("Added new table TvIdCache to database")
        except OperationalError:
            logger.error("Error adding table TvIdCache to database")
            #TODO How should we handle this?
            pass
        vi.version = 2
        vi.save()
    
    db.close()

