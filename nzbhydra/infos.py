from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from future import standard_library

standard_library.install_aliases()
from builtins import *
import logging
import requests
import tmdbsimple as tmdb
from furl import furl
from nzbhydra.exceptions import ExternalApiInfoException
from nzbhydra.database import TvIdCache

logger = logging.getLogger('root')

tmdb.API_KEY = '4df99d58875c2d01fc04936759fea56f'
tmdb_img_config = None


def find_movie_ids(input):
    global tmdb_img_config
    if tmdb_img_config is None:
        tmdb_img_config = tmdb.Configuration().info()["images"]
    base_url = tmdb_img_config["secure_base_url"]
    poster_size = "w92" if "w92" in tmdb_img_config["poster_sizes"] else tmdb_img_config["poster_sizes"][0]

    search = tmdb.Search()
    search.movie(query=input)
    infos = []
    for s in search.results:
        result = {"label": s["title"], "value": s["id"]}
        if "poster_path" in s and s["poster_path"]:
            result["poster"] = base_url + poster_size + s["poster_path"]
            infos.append(result)
    return infos


def get_imdbid_from_tmdbid(tmdbid):
    movie = tmdb.Movies(tmdbid)
    response = movie.info()
    return response["imdb_id"][2:]


def tvdbid_to_rid(tvdbid):
    try:
        id = TvIdCache.get(TvIdCache.tvdb == tvdbid)
        return id.tvrage
    except TvIdCache.DoesNotExist:
        logger.debug("Did not find entry for TVDB id %s in database. Will get infos from TVMaze")
    info = requests.get("http://api.tvmaze.com/lookup/shows?thetvdb=%s" % tvdbid)
    info.raise_for_status()
    result = info.json()

    tvrage = result["externals"]["tvrage"] or None #always present, but None if no result
    if tvrage is None:
        return None
    id = TvIdCache()
    id.tvdb = tvdbid
    id.tvrage = result["externals"]["tvrage"]
    id.save()
    return result["externals"]["tvrage"]


def rid_to_tvdbid(rid):
    try:
        id = TvIdCache.get(TvIdCache.tvrage == rid)
        return id.tvdb
    except TvIdCache.DoesNotExist:
        logger.debug("Did not find entry for TVRage id %s in database. Will get infos from TVMaze")
    info = requests.get("http://api.tvmaze.com/lookup/shows?tvrage=%s" % rid)
    info.raise_for_status()
    result = info.json()

    if "thetvdb" not in result["externals"].keys():
        return None
    id = TvIdCache()
    id.tvdb = result["externals"]["thetvdb"]
    id.tvrage = rid
    id.save()
    return result["externals"]["thetvdb"]


def find_series_ids(input):
    info = requests.get("http://api.tvmaze.com/search/shows?q=%s" % input)
    info.raise_for_status()
    results = []
    for result in info.json():
        result = result["show"]
        if result["externals"]["thetvdb"] is None:
            continue
        info = {"label": result["name"], "value": result["externals"]["thetvdb"]}
        try:
            info["poster"] = result["image"]["medium"]
        except:
            pass
        results.append(info)
    return results


def title_from_id(identifier_key, identifier_value):
    if identifier_key is None or identifier_value is None:
        raise AttributeError("Neither identifier key nor value were supplied")
    try:
        if identifier_key == "imdbid":
            if identifier_value[0:2] != "tt":
                identifier_value = "tt%s" % identifier_value
            url = furl("http://www.omdbapi.com").add({"i": identifier_value, "plot": "short", "r": "json"}).tostr()
            omdb = requests.get(url)
            return omdb.json()["Title"]

        if identifier_key not in ("rid", "tvdbid"):
            raise AttributeError("Unknown identifier %s" % identifier_key)

        tvmaze_key = "tvrage" if identifier_key == "rid" else "thetvdb"
        tvmaze = requests.get(furl("http://api.tvmaze.com/lookup/shows").add({tvmaze_key: identifier_value}).url)
        return tvmaze.json()["name"]

    except Exception as e:
        logger.exception("Unable to retrieve title by id %s and value %s" % (identifier_key, identifier_value))
        raise ExternalApiInfoException(e)
