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

try:
    from unittest import mock
except ImportError:
    import unittest.mock as mock
import pytest

from webtest import AppError

from .resources import GOOD_JPG
from mediagoblin import mg_globals
from mediagoblin.db.models import User, MediaEntry, TextComment
from mediagoblin.tests.tools import fixture_add_user
from mediagoblin.moderation.tools import take_away_privileges


class TestAPI:
    """ Test mediagoblin's pump.io complient APIs """

    @pytest.fixture(autouse=True)
    def setup(self, test_app):
        self.test_app = test_app
        self.db = mg_globals.database

        self.user = fixture_add_user(privileges=['active', 'uploader',
                                                 'commenter'])
        self.other_user = fixture_add_user(
            username="otheruser",
            privileges=['active', 'uploader', 'commenter']
        )
        self.active_user = self.user

    def _activity_to_feed(self, test_app, activity, headers=None):
        """ Posts an activity to the user's feed """
        if headers:
            headers.setdefault("Content-Type", "application/json")
        else:
            headers = {"Content-Type": "application/json"}

        with self.mock_oauth():
            response = test_app.post(
                "/api/user/{}/feed".format(self.active_user.username),
                json.dumps(activity),
                headers=headers
            )

        return response, json.loads(response.body.decode())

    def _upload_image(self, test_app, image, custom_filename=None):
        """ Uploads and image to MediaGoblin via pump.io API """
        data = open(image, "rb").read()
        headers = {
            "Content-Type": "image/jpeg",
            "Content-Length": str(len(data))
        }

        if custom_filename is not None:
            headers["X-File-Name"] = custom_filename

        with self.mock_oauth():
            response = test_app.post(
                "/api/user/{}/uploads".format(self.active_user.username),
                data,
                headers=headers
            )
            image = json.loads(response.body.decode())

        return response, image

    def _post_image_to_feed(self, test_app, image):
        """ Posts an already uploaded image to feed """
        activity = {
            "verb": "post",
            "object": image,
        }

        return self._activity_to_feed(test_app, activity)

    def mocked_oauth_required(self, *args, **kwargs):
        """ Mocks mediagoblin.decorator.oauth_required to always validate """

        def fake_controller(controller, request, *args, **kwargs):
            request.user = User.query.filter_by(id=self.active_user.id).first()
            return controller(request, *args, **kwargs)

        def oauth_required(c):
            return lambda *args, **kwargs: fake_controller(c, *args, **kwargs)

        return oauth_required

    def mock_oauth(self):
        """ Returns a mock.patch for the oauth_required decorator """
        return mock.patch(
            target="mediagoblin.decorators.oauth_required",
            new_callable=self.mocked_oauth_required
        )

    def test_can_post_image(self, test_app):
        """ Tests that an image can be posted to the API """
        # First request we need to do is to upload the image
        response, image = self._upload_image(test_app, GOOD_JPG)

        # I should have got certain things back
        assert response.status_code == 200

        assert "id" in image
        assert "fullImage" in image
        assert "url" in image["fullImage"]
        assert "url" in image
        assert "author" in image
        assert "published" in image
        assert "updated" in image
        assert image["objectType"] == "image"

        # Check that we got the response we're expecting
        response, data = self._post_image_to_feed(test_app, image)
        assert response.status_code == 200
        # mimetypes.guess_all_extensions gives a different result depending on Python version:
        # .jpe on Debian 10
        # .jfif on Debian 11
        assert (
            data["object"]["fullImage"]["url"].endswith("unknown.jpe")
            or data["object"]["fullImage"]["url"].endswith("unknown.jfif")
        )
        assert (
            data["object"]["image"]["url"].endswith("unknown.thumbnail.jpe")
            or data["object"]["image"]["url"].endswith("unknown.thumbnail.jfif")
        )

    def test_can_post_image_custom_filename(self, test_app):
        """ Tests an image can be posted to the API with custom filename """
        # First request we need to do is to upload the image
        response, image = self._upload_image(test_app, GOOD_JPG,
                                             custom_filename="hello.jpg")

        # I should have got certain things back
        assert response.status_code == 200

        assert "id" in image
        assert "fullImage" in image
        assert "url" in image["fullImage"]
        assert "url" in image
        assert "author" in image
        assert "published" in image
        assert "updated" in image
        assert image["objectType"] == "image"

        # Check that we got the response we're expecting
        response, data = self._post_image_to_feed(test_app, image)
        assert response.status_code == 200
        assert data["object"]["fullImage"]["url"].endswith("hello.jpg")
        assert data["object"]["image"]["url"].endswith("hello.thumbnail.jpg")

    def test_can_post_image_tags(self, test_app):
        """ Tests that an image can be posted to the API """
        # First request we need to do is to upload the image
        response, image = self._upload_image(test_app, GOOD_JPG)
        assert response.status_code == 200

        image["tags"] = ["hello", "world"]

        # Check that we got the response we're expecting
        response, data = self._post_image_to_feed(test_app, image)
        assert response.status_code == 200
        assert data["object"]["tags"] == ["hello", "world"]

    def test_unable_to_upload_as_someone_else(self, test_app):
        """ Test that can't upload as someoen else """
        data = open(GOOD_JPG, "rb").read()
        headers = {
            "Content-Type": "image/jpeg",
            "Content-Length": str(len(data))
        }

        with self.mock_oauth():
            # Will be self.user trying to upload as self.other_user
            with pytest.raises(AppError) as excinfo:
                test_app.post(
                    "/api/user/{}/uploads".format(self.other_user.username),
                    data,
                    headers=headers
                )

            assert "403 FORBIDDEN" in excinfo.value.args[0]

    def test_unable_to_post_feed_as_someone_else(self, test_app):
        """ Tests that can't post an image to someone else's feed """
        response, data = self._upload_image(test_app, GOOD_JPG)

        activity = {
            "verb": "post",
            "object": data
        }

        headers = {
            "Content-Type": "application/json",
        }

        with self.mock_oauth():
            with pytest.raises(AppError) as excinfo:
                test_app.post(
                    "/api/user/{}/feed".format(self.other_user.username),
                    json.dumps(activity),
                    headers=headers
                )

            assert "403 FORBIDDEN" in excinfo.value.args[0]

    def test_only_able_to_update_own_image(self, test_app):
        """ Test uploader is the only person who can update an image """
        response, data = self._upload_image(test_app, GOOD_JPG)
        response, data = self._post_image_to_feed(test_app, data)

        activity = {
            "verb": "update",
            "object": data["object"],
        }

        headers = {
            "Content-Type": "application/json",
        }

        # Lets change the image uploader to be self.other_user, this is easier
        # than uploading the image as someone else as the way
        # self.mocked_oauth_required and self._upload_image.
        media = MediaEntry.query \
            .filter_by(public_id=data["object"]["id"]) \
            .first()
        media.actor = self.other_user.id
        media.save()

        # Now lets try and edit the image as self.user, this should produce a
        # 403 error.
        with self.mock_oauth():
            with pytest.raises(AppError) as excinfo:
                test_app.post(
                    "/api/user/{}/feed".format(self.user.username),
                    json.dumps(activity),
                    headers=headers
                )

            assert "403 FORBIDDEN" in excinfo.value.args[0]

    def test_upload_image_with_filename(self, test_app):
        """ Tests that you can upload an image with filename and description """
        response, data = self._upload_image(test_app, GOOD_JPG)
        response, data = self._post_image_to_feed(test_app, data)

        image = data["object"]

        # Now we need to add a title and description
        title = "My image ^_^"
        description = "This is my super awesome image :D"
        license = "CC-BY-SA"

        image["displayName"] = title
        image["content"] = description
        image["license"] = license

        activity = {"verb": "update", "object": image}

        with self.mock_oauth():
            response = test_app.post(
                "/api/user/{}/feed".format(self.user.username),
                json.dumps(activity),
                headers={"Content-Type": "application/json"}
            )

        image = json.loads(response.body.decode())["object"]

        # Check everything has been set on the media correctly
        media = MediaEntry.query.filter_by(public_id=image["id"]).first()
        assert media.title == title
        assert media.description == description
        assert media.license == license

        # Check we're being given back everything we should on an update
        assert image["id"] == media.public_id
        assert image["displayName"] == title
        assert image["content"] == description
        assert image["license"] == license

    def test_only_uploaders_post_image(self, test_app):
        """ Test that only uploaders can upload images """
        # Remove uploader permissions from user
        take_away_privileges(self.user.username, "uploader")

        # Now try and upload a image
        data = open(GOOD_JPG, "rb").read()
        headers = {
            "Content-Type": "image/jpeg",
            "Content-Length": str(len(data)),
        }

        with self.mock_oauth():
            with pytest.raises(AppError) as excinfo:
                test_app.post(
                    "/api/user/{}/uploads".format(self.user.username),
                    data,
                    headers=headers
                )

            # Assert that we've got a 403
            assert "403 FORBIDDEN" in excinfo.value.args[0]

    def test_object_endpoint(self, test_app):
        """ Tests that object can be looked up at endpoint """
        # Post an image
        response, data = self._upload_image(test_app, GOOD_JPG)
        response, data = self._post_image_to_feed(test_app, data)

        # Now lookup image to check that endpoint works.
        image = data["object"]

        assert "links" in image
        assert "self" in image["links"]

        # Get URI and strip testing host off
        object_uri = image["links"]["self"]["href"]
        object_uri = object_uri.replace("http://localhost:80", "")

        with self.mock_oauth():
            request = test_app.get(object_uri)

        image = json.loads(request.body.decode())
        entry = MediaEntry.query.filter_by(public_id=image["id"]).first()

        assert entry is not None

        assert request.status_code == 200

        assert "image" in image
        assert "fullImage" in image
        assert "pump_io" in image
        assert "links" in image
        assert "tags" in image

    def test_post_comment(self, test_app):
        """ Tests that I can post an comment media """
        # Upload some media to comment on
        response, data = self._upload_image(test_app, GOOD_JPG)
        response, data = self._post_image_to_feed(test_app, data)

        content = "Hai this is a comment on this lovely picture ^_^"

        activity = {
            "verb": "post",
            "object": {
                "objectType": "comment",
                "content": content,
                "inReplyTo": data["object"],
            }
        }

        response, comment_data = self._activity_to_feed(test_app, activity)
        assert response.status_code == 200

        # Find the objects in the database
        media = MediaEntry.query \
            .filter_by(public_id=data["object"]["id"]) \
            .first()
        comment = media.get_comments()[0].comment()

        # Tests that it matches in the database
        assert comment.actor == self.user.id
        assert comment.content == content

        # Test that the response is what we should be given
        assert comment.content == comment_data["object"]["content"]

    def test_unable_to_post_comment_as_someone_else(self, test_app):
        """ Tests that you're unable to post a comment as someone else. """
        # Upload some media to comment on
        response, data = self._upload_image(test_app, GOOD_JPG)
        response, data = self._post_image_to_feed(test_app, data)

        activity = {
            "verb": "post",
            "object": {
                "objectType": "comment",
                "content": "comment commenty comment ^_^",
                "inReplyTo": data["object"],
            }
        }

        headers = {
            "Content-Type": "application/json",
        }

        with self.mock_oauth():
            with pytest.raises(AppError) as excinfo:
                test_app.post(
                    "/api/user/{}/feed".format(self.other_user.username),
                    json.dumps(activity),
                    headers=headers
                )

            assert "403 FORBIDDEN" in excinfo.value.args[0]

    def test_unable_to_update_someone_elses_comment(self, test_app):
        """ Test that you're able to update someoen elses comment. """
        # Upload some media to comment on
        response, data = self._upload_image(test_app, GOOD_JPG)
        response, data = self._post_image_to_feed(test_app, data)

        activity = {
            "verb": "post",
            "object": {
                "objectType": "comment",
                "content": "comment commenty comment ^_^",
                "inReplyTo": data["object"],
            }
        }

        headers = {
            "Content-Type": "application/json",
        }

        # Post the comment.
        response, comment_data = self._activity_to_feed(test_app, activity)

        # change who uploaded the comment as it's easier than changing
        comment = TextComment.query \
            .filter_by(public_id=comment_data["object"]["id"]) \
            .first()
        comment.actor = self.other_user.id
        comment.save()

        # Update the comment as someone else.
        comment_data["object"]["content"] = "Yep"
        activity = {
            "verb": "update",
            "object": comment_data["object"]
        }

        with self.mock_oauth():
            with pytest.raises(AppError) as excinfo:
                test_app.post(
                    "/api/user/{}/feed".format(self.user.username),
                    json.dumps(activity),
                    headers=headers
                )

            assert "403 FORBIDDEN" in excinfo.value.args[0]

    def test_profile(self, test_app):
        """ Tests profile endpoint """
        uri = "/api/user/{}/profile".format(self.user.username)
        with self.mock_oauth():
            response = test_app.get(uri)
            profile = json.loads(response.body.decode())

            assert response.status_code == 200

            assert profile["preferredUsername"] == self.user.username
            assert profile["objectType"] == "person"

            assert "links" in profile

    def test_user(self, test_app):
        """ Test the user endpoint """
        uri = "/api/user/{}/".format(self.user.username)
        with self.mock_oauth():
            response = test_app.get(uri)
            user = json.loads(response.body.decode())

            assert response.status_code == 200

            assert user["nickname"] == self.user.username
            assert user["updated"] == self.user.created.isoformat()
            assert user["published"] == self.user.created.isoformat()

            # Test profile exists but self.test_profile will test the value
            assert "profile" in response

    def test_whoami_without_login(self, test_app):
        """ Test that whoami endpoint returns error when not logged in """
        with pytest.raises(AppError) as excinfo:
            test_app.get("/api/whoami")

        assert "401 UNAUTHORIZED" in excinfo.value.args[0]

    def test_read_feed(self, test_app):
        """ Test able to read objects from the feed """
        response, image_data = self._upload_image(test_app, GOOD_JPG)
        response, data = self._post_image_to_feed(test_app, image_data)

        uri = "/api/user/{}/feed".format(self.active_user.username)
        with self.mock_oauth():
            response = test_app.get(uri)
            feed = json.loads(response.body.decode())

            assert response.status_code == 200

            # Check it has the attributes it should
            assert "displayName" in feed
            assert "objectTypes" in feed
            assert "url" in feed
            assert "links" in feed
            assert "author" in feed
            assert "items" in feed

            # Check that image i uploaded is there
            assert feed["items"][0]["verb"] == "post"
            assert feed["items"][0]["id"] == data["id"]
            assert feed["items"][0]["object"]["objectType"] == "image"
            assert feed["items"][0]["object"]["id"] == data["object"]["id"]

        default_limit = 20
        items_count = default_limit * 2
        for i in range(items_count):
            response, image_data = self._upload_image(test_app, GOOD_JPG)
            self._post_image_to_feed(test_app, image_data)
        items_count += 1  # because there already is one

        #
        # default returns default_limit items
        #
        with self.mock_oauth():
            response = test_app.get(uri)
            feed = json.loads(response.body.decode())
            assert len(feed["items"]) == default_limit

        #
        # silentely ignore count and offset that that are
        # not a number
        #
        with self.mock_oauth():
            response = test_app.get(uri + "?count=BAD&offset=WORSE")
            feed = json.loads(response.body.decode())
            assert len(feed["items"]) == default_limit

        #
        # if offset is less than default_limit items
        # from the end of the feed, return less than
        # default_limit
        #
        with self.mock_oauth():
            near_the_end = items_count - default_limit / 2
            response = test_app.get(uri + "?offset=%d" % near_the_end)
            feed = json.loads(response.body.decode())
            assert len(feed["items"]) < default_limit

        #
        # count=5 returns 5 items
        #
        with self.mock_oauth():
            response = test_app.get(uri + "?count=5")
            feed = json.loads(response.body.decode())
            assert len(feed["items"]) == 5

    def test_read_another_feed(self, test_app):
        """ Test able to read objects from someone else's feed """
        response, data = self._upload_image(test_app, GOOD_JPG)
        response, data = self._post_image_to_feed(test_app, data)

        # Change the active user to someone else.
        self.active_user = self.other_user

        # Fetch the feed
        url = "/api/user/{}/feed".format(self.user.username)
        with self.mock_oauth():
            response = test_app.get(url)
            feed = json.loads(response.body.decode())

            assert response.status_code == 200

            # Check it has the attributes it ought to.
            assert "displayName" in feed
            assert "objectTypes" in feed
            assert "url" in feed
            assert "links" in feed
            assert "author" in feed
            assert "items" in feed

            # Assert the uploaded image is there
            assert feed["items"][0]["verb"] == "post"
            assert feed["items"][0]["id"] == data["id"]
            assert feed["items"][0]["object"]["objectType"] == "image"
            assert feed["items"][0]["object"]["id"] == data["object"]["id"]

    def test_cant_post_to_someone_elses_feed(self, test_app):
        """ Test that can't post to someone elses feed """
        response, data = self._upload_image(test_app, GOOD_JPG)
        self.active_user = self.other_user

        with self.mock_oauth():
            with pytest.raises(AppError) as excinfo:
                self._post_image_to_feed(test_app, data)

            assert "403 FORBIDDEN" in excinfo.value.args[0]

    def test_object_endpoint_requestable(self, test_app):
        """ Test that object endpoint can be requested """
        response, data = self._upload_image(test_app, GOOD_JPG)
        response, data = self._post_image_to_feed(test_app, data)
        object_id = data["object"]["id"]

        with self.mock_oauth():
            response = test_app.get(data["object"]["links"]["self"]["href"])
            data = json.loads(response.body.decode())

            assert response.status_code == 200

            assert object_id == data["id"]
            assert "url" in data
            assert "links" in data
            assert data["objectType"] == "image"

    def test_delete_media_by_activity(self, test_app):
        """ Test that an image can be deleted by a delete activity to feed """
        response, data = self._upload_image(test_app, GOOD_JPG)
        response, data = self._post_image_to_feed(test_app, data)
        object_id = data["object"]["id"]

        activity = {
            "verb": "delete",
            "object": {
                "id": object_id,
                "objectType": "image",
            }
        }

        response = self._activity_to_feed(test_app, activity)[1]

        # Check the media is no longer in the database
        media = MediaEntry.query.filter_by(public_id=object_id).first()

        assert media is None

        # Check we've been given the full delete activity back
        assert "id" in response
        assert response["verb"] == "delete"
        assert "object" in response
        assert response["object"]["id"] == object_id
        assert response["object"]["objectType"] == "image"

    def test_delete_comment_by_activity(self, test_app):
        """ Test that a comment is deleted by a delete activity to feed """
        # First upload an image to comment against
        response, data = self._upload_image(test_app, GOOD_JPG)
        response, data = self._post_image_to_feed(test_app, data)

        # Post a comment to delete
        activity = {
            "verb": "post",
            "object": {
                "objectType": "comment",
                "content": "This is a comment.",
                "inReplyTo": data["object"],
            }
        }

        comment = self._activity_to_feed(test_app, activity)[1]

        # Now delete the image
        activity = {
            "verb": "delete",
            "object": {
                "id": comment["object"]["id"],
                "objectType": "comment",
            }
        }

        delete = self._activity_to_feed(test_app, activity)[1]

        # Verify the comment no longer exists
        assert TextComment.query \
            .filter_by(public_id=comment["object"]["id"]) \
            .first() is None

        assert "id" in comment["object"]

        # Check we've got a delete activity back
        assert "id" in delete
        assert delete["verb"] == "delete"
        assert "object" in delete
        assert delete["object"]["id"] == comment["object"]["id"]
        assert delete["object"]["objectType"] == "comment"

    def test_edit_comment(self, test_app):
        """ Test that someone can update their own comment """
        # First upload an image to comment against
        response, data = self._upload_image(test_app, GOOD_JPG)
        response, data = self._post_image_to_feed(test_app, data)

        # Post a comment to edit
        activity = {
            "verb": "post",
            "object": {
                "objectType": "comment",
                "content": "This is a comment",
                "inReplyTo": data["object"],
            }
        }

        comment = self._activity_to_feed(test_app, activity)[1]

        # Now create an update activity to change the content
        activity = {
            "verb": "update",
            "object": {
                "id": comment["object"]["id"],
                "content": "This is my fancy new content string!",
                "objectType": "comment",
            },
        }

        comment = self._activity_to_feed(test_app, activity)[1]

        # Verify the comment reflects the changes
        model = TextComment.query \
            .filter_by(public_id=comment["object"]["id"]) \
            .first()

        assert model.content == activity["object"]["content"]
