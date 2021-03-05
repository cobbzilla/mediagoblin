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
import datetime
import json

from mediagoblin import messages, mg_globals
from mediagoblin.db.models import (MediaEntry, MediaTag, Collection, Comment,
                                   CollectionItem, LocalUser, Activity, \
                                   GenericModelReference)
from mediagoblin.plugins.api.tools import get_media_file_paths
from mediagoblin.tools.response import render_to_response, render_404, \
    redirect, redirect_obj
from mediagoblin.tools.text import cleaned_markdown_conversion
from mediagoblin.tools.translate import pass_to_ugettext as _
from mediagoblin.tools.pagination import Pagination
from mediagoblin.tools.federation import create_activity
from mediagoblin.user_pages import forms as user_forms
from mediagoblin.user_pages.lib import (send_comment_email,
	add_media_to_collection, build_report_object)
from mediagoblin.notifications import trigger_notification, \
    add_comment_subscription, mark_comment_notification_seen
from mediagoblin.tools.pluginapi import hook_transform

from mediagoblin.decorators import (uses_pagination, get_user_media_entry,
    get_media_entry_by_id, user_has_privilege, user_not_banned,
    require_active_login, user_may_delete_media, user_may_alter_collection,
    get_user_collection, get_user_collection_item, active_user_from_url,
    get_optional_media_comment_by_id, allow_reporting)

from werkzeug.contrib.atom import AtomFeed
from werkzeug.exceptions import MethodNotAllowed
from werkzeug.wrappers import Response


_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)

@user_not_banned
@uses_pagination
def user_home(request, page):
    """'Homepage' of a LocalUser()"""
    user = LocalUser.query.filter_by(username=request.matchdict['user']).first()
    if not user:
        return render_404(request)
    elif not user.has_privilege('active'):
        return render_to_response(
            request,
            'mediagoblin/user_pages/user_nonactive.html',
            {'user': user})

    cursor = MediaEntry.query.\
        filter_by(actor = user.id).order_by(MediaEntry.created.desc())

    pagination = Pagination(page, cursor)
    media_entries = pagination()

    # if no data is available, return NotFound
    if media_entries == None:
        return render_404(request)

    user_gallery_url = request.urlgen(
        'mediagoblin.user_pages.user_gallery',
        user=user.username)

    return render_to_response(
        request,
        'mediagoblin/user_pages/user.html',
        {'user': user,
         'user_gallery_url': user_gallery_url,
         'media_entries': media_entries,
         'pagination': pagination})

@user_not_banned
@active_user_from_url
@uses_pagination
def user_gallery(request, page, url_user=None):
    """'Gallery' of a LocalUser()"""
    tag = request.matchdict.get('tag', None)
    cursor = MediaEntry.query.filter_by(
        actor=url_user.id,
        state='processed').order_by(MediaEntry.created.desc())

    # Filter potentially by tag too:
    if tag:
        cursor = cursor.filter(
            MediaEntry.tags_helper.any(
                MediaTag.slug == request.matchdict['tag']))

    # Paginate gallery
    pagination = Pagination(page, cursor)
    media_entries = pagination()

    #if no data is available, return NotFound
    # TODO: Should we really also return 404 for empty galleries?
    if media_entries == None:
        return render_404(request)

    return render_to_response(
        request,
        'mediagoblin/user_pages/gallery.html',
        {'user': url_user, 'tag': tag,
         'media_entries': media_entries,
         'pagination': pagination})


MEDIA_COMMENTS_PER_PAGE = 50

@user_not_banned
@get_user_media_entry
@uses_pagination
def media_home(request, media, page, **kwargs):
    """
    'Homepage' of a MediaEntry()
    """
    comment_id = request.matchdict.get('comment', None)
    if comment_id:
        if request.user:
            mark_comment_notification_seen(comment_id, request.user)

        pagination = Pagination(
            page, media.get_comments(
                mg_globals.app_config['comments_ascending']),
            MEDIA_COMMENTS_PER_PAGE,
            comment_id)
    else:
        pagination = Pagination(
            page, media.get_comments(
                mg_globals.app_config['comments_ascending']),
            MEDIA_COMMENTS_PER_PAGE)

    comments = pagination()

    comment_form = user_forms.MediaCommentForm(request.form)

    media_template_name = media.media_manager.display_template

    context = {
        'media': media,
        'comments': comments,
        'pagination': pagination,
        'comment_form': comment_form,
        'app_config': mg_globals.app_config}

    # Since the media template name gets swapped out for each media
    # type, normal context hooks don't work if you want to affect all
    # media displays.  This gives a general purpose hook.
    context = hook_transform(
        "media_home_context", context)

    return render_to_response(
        request,
        media_template_name,
        context)


@get_media_entry_by_id
@user_has_privilege('commenter')
def media_post_comment(request, media):
    """
    recieves POST from a MediaEntry() comment form, saves the comment.
    """
    if not request.method == 'POST':
        raise MethodNotAllowed()

    # If media is not processed, return NotFound.
    if not media.state == 'processed':
        return render_404(request)

    comment = request.db.TextComment()
    comment.actor = request.user.id
    comment.content = str(request.form['comment_content'])

    # Show error message if commenting is disabled.
    if not mg_globals.app_config['allow_comments']:
        messages.add_message(
            request,
            messages.ERROR,
            _("Sorry, comments are disabled."))
    elif not comment.content.strip():
        messages.add_message(
            request,
            messages.ERROR,
            _("Oops, your comment was empty."))
    else:
        create_activity("post", comment, comment.actor, target=media)
        add_comment_subscription(request.user, media)
        comment.save()

        link = request.db.Comment()
        link.target = media
        link.comment = comment
        link.save()

        messages.add_message(
            request,
            messages.SUCCESS,
            _('Your comment has been posted!'))
        trigger_notification(link, media, request)

    return redirect_obj(request, media)



def media_preview_comment(request):
    """Runs a comment through markdown so it can be previewed."""
    # If this isn't an ajax request, render_404
    if not request.is_xhr:
        return render_404(request)

    comment = str(request.form['comment_content'])
    cleancomment = { "content":cleaned_markdown_conversion(comment)}

    return Response(json.dumps(cleancomment))

@user_not_banned
@get_media_entry_by_id
@require_active_login
def media_collect(request, media):
    """Add media to collection submission"""

    # If media is not processed, return NotFound.
    if not media.state == 'processed':
        return render_404(request)

    form = user_forms.MediaCollectForm(request.form)
    # A user's own collections:
    form.collection.query = Collection.query.filter_by(
        actor=request.user.id,
        type=Collection.USER_DEFINED_TYPE
    ).order_by(Collection.title)

    if request.method != 'POST' or not form.validate():
        # No POST submission, or invalid form
        if not form.validate():
            messages.add_message(
                request,
                messages.ERROR,
                _('Please check your entries and try again.'))

        return render_to_response(
            request,
            'mediagoblin/user_pages/media_collect.html',
            {'media': media,
             'form': form})

    # If we are here, method=POST and the form is valid, submit things.
    # If the user is adding a new collection, use that:
    if form.collection_title.data:
        # Make sure this user isn't duplicating an existing collection
        existing_collection = Collection.query.filter_by(
            actor=request.user.id,
            title=form.collection_title.data,
            type=Collection.USER_DEFINED_TYPE
        ).first()
        if existing_collection:
            messages.add_message(
                request,
                messages.ERROR,
                _('You already have a collection called "%s"!') %
                    existing_collection.title)
            return redirect(request, "mediagoblin.user_pages.media_home",
                            user=media.get_actor.username,
                            media=media.slug_or_id)

        collection = Collection()
        collection.title = form.collection_title.data
        collection.description = form.collection_description.data
        collection.actor = request.user.id
        collection.type = Collection.USER_DEFINED_TYPE
        collection.generate_slug()
        collection.get_public_id(request.urlgen)
        create_activity("create", collection, collection.actor)
        collection.save()

    # Otherwise, use the collection selected from the drop-down
    else:
        collection = form.collection.data
        if collection and collection.actor != request.user.id:
            collection = None

    # Make sure the user actually selected a collection
    if not collection:
        messages.add_message(
            request,
            messages.ERROR,
            _('You have to select or add a collection'))
        return redirect(request, "mediagoblin.user_pages.media_collect",
                    user=media.get_actor.username,
                    media_id=media.id)

    item = CollectionItem.query.filter_by(collection=collection.id)
    item = item.join(CollectionItem.object_helper).filter_by(
        model_type=media.__tablename__,
        obj_pk=media.id
    ).first()

    # Check whether media already exists in collection
    if item is not None:
        messages.add_message(
            request,
            messages.ERROR,
            _('"%s" already in collection "%s"') %
                (media.title, collection.title))
    else: # Add item to collection
        add_media_to_collection(collection, media, form.note.data)
        create_activity("add", media, request.user, target=collection)
        messages.add_message(
            request,
            messages.SUCCESS,
            _('"%s" added to collection "%s"') %
                (media.title, collection.title))

    return redirect_obj(request, media)


#TODO: Why does @user_may_delete_media not implicate @require_active_login?
@get_media_entry_by_id
@require_active_login
@user_may_delete_media
def media_confirm_delete(request, media):

    form = user_forms.ConfirmDeleteForm(request.form)

    if request.method == 'POST' and form.validate():
        if form.confirm.data is True:
            username = media.get_actor.username

            # This probably is already filled but just in case it has slipped
            # through the net somehow, we need to try and make sure the
            # MediaEntry has a public ID so it gets properly soft-deleted.
            media.get_public_id(request.urlgen)

            # Decrement the users uploaded quota.
            media.get_actor.uploaded = media.get_actor.uploaded - \
                media.file_size
            media.get_actor.save()

            # Delete MediaEntry and all related files, comments etc.
            media.delete()
            messages.add_message(
                request,
                messages.SUCCESS,
                _('You deleted the media.'))

            location = media.url_to_next(request.urlgen)
            if not location:
                location=media.url_to_prev(request.urlgen)
            if not location:
                location=request.urlgen("mediagoblin.user_pages.user_home",
                                        user=username)
            return redirect(request, location=location)
        else:
            messages.add_message(
                request,
                messages.ERROR,
                _("The media was not deleted because you didn't check "
                  "that you were sure."))
            return redirect_obj(request, media)

    if (request.user.has_privilege('admin') and
         request.user.id != media.actor):
        messages.add_message(
            request,
            messages.WARNING,
            _("You are about to delete another user's media. "
              "Proceed with caution."))

    return render_to_response(
        request,
        'mediagoblin/user_pages/media_confirm_delete.html',
        {'media': media,
         'form': form})

@user_not_banned
@active_user_from_url
@uses_pagination
def user_collection(request, page, url_user=None):
    """A User-defined Collection"""
    collection = Collection.query.filter_by(
        get_actor=url_user,
        slug=request.matchdict['collection']).first()

    if not collection:
        return render_404(request)

    cursor = collection.get_collection_items()

    pagination = Pagination(page, cursor)
    collection_items = pagination()

    # if no data is available, return NotFound
    # TODO: Should an empty collection really also return 404?
    if collection_items == None:
        return render_404(request)

    return render_to_response(
        request,
        'mediagoblin/user_pages/collection.html',
        {'user': url_user,
         'collection': collection,
         'collection_items': collection_items,
         'pagination': pagination})

@user_not_banned
@active_user_from_url
def collection_list(request, url_user=None):
    """A User-defined Collection"""
    collections = Collection.query.filter_by(
        get_actor=url_user)

    return render_to_response(
        request,
        'mediagoblin/user_pages/collection_list.html',
        {'user': url_user,
         'collections': collections})


@get_user_collection_item
@require_active_login
@user_may_alter_collection
def collection_item_confirm_remove(request, collection_item):

    form = user_forms.ConfirmCollectionItemRemoveForm(request.form)

    if request.method == 'POST' and form.validate():
        username = collection_item.in_collection.get_actor.username
        collection = collection_item.in_collection

        if form.confirm.data is True:
            obj = collection_item.get_object()
            obj.save()

            collection_item.delete()
            collection.num_items = collection.num_items - 1
            collection.save()

            messages.add_message(
                request,
                messages.SUCCESS,
                _('You deleted the item from the collection.'))
        else:
            messages.add_message(
                request,
                messages.ERROR,
                _("The item was not removed because you didn't check "
                  "that you were sure."))

        return redirect_obj(request, collection)

    if (request.user.has_privilege('admin') and
         request.user.id != collection_item.in_collection.actor):
        messages.add_message(
            request,
            messages.WARNING,
            _("You are about to delete an item from another user's collection. "
              "Proceed with caution."))

    return render_to_response(
        request,
        'mediagoblin/user_pages/collection_item_confirm_remove.html',
        {'collection_item': collection_item,
         'form': form})


@get_user_collection
@require_active_login
@user_may_alter_collection
def collection_confirm_delete(request, collection):

    form = user_forms.ConfirmDeleteForm(request.form)

    if request.method == 'POST' and form.validate():

        username = collection.get_actor.username

        if form.confirm.data is True:
            collection_title = collection.title

            # Firstly like with the MediaEntry delete, lets ensure the
            # public_id is populated as this is really important!
            collection.get_public_id(request.urlgen)

            # Delete all the associated collection items
            for item in collection.get_collection_items():
                obj = item.get_object()
                obj.save()
                item.delete()

            collection.delete()
            messages.add_message(
                request,
                messages.SUCCESS,
                _('You deleted the collection "%s"') %
                    collection_title)

            return redirect(request, "mediagoblin.user_pages.user_home",
                user=username)
        else:
            messages.add_message(
                request,
                messages.ERROR,
                _("The collection was not deleted because you didn't "
                  "check that you were sure."))

            return redirect_obj(request, collection)

    if (request.user.has_privilege('admin') and
         request.user.id != collection.actor):
        messages.add_message(
            request, messages.WARNING,
            _("You are about to delete another user's collection. "
              "Proceed with caution."))

    return render_to_response(
        request,
        'mediagoblin/user_pages/collection_confirm_delete.html',
        {'collection': collection,
         'form': form})


ATOM_DEFAULT_NR_OF_UPDATED_ITEMS = 15


def atom_feed(request):
    """
    generates the atom feed with the newest images
    """
    user = LocalUser.query.filter_by(
        username = request.matchdict['user']).first()
    if not user or not user.has_privilege('active'):
        return render_404(request)
    feed_title = "MediaGoblin Feed for user '%s'" % request.matchdict['user']
    link = request.urlgen('mediagoblin.user_pages.user_home',
                          qualified=True, user=request.matchdict['user'])
    cursor = MediaEntry.query.filter_by(actor=user.id, state='processed')
    cursor = cursor.order_by(MediaEntry.created.desc())
    cursor = cursor.limit(ATOM_DEFAULT_NR_OF_UPDATED_ITEMS)


    """
    ATOM feed id is a tag URI (see http://en.wikipedia.org/wiki/Tag_URI)
    """
    atomlinks = [{
        'href': link,
        'rel': 'alternate',
        'type': 'text/html'}]

    if mg_globals.app_config["push_urls"]:
        for push_url in mg_globals.app_config["push_urls"]:
            atomlinks.append({
                'rel': 'hub',
                'href': push_url})

    feed = AtomFeed(
        feed_title,
        feed_url=request.url,
        id='tag:{host},{year}:gallery.user-{user}'.format(
            host=request.host,
            year=datetime.datetime.today().strftime('%Y'),
            user=request.matchdict['user']),
        links=atomlinks)

    for entry in cursor:
        # Include a thumbnail image in content.
        file_urls = get_media_file_paths(entry.media_files, request.urlgen)
        if 'thumb' in file_urls:
            content = '<img src="{thumb}" alt='' /> {desc}'.format(
                thumb=file_urls['thumb'], desc=entry.description_html)
        else:
            content = entry.description_html

        feed.add(
            entry.get('title'),
            content,
            id=entry.url_for_self(request.urlgen, qualified=True),
            content_type='html',
            author={
                'name': entry.get_actor.username,
                'uri': request.urlgen(
                    'mediagoblin.user_pages.user_home',
                    qualified=True,
                    user=entry.get_actor.username)},
            updated=entry.get('created'),
            links=[{
                'href': entry.url_for_self(
                    request.urlgen,
                    qualified=True),
                'rel': 'alternate',
                'type': 'text/html'}])

    return feed.get_response()


def collection_atom_feed(request):
    """
    generates the atom feed with the newest images from a collection
    """
    user = LocalUser.query.filter_by(
        username = request.matchdict['user']).first()
    if not user or not user.has_privilege('active'):
        return render_404(request)

    collection = Collection.query.filter_by(
               actor=user.id,
               slug=request.matchdict['collection']).first()
    if not collection:
        return render_404(request)

    cursor = CollectionItem.query.filter_by(
                 collection=collection.id) \
                 .order_by(CollectionItem.added.desc()) \
                 .limit(ATOM_DEFAULT_NR_OF_UPDATED_ITEMS)

    """
    ATOM feed id is a tag URI (see http://en.wikipedia.org/wiki/Tag_URI)
    """
    atomlinks = [{
           'href': collection.url_for_self(request.urlgen, qualified=True),
           'rel': 'alternate',
           'type': 'text/html'
           }]

    if mg_globals.app_config["push_urls"]:
        for push_url in mg_globals.app_config["push_urls"]:
            atomlinks.append({
                'rel': 'hub',
                'href': push_url})

    feed = AtomFeed(
                "MediaGoblin: Feed for %s's collection %s" %
                (request.matchdict['user'], collection.title),
                feed_url=request.url,
                id='tag:{host},{year}:gnu-mediagoblin.{user}.collection.{slug}'\
                    .format(
                    host=request.host,
                    year=collection.created.strftime('%Y'),
                    user=request.matchdict['user'],
                    slug=collection.slug),
                links=atomlinks)

    for item in cursor:
        obj = item.get_object()
        feed.add(
            obj.get('title'),
            item.note_html,
            id=obj.url_for_self(request.urlgen, qualified=True),
            content_type='html',
            author={
                'name': obj.get_actor.username,
                'uri': request.urlgen(
                    'mediagoblin.user_pages.user_home',
                    qualified=True, user=obj.get_actor.username)},
            updated=item.get('added'),
            links=[{
                'href': obj.url_for_self(
                    request.urlgen,
                    qualified=True),
                'rel': 'alternate',
                'type': 'text/html'}])

    return feed.get_response()

@active_user_from_url
@uses_pagination
@require_active_login
def processing_panel(request, page, url_user):
    """
    Show to the user what media is still in conversion/processing...
    and what failed, and why!
    """
    user = LocalUser.query.filter_by(username=request.matchdict['user']).first()
    # TODO: XXX: Should this be a decorator?
    #
    # Make sure we have permission to access this user's panel.  Only
    # admins and this user herself should be able to do so.
    if not (user.id == request.user.id or request.user.has_privilege('admin')):
        # No?  Simply redirect to this user's homepage.
        return redirect(
            request, 'mediagoblin.user_pages.user_home',
            user=user.username)
    # Get media entries which are in-processing
    entries = (MediaEntry.query.filter_by(actor=user.id)
            .order_by(MediaEntry.created.desc()))

    try:
        state = request.matchdict['state']
        # no exception was thrown, filter entries by state
        entries = entries.filter_by(state=state)
    except KeyError:
        # show all entries
        pass

    pagination = Pagination(page, entries)
    pagination.per_page = 30
    entries_on_a_page = pagination()

    # Render to response
    return render_to_response(
        request,
        'mediagoblin/user_pages/processing_panel.html',
        {'user': user,
         'entries': entries_on_a_page,
         'pagination': pagination})

@allow_reporting
@get_user_media_entry
@user_has_privilege('reporter')
@get_optional_media_comment_by_id
def file_a_report(request, media, comment):
    """
    This view handles the filing of a Report.
    """
    if comment is not None:
        if not comment.target().id == media.id:
            return render_404(request)

        form = user_forms.CommentReportForm(request.form)
        context = {'media': comment.target(),
                   'comment':comment,
                   'form':form}
    else:
        form = user_forms.MediaReportForm(request.form)
        context = {'media': media,
                   'form':form}
    form.reporter_id.data = request.user.id


    if request.method == "POST":
        report_object = build_report_object(
            form,
            media_entry=media,
            comment=comment
        )

        # if the object was built successfully, report_table will not be None
        if report_object:
            report_object.save()
            return redirect(
                request,
                'index')


    return render_to_response(
        request,
        'mediagoblin/user_pages/report.html',
        context)

@require_active_login
def activity_view(request):
    """ /<username>/activity/<id> - Display activity

    This should display a HTML presentation of the activity
    this is NOT an API endpoint.
    """
    # Get the user object.
    username = request.matchdict["username"]
    user = LocalUser.query.filter_by(username=username).first()

    activity_id = request.matchdict["id"]

    if request.user is None:
        return render_404(request)

    activity = Activity.query.filter_by(
        id=activity_id,
        author=user.id
    ).first()

    # There isn't many places to check that the public_id is filled so this
    # will do, it really should be, lets try and fix that if it isn't.
    activity.get_public_id(request.urlgen)

    if activity is None:
        return render_404(request)

    return render_to_response(
        request,
        "mediagoblin/api/activity.html",
        {"activity": activity}
    )
