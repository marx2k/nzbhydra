from os.path import dirname, join, abspath
from sys import path
base_path = dirname(abspath(__file__))
path.insert(0, join(base_path, 'nzbhydra'))
path.insert(0, join(base_path, 'libs'))
import os
import sys
import argparse
import requests
import webbrowser
import nzbhydra.config as config
from furl import furl
from nzbhydra import log
from nzbhydra import indexers
from nzbhydra import database
from nzbhydra import web
from nzbhydra.versioning import check_for_new_version

os.chdir(base_path)
requests.packages.urllib3.disable_warnings()
logger = None


def daemonize():
    """
    Fork off as a daemon. Taken directly from sickbeard
    """

    # pylint: disable=E1101
    # Make a non-session-leader child process
    try:
        pid = os.fork()  # @UndefinedVariable - only available in UNIX
        if pid != 0:
            os._exit(0)
    except OSError, e:
        sys.stderr.write("fork #1 failed: %d (%s)\n" % (e.errno, e.strerror))
        sys.exit(1)

    os.setsid()  # @UndefinedVariable - only available in UNIX

    # Make sure I can read my own files and shut out others
    prev = os.umask(0)
    os.umask(prev and int('077', 8))

    # Make the child a session-leader by detaching from the terminal
    try:
        pid = os.fork()  # @UndefinedVariable - only available in UNIX
        if pid != 0:
            os._exit(0)
    except OSError, e:
        sys.stderr.write("fork #2 failed: %d (%s)\n" % (e.errno, e.strerror))
        sys.exit(1)

    # Write pid
    
    pid = str(os.getpid())
    #print(u"Writing PID: " + pid + " to nzbhydra.pid")
    try:
        file("nzbhydra.pid", 'w').write("%s\n" % pid)
    except IOError, e:
        print(u"Unable to write PID file: nzbhydra.pid. Error: " + str(e.strerror) + " [" + str(e.errno) + "]")

    # Redirect all output
    sys.stdout.flush()
    sys.stderr.flush()

    devnull = getattr(os, 'devnull', '/dev/null')
    stdin = file(devnull, 'r')
    stdout = file(devnull, 'a+')
    stderr = file(devnull, 'a+')
    os.dup2(stdin.fileno(), sys.stdin.fileno())
    os.dup2(stdout.fileno(), sys.stdout.fileno())
    os.dup2(stderr.fileno(), sys.stderr.fileno())


def run():
    global logger
    parser = argparse.ArgumentParser(description='NZBHydra')
    parser.add_argument('--config', action='store', help='Settings file to load', default="settings.cfg")
    parser.add_argument('--database', action='store', help='Database file to load', default="nzbhydra.db")
    parser.add_argument('--host', action='store', help='Host to run on')
    parser.add_argument('--port', action='store', help='Port to run on', type=int)
    parser.add_argument('--nobrowser', action='store_true', help='Don\'t open URL on startup', default=False)
    parser.add_argument('--daemon', action='store_true', help='Run as daemon. *nix only', default=False)
    
    args = parser.parse_args()
    
    parser.print_help()
    
    settings_file = args.config
    database_file = args.database

    print("Loading settings from %s" % settings_file)
    config.load(settings_file)
    config.save(settings_file)  # Write any new settings back to the file
    logger = log.setup_custom_logger('root')
    try:
        logger.info("Started")

        if args.daemon:
            logger.info("Daemonizing...")
            daemonize()
        
        config.logLogMessages()
        logger.info("Loading database file %s" % database_file)
        if not os.path.exists(database_file):
            database.init_db(database_file)
        else:
            database.update_db(database_file)
        database.db.init(database_file)
        indexers.read_indexers_from_config()
    
        if config.mainSettings.debug.get():
            logger.info("Debug mode enabled")
            
        host = config.mainSettings.host.get() if args.host is None else args.host
        port = config.mainSettings.port.get() if args.port is None else args.port
    
        logger.info("Starting web app on %s:%d" % (host, port))
        f = furl()
        f.host = "127.0.0.1"
        f.port = port
        f.scheme = "https" if config.mainSettings.ssl.get() else "http"
        if not args.nobrowser and config.mainSettings.startup_browser.get():
            logger.info("Opening browser to %s" % f.url)
            webbrowser.open_new(f.url)
        else:
            logger.info("Go to %s for the frontend (or whatever your public IP is)" % f.url)
        
        check_for_new_version()
        web.run(host, port)
    except Exception:
        logger.exception("Fatal error occurred")

if __name__ == '__main__':
    run()
