from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import
from builtins import range
from builtins import str
from builtins import *
from future import standard_library
from peewee import fn



standard_library.install_aliases()
from collections import namedtuple
from itertools import groupby
import rison
import logging
from io import BytesIO
import urllib

from flask import request, send_file
from furl import furl
from marshmallow import Schema, fields

from requests import RequestException

from nzbhydra import config
from nzbhydra.config import downloaderSettings, NzbAccessTypeSelection
from nzbhydra import indexers
from nzbhydra.database import IndexerApiAccess, IndexerNzbDownload, Indexer, IndexerSearch

logger = logging.getLogger('root')

categories = {'Console': {'code': [1000, 1010, 1020, 1030, 1040, 1050, 1060, 1070, 1080], 'pretty': 'Console'},
              'Movie': {'code': [2000, 2010, 2020], 'pretty': 'Movie'},
              'Movie_HD': {'code': [2040, 2050, 2060], 'pretty': 'HD'},
              'Movie_SD': {'code': [2030], 'pretty': 'SD'},
              'Audio': {'code': [3000, 3010, 3020, 3030, 3040], 'pretty': 'Audio'},
              'PC': {'code': [4000, 4010, 4020, 4030, 4040, 4050, 4060, 4070], 'pretty': 'PC'},
              'TV': {'code': [5000, 5020], 'pretty': 'TV'},
              'TV_SD': {'code': [5030], 'pretty': 'SD'},
              'TV_HD': {'code': [5040], 'pretty': 'HD'},
              'XXX': {'code': [6000, 6010, 6020, 6030, 6040, 6050], 'pretty': 'XXX'},
              'Other': {'code': [7000, 7010], 'pretty': 'Other'},
              'Ebook': {'code': [7020], 'pretty': 'Ebook'},
              'Comics': {'code': [7030], 'pretty': 'Comics'},
              }


class IndexerSchema(Schema):
    name = fields.String()
    module = fields.String()
    enabled = fields.Boolean()
    settings = fields.String()


class NzbSearchResultSchema(Schema):
    title = fields.String()
    link = fields.String()
    epoch = fields.Integer()
    pubdate_utc = fields.String()
    age_days = fields.Integer()
    age_precise = fields.Boolean()
    indexer = fields.String()
    indexerscore = fields.String()
    guid = fields.String()
    indexerguid = fields.String()
    size = fields.Integer()
    category = fields.String()
    has_nfo = fields.Integer()
    details_link = fields.String()
    hash = fields.Integer()


class IndexerApiAccessSchema(Schema):
    indexer = fields.Nested(IndexerSchema, only="name")
    time = fields.DateTime()
    type = fields.String()
    url = fields.String()
    response_successful = fields.Boolean()
    response_time = fields.Integer()
    error = fields.String()


class IndexerSearchSchema(Schema):
    indexer = fields.Nested(IndexerSchema, only="name")
    time = fields.DateTime()
    successful = fields.Boolean()
    results = fields.Integer()

    api_accesses = fields.Nested(IndexerApiAccessSchema, many=True)


def get_root_url():
    return request.url_root


def get_nzb_link_and_guid(indexer, guid, searchid, title):
    data_getnzb = {"indexer": indexer, "guid": guid, "searchid": searchid, "title": title}
    baseUrl = config.mainSettings.baseUrl.get_with_default(None)
    if baseUrl is not None and baseUrl != "":
        f = furl(baseUrl)
    else:
        f = furl(get_root_url())
    f.path.add("api")
    guid_rison = rison.dumps(data_getnzb)
    args = {"t": "get", "id": guid_rison}
    apikey = config.mainSettings.apikey.get_with_default(None)
    if apikey is not None:
        args["apikey"] = apikey
    f.set(args=args)
    
    return f.url, guid_rison


def transform_results(results, dbsearch):
    if downloaderSettings.nzbaccesstype.get() == NzbAccessTypeSelection.direct:  # We don't change the link, the results lead directly to the NZB
        return results
    transformed = []
    for i in results:
        nzb_link, guid_json = get_nzb_link_and_guid(i.indexer, i.guid, dbsearch, i.title)
        i.link = nzb_link
        i.indexerguid = i.guid  # Save the indexer's original GUID so that we can send it later from the GUI to identify the result
        i.guid = nzb_link  # For now it's the same as the link to the NZB, later we might link to a details page that at the least redirects to the original indexer's page

        # Add our internal guid (like the link above but only the identifying part) to the newznab attributes so that when any external tool uses it together with g=get or t=getnfo we can identify it
        has_guid = False
        has_size = False
        
        for a in i.attributes:
            if a["name"] == "guid":
                a["value"] = guid_json
                has_guid = True
            if a["name"] == "size":
                has_size = True
        if not has_guid:
            i.attributes.append({"name": "guid", "value": guid_json})  # If it wasn't set before now it is (for results from newznab-indexers)
        if not has_size:
            i.attributes.append({"name": "size", "value": i.size})  # If it wasn't set before now it is (for results from newznab-indexers)
        transformed.append(i)

    return transformed


def sizeof_fmt(num, suffix='B'):
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)


def process_for_external_api(results):
    results = transform_results(results["results"], results["dbsearch"])
    return results


def process_for_internal_api(search_result):
    nzbsearchresults = search_result["results"]
    logger.debug("Processing %d results" % len(nzbsearchresults))
    indexersearchdbentries = []
    for indexer, indexer_info in search_result["indexer_infos"].items():
        indexer_search_info = IndexerSearchSchema().dump(indexer_info["indexer_search"]).data
        indexer_search_info["total"] = indexer_info["total"]
        indexer_search_info["offset"] = search_result["indexer_infos"][indexer]["search_request"].offset
        indexer_search_info["total_known"] = indexer_info["total_known"]
        indexer_search_info["has_more"] = indexer_info["has_more"]
        indexersearchdbentries.append(indexer_search_info)

    nzbsearchresults = transform_results(nzbsearchresults, search_result["dbsearch"])
    nzbsearchresults = serialize_nzb_search_result(nzbsearchresults)

    return {"results": nzbsearchresults, "indexersearches": indexersearchdbentries, "searchentryid": search_result["dbsearch"], "total": search_result["total"]}


def serialize_nzb_search_result(results):
    return NzbSearchResultSchema(many=True).dump(results).data


def get_nfo(indexer_name, guid):
    for p in indexers.enabled_indexers:
        if p.name == indexer_name:
            has_nfo, nfo, message = p.get_nfo(guid)
            break
    else:
        logger.error("Did not find indexer with name %s" % indexer_name)
        return {"has_nfo": False, "error": "Unable to find indexer"}
    return {"has_nfo": has_nfo, "nfo": nfo, "message": message}
    return result


def get_details_link(indexer_name, guid):
    for p in indexers.enabled_indexers:
        if p.name == indexer_name:
            return p.get_details_link(guid)
    else:
        logger.error("Did not find indexer with name %s" % indexer_name)
        return None
    

def get_nzb_link(indexer_name, guid, title, searchid):
    """
    Build a link that leads to the actual NZB of the indexer using the given informations. We log this as indexer API access and NZB download because this is only called
    when the NZB will be actually downloaded later (by us or a downloader) 
    :return: str
    """
    for p in indexers.enabled_indexers:
        if p.name == indexer_name:
            link = p.get_nzb_link(guid, title)

            # Log to database
            indexer = Indexer.get(fn.lower(Indexer.name) == indexer_name.lower())
            papiaccess = IndexerApiAccess(indexer=p.indexer, type="nzb", url=link, response_successful=None, indexer_search=indexer)
            papiaccess.save()
            pnzbdl = IndexerNzbDownload(indexer=indexer, indexer_search=searchid, api_access=papiaccess, mode="redirect")
            pnzbdl.save()

            return link

    else:
        logger.error("Did not find indexer with name %s" % indexer_name)
        return None


IndexerNzbDownloadResult = namedtuple("IndexerNzbDownload", "content headers")


def download_nzb_and_log(indexer_name, provider_guid, title, searchid):
    """
    Gets the NZB link from the indexer using the guid, downloads it and logs the download

    :param indexer_name: name of the indexer
    :param provider_guid: guid to build link
    :param title: the title to build the link
    :param searchid: the id of the IndexerSearch entry so we can link the download to a search
    :return: IndexerNzbDownloadResult
    """
    for p in indexers.enabled_indexers:
        if p.name == indexer_name:

            link = p.get_nzb_link(provider_guid, title)
            indexer = Indexer.get(fn.lower(Indexer.name) == indexer_name.lower())
            psearch = IndexerSearch.get((IndexerSearch.indexer == indexer) & (IndexerSearch.search == searchid))
            papiaccess = IndexerApiAccess(indexer=p.indexer, type="nzb", url=link, indexer_search=psearch)
            papiaccess.save()

            internallink, guid = get_nzb_link_and_guid(indexer_name, provider_guid, searchid, title)
            pnzbdl = IndexerNzbDownload(indexer=indexer, indexer_search=searchid, api_access=papiaccess, mode="serve", title=title, guid=internallink)
            pnzbdl.save()
            try:
                r = p.get(link, timeout=10)
                r.raise_for_status()

                papiaccess.response_successful = True
                papiaccess.response_time = r.elapsed.microseconds / 1000

                return IndexerNzbDownloadResult(content=r.content, headers=r.headers)
            except RequestException as e:
                logger.error("Error while connecting to URL %s: %s" % (link, str(e)))
                papiaccess.error = str(e)
                return None
            finally:
                papiaccess.save()
    else:
        return "Unable to find NZB link"


def get_nzb_response(indexer_name, guid, title, searchid):
    nzbdownloadresult = download_nzb_and_log(indexer_name, guid, title, searchid)
    if nzbdownloadresult is not None:
        bio = BytesIO(nzbdownloadresult.content)
        filename = title + ".nzb" if title is not None else "nzbhydra.nzb"
        response = send_file(bio, mimetype='application/x-nzb;', as_attachment=True, attachment_filename=filename, add_etags=False)
        response.headers["content-length"] = len(nzbdownloadresult.content)

        for header in nzbdownloadresult.headers.keys():
            if header.lower().startswith("x-dnzb") or header.lower() in ("content-disposition", "content-type"):
                response.headers[header] = nzbdownloadresult.headers[header]
        logger.info("Returning downloaded NZB %s from %s" % (title, indexer_name))
        return response
    else:
        logger.error("Error while trying to download NZB %s from %s" % (title, indexer_name))
        return "Unable to download NZB", 500
