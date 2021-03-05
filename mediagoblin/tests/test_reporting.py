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

import pytest
from mediagoblin.tools import template
from mediagoblin.tests.tools import (fixture_add_user, fixture_media_entry,
        fixture_add_comment, fixture_add_comment_report)
from mediagoblin.db.models import Report, User, LocalUser, TextComment


class TestReportFiling:
    @pytest.fixture(autouse=True)
    def _setup(self, test_app):
        self.test_app = test_app

        fixture_add_user('allie',
            privileges=['reporter','active'])
        fixture_add_user('natalie',
            privileges=['active', 'moderator'])

    def login(self, username):
        self.test_app.post(
            '/auth/login/', {
                'username': username,
                'password': 'toast'})

    def logout(self):
        self.test_app.get('/auth/logout/')

    def do_post(self, data, *context_keys, **kwargs):
        url = kwargs.pop('url', '/submit/')
        do_follow = kwargs.pop('do_follow', False)
        template.clear_test_template_context()
        response = self.test_app.post(url, data, **kwargs)
        if do_follow:
            response.follow()
        context_data = template.TEMPLATE_TEST_CONTEXT
        for key in context_keys:
            context_data = context_data[key]
        return response, context_data

    def query_for_users(self):
        return (LocalUser.query.filter(LocalUser.username=='allie').first(),
        LocalUser.query.filter(LocalUser.username=='natalie').first())

    def testMediaReports(self):
        self.login('allie')
        allie_user, natalie_user = self.query_for_users()
        allie_id = allie_user.id

        media_entry = fixture_media_entry(uploader=natalie_user.id,
            state='processed')

        mid = media_entry.id
        media_uri_slug = '/u/{}/m/{}/'.format(natalie_user.username,
                                                media_entry.slug)

        response = self.test_app.get(media_uri_slug + "report/")
        assert response.status == "200 OK"

        response, context = self.do_post(
            {'report_reason':'Testing Media Report',
            'reporter_id':str(allie_id)},url= media_uri_slug + "report/")

        assert response.status == "302 FOUND"

        media_report = Report.query.first()

        allie_user, natalie_user = self.query_for_users()
        assert media_report is not None
        assert media_report.report_content == 'Testing Media Report'
        assert media_report.reporter_id == allie_id
        assert media_report.reported_user_id == natalie_user.id
        assert media_report.created is not None

    def testCommentReports(self):
        self.login('allie')
        allie_user, natalie_user = self.query_for_users()
        allie_id = allie_user.id

        media_entry = fixture_media_entry(uploader=natalie_user.id,
            state='processed')
        mid = media_entry.id
        fixture_add_comment(
            media_entry=media_entry,
            author=natalie_user.id
        )
        comment = TextComment.query.first()

        comment_uri_slug = '/u/{}/m/{}/c/{}/'.format(natalie_user.username,
                                                media_entry.slug,
                                                comment.id)

        response = self.test_app.get(comment_uri_slug + "report/")
        assert response.status == "200 OK"

        response, context = self.do_post({
            'report_reason':'Testing Comment Report',
            'reporter_id':str(allie_id)},url= comment_uri_slug + "report/")

        assert response.status == "302 FOUND"

        comment_report = Report.query.first()

        allie_user, natalie_user = self.query_for_users()
        assert comment_report is not None
        assert comment_report.report_content == 'Testing Comment Report'
        assert comment_report.reporter_id == allie_id
        assert comment_report.reported_user_id == natalie_user.id
        assert comment_report.created is not None

    def testArchivingReports(self):
        self.login('natalie')
        allie_user, natalie_user = self.query_for_users()
        allie_id, natalie_id = allie_user.id, natalie_user.id

        fixture_add_comment(author=allie_user.id,
            comment='Comment will be removed')
        test_comment = TextComment.query.filter(
            TextComment.actor==allie_user.id).first()
        fixture_add_comment_report(comment=test_comment,
            reported_user=allie_user,
            report_content='Testing Archived Reports #1',
            reporter=natalie_user)
        comment_report = Report.query.filter(
            Report.reported_user==allie_user).first()

        assert comment_report.report_content == 'Testing Archived Reports #1'
        response, context = self.do_post(
            {'action_to_resolve':['userban', 'delete'],
            'targeted_user':allie_user.id,
            'resolution_content':'This is a test of archiving reports.'},
            url='/mod/reports/{}/'.format(comment_report.id))

        assert response.status == "302 FOUND"
        allie_user, natalie_user = self.query_for_users()

        archived_report = Report.query.filter(
            Report.reported_user==allie_user).first()

        assert Report.query.count() != 0
        assert archived_report is not None
        assert archived_report.report_content == 'Testing Archived Reports #1'
        assert archived_report.reporter_id == natalie_id
        assert archived_report.reported_user_id == allie_id
        assert archived_report.created is not None
        assert archived_report.resolved is not None
        assert archived_report.result == '''This is a test of archiving reports.
natalie banned user allie indefinitely.
natalie deleted the comment.'''
