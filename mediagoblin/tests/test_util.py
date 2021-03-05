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

try:
    from unittest import mock
except ImportError:
    import unittest.mock as mock
import email
import socket
import pytest
import smtplib
import pkg_resources

from mediagoblin.tests.tools import get_app
from mediagoblin import mg_globals
from mediagoblin.tools import common, url, translate, mail, text, testing

testing._activate_testing()


def _import_component_testing_method(silly_string):
    # Just for the sake of testing that our component importer works.
    return "'%s' is the silliest string I've ever seen" % silly_string


def test_import_component():
    imported_func = common.import_component(
        'mediagoblin.tests.test_util:_import_component_testing_method')
    result = imported_func('hooobaladoobala')
    expected = "'hooobaladoobala' is the silliest string I've ever seen"
    assert result == expected


def test_send_email():
    mail._clear_test_inboxes()

    # send the email
    mail.send_email(
        "sender@mediagoblin.example.org",
        ["amanda@example.org", "akila@example.org"],
        "Testing is so much fun!",
        """HAYYY GUYS!

I hope you like unit tests JUST AS MUCH AS I DO!""")

    # check the main inbox
    assert len(mail.EMAIL_TEST_INBOX) == 1
    message = mail.EMAIL_TEST_INBOX.pop()
    assert message['From'] == "sender@mediagoblin.example.org"
    assert message['To'] == "amanda@example.org, akila@example.org"
    assert message['Subject'] == "Testing is so much fun!"
    assert message.get_payload(decode=True) == b"""HAYYY GUYS!

I hope you like unit tests JUST AS MUCH AS I DO!"""

    # Check everything that the FakeMhost.sendmail() method got is correct
    assert len(mail.EMAIL_TEST_MBOX_INBOX) == 1
    mbox_dict = mail.EMAIL_TEST_MBOX_INBOX.pop()
    assert mbox_dict['from'] == "sender@mediagoblin.example.org"
    assert mbox_dict['to'] == ["amanda@example.org", "akila@example.org"]
    mbox_message = email.message_from_string(mbox_dict['message'])
    assert mbox_message['From'] == "sender@mediagoblin.example.org"
    assert mbox_message['To'] == "amanda@example.org, akila@example.org"
    assert mbox_message['Subject'] == "Testing is so much fun!"
    assert mbox_message.get_payload(decode=True) == b"""HAYYY GUYS!

I hope you like unit tests JUST AS MUCH AS I DO!"""

@pytest.fixture()
def starttls_enabled_app(request):
    return get_app(
        request,
        mgoblin_config=pkg_resources.resource_filename(
            "mediagoblin.tests",
            "starttls_config.ini"
        )
    )

def test_email_force_starttls(starttls_enabled_app):
    common.TESTS_ENABLED = False
    SMTP = lambda *args, **kwargs: mail.FakeMhost()
    with mock.patch('smtplib.SMTP', SMTP):
        with pytest.raises(smtplib.SMTPException):
            mail.send_email(
                from_addr="notices@my.test.instance.com",
                to_addrs="someone@someplace.com",
                subject="Testing is so much fun!",
                message_body="Ohai ^_^"
            )

def test_slugify():
    assert url.slugify('a walk in the park') == 'a-walk-in-the-park'
    assert url.slugify('A Walk in the Park') == 'a-walk-in-the-park'
    assert url.slugify('a  walk in the park') == 'a-walk-in-the-park'
    assert url.slugify('a walk in-the-park') == 'a-walk-in-the-park'
    assert url.slugify('a w@lk in the park?') == 'a-w-lk-in-the-park'
    assert url.slugify('a walk in the par\u0107') == 'a-walk-in-the-parc'
    assert url.slugify('\u00E0\u0042\u00E7\u010F\u00EB\u0066') == 'abcdef'
    # Russian
    assert url.slugify('\u043f\u0440\u043e\u0433\u0443\u043b\u043a\u0430 '
            '\u0432 \u043f\u0430\u0440\u043a\u0435') == 'progulka-v-parke'
    # Korean
    assert (url.slugify('\uacf5\uc6d0\uc5d0\uc11c \uc0b0\ucc45') ==
            'gongweoneseo-sancaeg')

def test_locale_to_lower_upper():
    """
    Test cc.i18n.util.locale_to_lower_upper()
    """
    assert translate.locale_to_lower_upper('en') == 'en'
    assert translate.locale_to_lower_upper('en_US') == 'en_US'
    assert translate.locale_to_lower_upper('en-us') == 'en_US'

    # crazy renditions.  Useful?
    assert translate.locale_to_lower_upper('en-US') == 'en_US'
    assert translate.locale_to_lower_upper('en_us') == 'en_US'


def test_locale_to_lower_lower():
    """
    Test cc.i18n.util.locale_to_lower_lower()
    """
    assert translate.locale_to_lower_lower('en') == 'en'
    assert translate.locale_to_lower_lower('en_US') == 'en-us'
    assert translate.locale_to_lower_lower('en-us') == 'en-us'

    # crazy renditions.  Useful?
    assert translate.locale_to_lower_lower('en-US') == 'en-us'
    assert translate.locale_to_lower_lower('en_us') == 'en-us'


def test_gettext_lazy_proxy():
    from mediagoblin.tools.translate import lazy_pass_to_ugettext as _
    from mediagoblin.tools.translate import pass_to_ugettext, set_thread_locale
    proxy = _("Password")
    orig = "Password"

    set_thread_locale("es")
    p1 = str(proxy)
    p1_should = pass_to_ugettext(orig)
    assert p1_should != orig, "Test useless, string not translated"
    assert p1 == p1_should

    set_thread_locale("sv")
    p2 = str(proxy)
    p2_should = pass_to_ugettext(orig)
    assert p2_should != orig, "Test broken, string not translated"
    assert p2 == p2_should

    assert p1_should != p2_should, "Test broken, same translated string"
    assert p1 != p2


def test_html_cleaner():
    # Remove images
    result = text.clean_html(
        '<p>Hi everybody! '
        '<img src="http://example.org/huge-purple-barney.png" /></p>\n'
        '<p>:)</p>')
    assert result == (
        '<div>'
        '<p>Hi everybody! </p>\n'
        '<p>:)</p>'
        '</div>')

    # Remove evil javascript
    result = text.clean_html(
        '<p><a href="javascript:nasty_surprise">innocent link!</a></p>')
    assert result == (
        '<p><a href="">innocent link!</a></p>')


class TestMail:
    """ Test mediagoblin's mail tool """
    def test_no_mail_server(self):
        """ Tests that no smtp server is available """
        with pytest.raises(mail.NoSMTPServerError), mock.patch("smtplib.SMTP") as smtp_mock:
            smtp_mock.side_effect = socket.error
            mg_globals.app_config = {
                "email_debug_mode": False,
                "email_smtp_use_ssl": False,
                "email_smtp_host": "127.0.0.1",
                "email_smtp_port": 0}
            common.TESTS_ENABLED = False
            mail.send_email("", "", "", "")

    def test_no_smtp_host(self):
        """ Empty email_smtp_host """
        with pytest.raises(mail.NoSMTPServerError), mock.patch("smtplib.SMTP") as smtp_mock:
            smtp_mock.return_value.connect.side_effect = socket.error
            mg_globals.app_config = {
                "email_debug_mode": False,
                "email_smtp_use_ssl": False,
                "email_smtp_host": "",
                "email_smtp_port": 0}
            common.TESTS_ENABLED = False
            mail.send_email("", "", "", "")
