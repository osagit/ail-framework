#!/usr/bin/env python3
# -*-coding:UTF-8 -*

import os
import sys
import ssl
import json
import time
import uuid

import redis
import random
import logging
import logging.handlers

from flask import Flask, render_template, jsonify, request, Request, Response, session, redirect, url_for
from flask_login import LoginManager, current_user, login_user, logout_user, login_required

import flask
import importlib
from os.path import join

# # TODO: put me in lib/Tag
from pytaxonomies import Taxonomies

sys.path.append(os.path.join(os.environ['AIL_BIN'], 'packages/'))
import Tag

sys.path.append('./modules/')

from User import User

sys.path.append(os.path.join(os.environ['AIL_BIN'], 'lib/'))
import ConfigLoader

# Import config
import Flask_config

# Import Blueprint
from blueprints.root import root
from blueprints.crawler_splash import crawler_splash
from blueprints.correlation import correlation
from blueprints.tags_ui import tags_ui
from blueprints.import_export import import_export


Flask_dir = os.environ['AIL_FLASK']

# CONFIG #
config_loader = ConfigLoader.ConfigLoader()
baseUrl = config_loader.get_config_str("Flask", "baseurl")
baseUrl = baseUrl.replace('/', '')
if baseUrl != '':
    baseUrl = '/'+baseUrl

try:
    FLASK_PORT = config_loader.get_config_int("Flask", "port")
except Exception:
    FLASK_PORT = 7000

# ========= REDIS =========#
r_serv_db = config_loader.get_redis_conn("ARDB_DB")
r_serv_tags = config_loader.get_redis_conn("ARDB_Tags")
r_cache = config_loader.get_redis_conn("Redis_Cache")

# logs
log_dir = os.path.join(os.environ['AIL_HOME'], 'logs')
if not os.path.isdir(log_dir):
    os.makedirs(logs_dir)

# log_filename = os.path.join(log_dir, 'flask_server.logs')
# logger = logging.getLogger()
# formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
# handler_log = logging.handlers.TimedRotatingFileHandler(log_filename, when="midnight", interval=1)
# handler_log.suffix = '%Y-%m-%d.log'
# handler_log.setFormatter(formatter)
# handler_log.setLevel(30)
# logger.addHandler(handler_log)
# logger.setLevel(30)

# =========       =========#

# =========  TLS  =========#
ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
ssl_context.load_cert_chain(certfile=os.path.join(Flask_dir, 'server.crt'), keyfile=os.path.join(Flask_dir, 'server.key'))
#print(ssl_context.get_ciphers())
# =========       =========#

Flask_config.app = Flask(__name__, static_url_path=baseUrl+'/static/')
app = Flask_config.app
app.config['MAX_CONTENT_LENGTH'] = 900 * 1024 * 1024

# =========  BLUEPRINT  =========#
app.register_blueprint(root, url_prefix=baseUrl)
app.register_blueprint(crawler_splash, url_prefix=baseUrl)
app.register_blueprint(correlation, url_prefix=baseUrl)
app.register_blueprint(tags_ui, url_prefix=baseUrl)
app.register_blueprint(import_export, url_prefix=baseUrl)
# =========       =========#

# ========= Cookie name ========
app.config.update(SESSION_COOKIE_NAME='ail_framework_{}'.format(uuid.uuid4().int))

# ========= session ========
app.secret_key = str(random.getrandbits(256))
login_manager = LoginManager()
login_manager.login_view = 'root.login'
login_manager.init_app(app)

print()

# ========= LOGIN MANAGER ========

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

# ========= HEADER GENERATION ======== DEPRECATED

# Get headers items that should be ignored (not displayed)
toIgnoreModule = set()
try:
    with open('templates/ignored_modules.txt', 'r') as f:
        lines = f.read().splitlines()
        for line in lines:
            toIgnoreModule.add(line)

except IOError:
    pass

# Dynamically import routes and functions from modules
# Also, prepare header.html
to_add_to_header_dico = {}
for root, dirs, files in os.walk(os.path.join(Flask_dir, 'modules')):
    sys.path.append(join(root))

    # Ignore the module
    curr_dir = root.split('/')[1]
    if curr_dir in toIgnoreModule:
        continue

    for name in files:
        module_name = root.split('/')[-2]
        if name.startswith('Flask_') and name.endswith('.py'):
            if name == 'Flask_config.py':
                continue
            name = name.strip('.py')
            #print('importing {}'.format(name))
            importlib.import_module(name)
        elif name == 'header_{}.html'.format(module_name):
            with open(join(root, name), 'r') as f:
                to_add_to_header_dico[module_name] = f.read()

#create header.html
complete_header = ""
with open(os.path.join(Flask_dir, 'templates', 'header_base.html'), 'r') as f:
    complete_header = f.read()
modified_header = complete_header

#Add the header in the supplied order
for module_name, txt in list(to_add_to_header_dico.items()):
    to_replace = '<!--{}-->'.format(module_name)
    if to_replace in complete_header:
        modified_header = modified_header.replace(to_replace, txt)
        del to_add_to_header_dico[module_name]

#Add the header for no-supplied order
to_add_to_header = []
for module_name, txt in to_add_to_header_dico.items():
    to_add_to_header.append(txt)

modified_header = modified_header.replace('<!--insert here-->', '\n'.join(to_add_to_header))

#Write the header.html file
with open(os.path.join(Flask_dir, 'templates', 'header.html'), 'w') as f:
    f.write(modified_header)

# ========= JINJA2 FUNCTIONS ========
def list_len(s):
    return len(s)
app.jinja_env.filters['list_len'] = list_len


# ========= CACHE CONTROL ========
@app.after_request
def add_header(response):
    """
    Add headers to both force latest IE rendering engine or Chrome Frame,
    and also to cache the rendered page for 10 minutes.
    """
    response.headers['X-UA-Compatible'] = 'IE=Edge,chrome=1'
    if 'Cache-Control' not in response.headers:
        response.headers['Cache-Control'] = 'private, max-age=0'
    return response

# ========== ROUTES ============

#@app.route('/endpoints')
#def endpoints():
#    for rule in app.url_map.iter_rules():
#        str_endpoint = str(rule)
#        if len(str_endpoint)>5:
#            if str_endpoint[0:5]=='/api/': ## add baseUrl ???
#                print(str_endpoint)
#                #print(rule.endpoint) #internal endpoint name
#                #print(rule.methods)
#    return 'ok'

# ========== ERROR HANDLER ============

@app.errorhandler(405)
def _handle_client_error(e):
    if request.path.startswith('/api/'): ## # TODO: add baseUrl
        res_dict = {"status": "error", "reason": "Method Not Allowed: The method is not allowed for the requested URL"}
        anchor_id = request.path[8:]
        anchor_id = anchor_id.replace('/', '_')
        api_doc_url = 'https://github.com/ail-project/ail-framework/tree/master/doc#{}'.format(anchor_id)
        res_dict['documentation'] = api_doc_url
        return Response(json.dumps(res_dict, indent=2, sort_keys=True), mimetype='application/json'), 405
    else:
        return e

@app.errorhandler(404)
def error_page_not_found(e):
    if request.path.startswith('/api/'): ## # TODO: add baseUrl
        return Response(json.dumps({"status": "error", "reason": "404 Not Found"}, indent=2, sort_keys=True), mimetype='application/json'), 404
    else:
        # avoid endpoint enumeration
        return page_not_found(e)

@login_required
def page_not_found(e):
    # avoid endpoint enumeration
    return render_template('error/404.html'), 404

# ========== INITIAL taxonomies ============
default_taxonomies = ["infoleak", "gdpr", "fpf", "dark-web"]

# enable default taxonomies
for taxo in default_taxonomies:
    Tag.enable_taxonomy(taxo)

# ========== INITIAL tags auto export ============
taxonomies = Taxonomies()

infoleak_tags = taxonomies.get('infoleak').machinetags()
infoleak_automatic_tags = []
for tag in taxonomies.get('infoleak').machinetags():
    if tag.split('=')[0][:] == 'infoleak:automatic-detection':
        r_serv_db.sadd('list_export_tags', tag)

r_serv_db.sadd('list_export_tags', 'infoleak:submission="manual"')
# ============ MAIN ============

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=FLASK_PORT, threaded=True, ssl_context=ssl_context)
