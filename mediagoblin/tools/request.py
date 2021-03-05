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

import json
import logging

from werkzeug.http import parse_options_header

from mediagoblin.db.models import User, AccessToken
from mediagoblin.oauth.tools.request import decode_authorization_header

_log = logging.getLogger(__name__)


# MIME-Types
form_encoded = "application/x-www-form-urlencoded"
json_encoded = "application/json"


def setup_user_in_request(request):
    """
    Examine a request and tack on a request.user parameter if that's
    appropriate.
    """
    # If API request the user will be associated with the access token
    authorization = decode_authorization_header(request.headers)

    if authorization.get("access_token"):
        # Check authorization header.
        token = authorization["oauth_token"]
        token = AccessToken.query.filter_by(token=token).first()
        if token is not None:
            request.user = token.user
            return


    if 'user_id' not in request.session:
        request.user = None
        return

    request.user = User.query.get(request.session['user_id'])

    if not request.user:
        # Something's wrong... this user doesn't exist?  Invalidate
        # this session.
        _log.warn("Killing session for user id %r", request.session['user_id'])
        request.session.delete()

def decode_request(request):
    """ Decodes a request based on MIME-Type """
    data = request.data
    content_type, _ = parse_options_header(request.content_type)

    if content_type == json_encoded:
        data = json.loads(str(data, "utf-8"))
    elif content_type == form_encoded or content_type == "":
        data = request.form
    else:
        data = ""
    return data
