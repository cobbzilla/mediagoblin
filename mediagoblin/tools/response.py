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

import werkzeug.utils
from werkzeug.wrappers import Response as wz_Response
from mediagoblin.tools.template import render_template
from mediagoblin.tools.translate import (lazy_pass_to_ugettext as _,
                                         pass_to_ugettext)
from mediagoblin.db.models import UserBan, User
from datetime import date

class Response(wz_Response):
    """Set default response mimetype to HTML, otherwise we get text/plain"""
    default_mimetype = 'text/html'


def render_to_response(request, template, context, status=200, mimetype=None):
    """Much like Django's shortcut.render()"""
    return Response(
        render_template(request, template, context),
        status=status,
        mimetype=mimetype)

def render_error(request, status=500, title=_('Oops!'),
                 err_msg=_('An error occured')):
    """Render any error page with a given error code, title and text body

    Title and description are passed through as-is to allow html. Make
    sure no user input is contained therein for security reasons. The
    description will be wrapped in <p></p> tags.
    """
    return Response(render_template(request, 'mediagoblin/error.html',
        {'err_code': status, 'title': title, 'err_msg': err_msg}),
        status=status)

def render_400(request, err_msg=None):
    """ Render a standard 400 page"""
    _ = pass_to_ugettext
    title = _("Bad Request")
    if err_msg is None:
        err_msg = _("The request sent to the server is invalid, \
please double check it")

    return render_error(request, 400, title, err_msg)

def render_403(request):
    """Render a standard 403 page"""
    _ = pass_to_ugettext
    title = _('Operation not allowed')
    err_msg = _("Sorry Dave, I can't let you do that!</p><p>You have tried "
                " to perform a function that you are not allowed to. Have you "
                "been trying to delete all user accounts again?")
    return render_error(request, 403, title, err_msg)

def render_404(request):
    """Render a standard 404 page."""
    _ = pass_to_ugettext
    err_msg = _("There doesn't seem to be a page at this address. Sorry!</p>"
                "<p>If you're sure the address is correct, maybe the page "
                "you're looking for has been moved or deleted.")
    return render_error(request, 404, err_msg=err_msg)

def render_user_banned(request):
    """Renders the page which tells a user they have been banned, for how long
    and the reason why they have been banned"
    """
    user_ban = UserBan.query.get(request.user.id)
    if (user_ban.expiration_date is not None and
            date.today()>user_ban.expiration_date):

        user_ban.delete()
        return redirect(request,
            'index')
    return render_to_response(request,
        'mediagoblin/banned.html',
        {'reason':user_ban.reason,
         'expiration_date':user_ban.expiration_date})

def render_http_exception(request, exc, description):
    """Return Response() given a werkzeug.HTTPException

    :param exc: werkzeug.HTTPException or subclass thereof
    :description: message describing the error."""
    # If we were passed the HTTPException stock description on
    # exceptions where we have localized ones, use those:
    stock_desc = (description == exc.__class__.description)

    if stock_desc and exc.code == 403:
        return render_403(request)
    elif stock_desc and exc.code == 404:
        return render_404(request)

    return render_error(request, title='{} {}'.format(exc.code, exc.name),
                        err_msg=description,
                        status=exc.code)


def redirect(request, *args, **kwargs):
    """Redirects to an URL, using urlgen params or location string

    :param querystring: querystring to be appended to the URL
    :param location: If the location keyword is given, redirect to the URL
    """
    querystring = kwargs.pop('querystring', None)

    # Redirect to URL if given by "location=..."
    if 'location' in kwargs:
        location = kwargs.pop('location')
    else:
        location = request.urlgen(*args, **kwargs)

    if querystring:
        location += querystring
    return werkzeug.utils.redirect(location)


def redirect_obj(request, obj):
    """Redirect to the page for the given object.

    Requires obj to have a .url_for_self method."""
    return redirect(request, location=obj.url_for_self(request.urlgen))

def json_response(serializable, _disable_cors=False, *args, **kw):
    '''
    Serializes a json objects and returns a werkzeug Response object with the
    serialized value as the response body and Content-Type: application/json.

    :param serializable: A json-serializable object

    Any extra arguments and keyword arguments are passed to the
    Response.__init__ method.
    '''

    response = wz_Response(json.dumps(serializable), *args, content_type='application/json', **kw)

    if not _disable_cors:
        cors_headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, X-Requested-With'}
        for key, value in cors_headers.items():
            response.headers.set(key, value)

    return response

def json_error(error_str, status=400, *args, **kwargs):
    """
        This is like json_response but takes an error message in and formats
        it in {"error": error_str}. This also sets the default HTTP status
        code to 400.
    """
    return json_response({"error": error_str}, status=status, *args, **kwargs)

def form_response(data, *args, **kwargs):
    """
        Responds using application/x-www-form-urlencoded and returns a werkzeug
        Response object with the data argument as the body
        and 'application/x-www-form-urlencoded' as the Content-Type.

        Any extra arguments and keyword arguments are passed to the
        Response.__init__ method.
    """

    response = wz_Response(
            data,
            content_type="application/x-www-form-urlencoded",
            *args,
            **kwargs
            )

    return response
