# GNU MediaGoblin -- federated, autonomous media hosting
# Copyright (C) 2011, 2012 MediaGoblin contributors.  See AUTHORS.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging

from urllib.parse import urlparse
from werkzeug.routing import Map, Rule

from mediagoblin.tools.common import import_component


_log = logging.getLogger(__name__)

url_map = Map()


class MGRoute(Rule):
    def __init__(self, endpoint, url, controller, match_slash=True):
        Rule.__init__(self, url, endpoint=endpoint)
        self.gmg_controller = controller
        self.match_slash = match_slash

    def empty(self):
        new_rule = Rule.empty(self)
        new_rule.gmg_controller = self.gmg_controller
        return new_rule

    def match(self, path, *args, **kwargs):
        if not (self.match_slash or path.endswith("/")):
            path = path + "/"

        return super().match(path, *args, **kwargs)


def endpoint_to_controller(rule):
    endpoint = rule.endpoint
    view_func = rule.gmg_controller

    _log.debug('endpoint: {} view_func: {}'.format(endpoint, view_func))

    # import the endpoint, or if it's already a callable, call that
    if isinstance(view_func, str):
        view_func = import_component(view_func)
        rule.gmg_controller = view_func

    return view_func


def add_route(endpoint, url, controller, *args, **kwargs):
    """
    Add a route to the url mapping
    """
    url_map.add(MGRoute(endpoint, url, controller, *args, **kwargs))


def mount(mountpoint, routes):
    """
    Mount a bunch of routes to this mountpoint
    """
    for endpoint, url, controller in routes:
        url = "{}/{}".format(mountpoint.rstrip('/'), url.lstrip('/'))
        add_route(endpoint, url, controller)

def extract_url_arguments(url, urlmap):
    """
    This extracts the URL arguments from a given URL
    """
    parsed_url = urlparse(url)
    map_adapter = urlmap.bind(
        server_name=parsed_url.netloc,
        script_name=parsed_url.path,
        url_scheme=parsed_url.scheme,
        path_info=parsed_url.path
    )

    return map_adapter.match()[1]
