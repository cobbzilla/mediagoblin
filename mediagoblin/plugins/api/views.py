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

from werkzeug.exceptions import BadRequest
from werkzeug.wrappers import Response

from mediagoblin.tools.translate import pass_to_ugettext as _
from mediagoblin.tools.response import json_response
from mediagoblin.decorators import require_active_login
from mediagoblin.meddleware.csrf import csrf_exempt
from mediagoblin.media_types import FileTypeNotSupported
from mediagoblin.plugins.api.tools import api_auth, get_entry_serializable
from mediagoblin.submit.lib import \
    check_file_field, submit_media, get_upload_file_limits, \
    FileUploadLimit, UserUploadLimit, UserPastUploadLimit

_log = logging.getLogger(__name__)


@csrf_exempt
@api_auth
@require_active_login
def post_entry(request):
    _log.debug('Posting entry')

    if request.method == 'OPTIONS':
        return json_response({'status': 200})

    if request.method != 'POST':
        _log.debug('Must POST against post_entry')
        raise BadRequest()

    if not check_file_field(request, 'file'):
        _log.debug('File field not found')
        raise BadRequest()

    callback_url = request.form.get('callback_url')
    if callback_url:
        callback_url = str(callback_url)
    try:
        entry = submit_media(
            mg_app=request.app, user=request.user,
            submitted_file=request.files['file'],
            filename=request.files['file'].filename,
            title=str(request.form.get('title')),
            description=str(request.form.get('description')),
            license=str(request.form.get('license', '')),
            tags_string=str(request.form.get('tags', '')),
            callback_url=callback_url)

        return json_response(get_entry_serializable(entry, request.urlgen))

    # Handle upload limit issues
    except FileUploadLimit:
        raise BadRequest(
            _('Sorry, the file size is too big.'))
    except UserUploadLimit:
        raise BadRequest(
            _('Sorry, uploading this file will put you over your'
              ' upload limit.'))
    except UserPastUploadLimit:
        raise BadRequest(
            _('Sorry, you have reached your upload limit.'))
    except FileTypeNotSupported as e:
        raise BadRequest(e)


@api_auth
@require_active_login
def api_test(request):
    user_data = {
            'username': request.user.username,
            'email': request.user.email}

    # TODO: This is the *only* thing using Response() here, should that
    # not simply use json_response()?
    return Response(json.dumps(user_data, sort_keys=True))


def get_entries(request):
    entries = request.db.MediaEntry.query

    # TODO: Make it possible to fetch unprocessed media, or media in-processing
    entries = entries.filter_by(state='processed')

    # TODO: Add sort order customization
    entries = entries.order_by(request.db.MediaEntry.created.desc())

    # TODO: Fetch default and upper limit from config
    entries = entries.limit(int(request.GET.get('limit') or 10))

    entries_serializable = []

    for entry in entries:
        entries_serializable.append(get_entry_serializable(entry, request.urlgen))

    return json_response(entries_serializable)
