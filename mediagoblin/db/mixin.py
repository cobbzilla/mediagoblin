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

"""
This module contains some Mixin classes for the db objects.

A bunch of functions on the db objects are really more like
"utility functions": They could live outside the classes
and be called "by hand" passing the appropiate reference.
They usually only use the public API of the object and
rarely use database related stuff.

These functions now live here and get "mixed in" into the
real objects.
"""

import uuid
import re
from datetime import datetime

from pytz import UTC
from werkzeug.utils import cached_property

from mediagoblin.media_types import FileTypeNotSupported
from mediagoblin.tools import common, licenses
from mediagoblin.tools.pluginapi import hook_handle
from mediagoblin.tools.text import cleaned_markdown_conversion
from mediagoblin.tools.url import slugify
from mediagoblin.tools.translate import pass_to_ugettext as _

class CommentingMixin:
    """
    Mixin that gives classes methods to get and add the comments on/to it

    This assumes the model has a "comments" class which is a ForeignKey to the
    Collection model. This will hold a Collection of comments which are
    associated to this model. It also assumes the model has an "actor"
    ForeignKey which points to the creator/publisher/etc. of the model.

    NB: This is NOT the mixin for the Comment Model, this is for
        other models which support commenting.
    """

    def get_comment_link(self):
        # Import here to avoid cyclic imports
        from mediagoblin.db.models import Comment, GenericModelReference

        gmr = GenericModelReference.query.filter_by(
            obj_pk=self.id,
            model_type=self.__tablename__
        ).first()

        if gmr is None:
            return None

        link = Comment.query.filter_by(comment_id=gmr.id).first()
        return link

    def get_reply_to(self):
        link = self.get_comment_link()
        if link is None or link.target_id is None:
            return None

        return link.target()

    def soft_delete(self, *args, **kwargs):
        link = self.get_comment_link()
        if link is not None:
            link.delete()
        super().soft_delete(*args, **kwargs)

class GeneratePublicIDMixin:
    """
    Mixin that ensures that a the public_id field is populated.

    The public_id is the ID that is used in the API, this must be globally
    unique and dereferencable. This will be the URL for the API view of the
    object. It's used in several places, not only is it used to give out via
    the API but it's also vital information stored when a soft_deletion occurs
    on the `Graveyard.public_id` field, this is needed to follow the spec which
    says we have to be able to provide a shell of an object and return a 410
    (rather than a 404) when a deleted object has been deleted.

    This requires a the urlgen off the request object (`request.urlgen`) to be
    provided as it's the ID is a URL.
    """

    def get_public_id(self, urlgen):
        # Verify that the class this is on actually has a public_id field...
        if "public_id" not in self.__table__.columns.keys():
            raise Exception("Model has no public_id field")

        # Great! the model has a public id, if it's None, let's create one!
        if self.public_id is None:
            # We need the internal ID for this so ensure we've been saved.
            self.save(commit=False)

            # Create the URL
            self.public_id = urlgen(
                "mediagoblin.api.object",
                object_type=self.object_type,
                id=str(uuid.uuid4()),
                qualified=True
            )
            self.save()
        return self.public_id

class UserMixin:
    object_type = "person"

    @property
    def bio_html(self):
        return cleaned_markdown_conversion(self.bio)

    def url_for_self(self, urlgen, **kwargs):
        """Generate a URL for this User's home page."""
        return urlgen('mediagoblin.user_pages.user_home',

                      user=self.username, **kwargs)


class GenerateSlugMixin:
    """
    Mixin to add a generate_slug method to objects.

    Depends on:
     - self.slug
     - self.title
     - self.check_slug_used(new_slug)
    """
    def generate_slug(self):
        """
        Generate a unique slug for this object.

        This one does not *force* slugs, but usually it will probably result
        in a niceish one.

        The end *result* of the algorithm will result in these resolutions for
        these situations:
         - If we have a slug, make sure it's clean and sanitized, and if it's
           unique, we'll use that.
         - If we have a title, slugify it, and if it's unique, we'll use that.
         - If we can't get any sort of thing that looks like it'll be a useful
           slug out of a title or an existing slug, bail, and don't set the
           slug at all.  Don't try to create something just because.  Make
           sure we have a reasonable basis for a slug first.
         - If we have a reasonable basis for a slug (either based on existing
           slug or slugified title) but it's not unique, first try appending
           the entry's id, if that exists
         - If that doesn't result in something unique, tack on some randomly
           generated bits until it's unique.  That'll be a little bit of junk,
           but at least it has the basis of a nice slug.
        """

        #Is already a slug assigned? Check if it is valid
        if self.slug:
            slug = slugify(self.slug)

        # otherwise, try to use the title.
        elif self.title:
            # assign slug based on title
            slug = slugify(self.title)

        else:
            # We don't have any information to set a slug
            return

        # We don't want any empty string slugs
        if slug == "":
            return

        # Otherwise, let's see if this is unique.
        if self.check_slug_used(slug):
            # It looks like it's being used... lame.

            # Can we just append the object's id to the end?
            if self.id:
                slug_with_id = "{}-{}".format(slug, self.id)
                if not self.check_slug_used(slug_with_id):
                    self.slug = slug_with_id
                    return  # success!

            # okay, still no success;
            # let's whack junk on there till it's unique.
            slug += '-' + uuid.uuid4().hex[:4]
            # keep going if necessary!
            while self.check_slug_used(slug):
                slug += uuid.uuid4().hex[:4]

        # self.check_slug_used(slug) must be False now so we have a slug that
        # we can use now.
        self.slug = slug


class MediaEntryMixin(GenerateSlugMixin, GeneratePublicIDMixin):
    def check_slug_used(self, slug):
        # import this here due to a cyclic import issue
        # (db.models -> db.mixin -> db.util -> db.models)
        from mediagoblin.db.util import check_media_slug_used

        return check_media_slug_used(self.actor, slug, self.id)

    @property
    def object_type(self):
        """ Converts media_type to pump-like type - don't use internally """
        return self.media_type.split(".")[-1]

    @property
    def description_html(self):
        """
        Rendered version of the description, run through
        Markdown and cleaned with our cleaning tool.
        """
        return cleaned_markdown_conversion(self.description)

    def get_display_media(self):
        """Find the best media for display.

        We try checking self.media_manager.fetching_order if it exists to
        pull down the order.

        Returns:
          (media_size, media_path)
          or, if not found, None.

        """
        fetch_order = self.media_manager.media_fetch_order

        # No fetching order found?  well, give up!
        if not fetch_order:
            return None

        media_sizes = self.media_files.keys()

        for media_size in fetch_order:
            if media_size in media_sizes:
                return media_size, self.media_files[media_size]

    def get_all_media(self):
        """
        Returns all available qualties of a media (except original)
        """
        fetch_order = self.media_manager.media_fetch_order

        # No fetching order found?  well, give up!
        if not fetch_order:
            return None

        media_sizes = self.media_files.keys()

        all_media_path = []

        for media_size in fetch_order:
            if media_size in media_sizes and media_size != 'original':
                file_metadata = self.get_file_metadata(media_size)
                size = file_metadata['medium_size']
                if media_size != 'webm_video':
                    all_media_path.append((media_size[5:], size,
                                           self.media_files[media_size]))
                else:
                    all_media_path.append(('default', size,
                                           self.media_files[media_size]))

        return all_media_path

    def main_mediafile(self):
        pass

    @property
    def slug_or_id(self):
        if self.slug:
            return self.slug
        else:
            return 'id:%s' % self.id

    def url_for_self(self, urlgen, **extra_args):
        """
        Generate an appropriate url for ourselves

        Use a slug if we have one, else use our 'id'.
        """
        uploader = self.get_actor

        return urlgen(
            'mediagoblin.user_pages.media_home',
            user=uploader.username,
            media=self.slug_or_id,
            **extra_args)

    @property
    def thumb_url(self):
        """Return the thumbnail URL (for usage in templates)
        Will return either the real thumbnail or a default fallback icon."""
        # TODO: implement generic fallback in case MEDIA_MANAGER does
        # not specify one?
        if 'thumb' in self.media_files:
            thumb_url = self._app.public_store.file_url(
                            self.media_files['thumb'])
        else:
            # No thumbnail in media available. Get the media's
            # MEDIA_MANAGER for the fallback icon and return static URL
            # Raises FileTypeNotSupported in case no such manager is enabled
            manager = self.media_manager
            thumb_url = self._app.staticdirector(manager['default_thumb'])
        return thumb_url

    @property
    def original_url(self):
        """ Returns the URL for the original image
        will return self.thumb_url if original url doesn't exist"""
        if "original" not in self.media_files:
            return self.thumb_url

        return self._app.public_store.file_url(
            self.media_files["original"]
            )

    @property
    def icon_url(self):
        '''Return the icon URL (for usage in templates) if it exists'''
        try:
            return self._app.staticdirector(
                    self.media_manager['type_icon'])
        except AttributeError:
            return None

    @cached_property
    def media_manager(self):
        """Returns the MEDIA_MANAGER of the media's media_type

        Raises FileTypeNotSupported in case no such manager is enabled
        """
        manager = hook_handle(('media_manager', self.media_type))
        if manager:
            return manager(self)

        # Not found?  Then raise an error
        raise FileTypeNotSupported(
            "MediaManager not in enabled types. Check media_type plugins are"
            " enabled in config?")

    def get_fail_exception(self):
        """
        Get the exception that's appropriate for this error
        """
        if self.fail_error:
            try:
                return common.import_component(self.fail_error)
            except ImportError:
                # TODO(breton): fail_error should give some hint about why it
                # failed. fail_error is used as a path to import().
                # Unfortunately, I didn't know about that and put general error
                # message there. Maybe it's for the best, because for admin,
                # we could show even some raw python things. Anyway, this
                # should be properly resolved. Now we are in a freeze, that's
                # why I simply catch ImportError.
                return None

    def get_license_data(self):
        """Return license dict for requested license"""
        return licenses.get_license_by_url(self.license or "")

    def exif_display_iter(self):
        if not self.media_data:
            return
        exif_all = self.media_data.get("exif_all")

        for key in exif_all:
            label = re.sub('(.)([A-Z][a-z]+)', r'\1 \2', key)
            yield label.replace('EXIF', '').replace('Image', ''), exif_all[key]

    def exif_display_data_short(self):
        """Display a very short practical version of exif info"""
        if not self.media_data:
            return

        exif_all = self.media_data.get("exif_all")

        exif_short = {}

        if 'Image DateTimeOriginal' in exif_all:
            # format date taken
            takendate = datetime.strptime(
                exif_all['Image DateTimeOriginal']['printable'],
                '%Y:%m:%d %H:%M:%S').date()
            taken = takendate.strftime('%B %d %Y')

            exif_short.update({'Date Taken': taken})

        aperture = None
        if 'EXIF FNumber' in exif_all:
            fnum = str(exif_all['EXIF FNumber']['printable']).split('/')

            # calculate aperture
            if len(fnum) == 2:
                aperture = "f/%.1f" % (float(fnum[0])/float(fnum[1]))
            elif fnum[0] != 'None':
                aperture = "f/%s" % (fnum[0])

        if aperture:
            exif_short.update({'Aperture': aperture})

        short_keys = [
            ('Camera', 'Image Model', None),
            ('Exposure', 'EXIF ExposureTime', lambda x: '%s sec' % x),
            ('ISO Speed', 'EXIF ISOSpeedRatings', None),
            ('Focal Length', 'EXIF FocalLength', lambda x: '%s mm' % x)]

        for label, key, fmt_func in short_keys:
            try:
                val = fmt_func(exif_all[key]['printable']) if fmt_func \
                        else exif_all[key]['printable']
                exif_short.update({label: val})
            except KeyError:
                pass

        return exif_short


class TextCommentMixin(GeneratePublicIDMixin):
    object_type = "comment"

    @property
    def content_html(self):
        """
        the actual html-rendered version of the comment displayed.
        Run through Markdown and the HTML cleaner.
        """
        return cleaned_markdown_conversion(self.content)

    def __unicode__(self):
        return '<{klass} #{id} {actor} "{comment}">'.format(
            klass=self.__class__.__name__,
            id=self.id,
            actor=self.get_actor,
            comment=self.content)

    def __repr__(self):
        return '<{klass} #{id} {actor} "{comment}">'.format(
            klass=self.__class__.__name__,
            id=self.id,
            actor=self.get_actor,
            comment=self.content)

class CollectionMixin(GenerateSlugMixin, GeneratePublicIDMixin):
    object_type = "collection"

    def check_slug_used(self, slug):
        # import this here due to a cyclic import issue
        # (db.models -> db.mixin -> db.util -> db.models)
        from mediagoblin.db.util import check_collection_slug_used

        return check_collection_slug_used(self.actor, slug, self.id)

    @property
    def description_html(self):
        """
        Rendered version of the description, run through
        Markdown and cleaned with our cleaning tool.
        """
        return cleaned_markdown_conversion(self.description)

    @property
    def slug_or_id(self):
        return (self.slug or self.id)

    def url_for_self(self, urlgen, **extra_args):
        """
        Generate an appropriate url for ourselves

        Use a slug if we have one, else use our 'id'.
        """
        creator = self.get_actor

        return urlgen(
            'mediagoblin.user_pages.user_collection',
            user=creator.username,
            collection=self.slug_or_id,
            **extra_args)

    def add_to_collection(self, obj, content=None, commit=True):
        """ Adds an object to the collection """
        # It's here to prevent cyclic imports
        from mediagoblin.db.models import CollectionItem

        # Need the ID of this collection for this so check we've got one.
        self.save(commit=False)

        # Create the CollectionItem
        item = CollectionItem()
        item.collection = self.id
        item.get_object = obj

        if content is not None:
            item.note = content

        self.num_items = self.num_items + 1

        # Save both!
        self.save(commit=commit)
        item.save(commit=commit)
        return item

class CollectionItemMixin:
    @property
    def note_html(self):
        """
        the actual html-rendered version of the note displayed.
        Run through Markdown and the HTML cleaner.
        """
        return cleaned_markdown_conversion(self.note)

class ActivityMixin(GeneratePublicIDMixin):
    object_type = "activity"

    VALID_VERBS = ["add", "author", "create", "delete", "dislike", "favorite",
                   "follow", "like", "post", "share", "unfavorite", "unfollow",
                   "unlike", "unshare", "update", "tag"]

    def get_url(self, request):
        return request.urlgen(
            "mediagoblin.user_pages.activity_view",
            username=self.get_actor.username,
            id=self.id,
            qualified=True
        )

    def generate_content(self):
        """ Produces a HTML content for object """
        # some of these have simple and targetted. If self.target it set
        # it will pick the targetted. If they DON'T have a targetted version
        # the information in targetted won't be added to the content.
        verb_to_content = {
            "add": {
                "simple" : _("{username} added {object}"),
                "targetted":  _("{username} added {object} to {target}"),
            },
            "author": {"simple": _("{username} authored {object}")},
            "create": {"simple": _("{username} created {object}")},
            "delete": {"simple": _("{username} deleted {object}")},
            "dislike": {"simple": _("{username} disliked {object}")},
            "favorite": {"simple": _("{username} favorited {object}")},
            "follow": {"simple": _("{username} followed {object}")},
            "like": {"simple": _("{username} liked {object}")},
            "post": {
                "simple": _("{username} posted {object}"),
                "targetted": _("{username} posted {object} to {target}"),
            },
            "share": {"simple": _("{username} shared {object}")},
            "unfavorite": {"simple": _("{username} unfavorited {object}")},
            "unfollow": {"simple": _("{username} stopped following {object}")},
            "unlike": {"simple": _("{username} unliked {object}")},
            "unshare": {"simple": _("{username} unshared {object}")},
            "update": {"simple": _("{username} updated {object}")},
            "tag": {"simple": _("{username} tagged {object}")},
        }

        object_map = {
            "image": _("an image"),
            "comment": _("a comment"),
            "collection": _("a collection"),
            "video": _("a video"),
            "audio": _("audio"),
            "person": _("a person"),
        }
        obj = self.object()
        target = None if self.target_id is None else self.target()
        actor = self.get_actor
        content = verb_to_content.get(self.verb, None)

        if content is None or self.object is None:
            return

        # Decide what to fill the object with
        if hasattr(obj, "title") and obj.title.strip(" "):
            object_value = obj.title
        elif obj.object_type in object_map:
            object_value = object_map[obj.object_type]
        else:
            object_value = _("an object")

        # Do we want to add a target (indirect object) to content?
        if target is not None and "targetted" in content:
            if hasattr(target, "title") and target.title.strip(" "):
                target_value = target.title
            elif target.object_type in object_map:
                target_value = object_map[target.object_type]
            else:
                target_value = _("an object")

            self.content = content["targetted"].format(
                username=actor.username,
                object=object_value,
                target=target_value
            )
        else:
            self.content = content["simple"].format(
                username=actor.username,
                object=object_value
            )

        return self.content

    def serialize(self, request):
        href = request.urlgen(
            "mediagoblin.api.object",
            object_type=self.object_type,
            id=self.id,
            qualified=True
        )
        published = UTC.localize(self.published)
        updated = UTC.localize(self.updated)
        obj = {
            "id": href,
            "actor": self.get_actor.serialize(request),
            "verb": self.verb,
            "published": published.isoformat(),
            "updated": updated.isoformat(),
            "content": self.content,
            "url": self.get_url(request),
            "object": self.object().serialize(request),
            "objectType": self.object_type,
            "links": {
                "self": {
                    "href": href,
                },
            },
        }

        if self.generator:
            obj["generator"] = self.get_generator.serialize(request)

        if self.title:
            obj["title"] = self.title

        if self.target_id is not None:
            obj["target"] = self.target().serialize(request)

        return obj

    def unseralize(self, data):
        """
        Takes data given and set it on this activity.

        Several pieces of data are not written on because of security
        reasons. For example changing the author or id of an activity.
        """
        if "verb" in data:
            self.verb = data["verb"]

        if "title" in data:
            self.title = data["title"]

        if "content" in data:
            self.content = data["content"]
