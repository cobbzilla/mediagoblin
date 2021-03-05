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

from urllib import request, parse

import celery
from celery.registry import tasks

from mediagoblin import mg_globals as mgg
from . import mark_entry_failed, BaseProcessingFail
from mediagoblin.tools.processing import json_processing_callback
from mediagoblin.processing import get_entry_and_processing_manager

_log = logging.getLogger(__name__)
logging.basicConfig()
_log.setLevel(logging.DEBUG)


@celery.task(default_retry_delay=2 * 60)
def handle_push_urls(feed_url):
    """Subtask, notifying the PuSH servers of new content

    Retry 3 times every 2 minutes if run in separate process before failing."""
    if not mgg.app_config["push_urls"]:
        return # Nothing to do
    _log.debug('Notifying Push servers for feed {}'.format(feed_url))
    hubparameters = {
        'hub.mode': 'publish',
        'hub.url': feed_url}
    hubdata = parse.urlencode(hubparameters)
    hubheaders = {
        "Content-type": "application/x-www-form-urlencoded",
        "Connection": "close"}
    for huburl in mgg.app_config["push_urls"]:
        hubrequest = request.Request(huburl, hubdata, hubheaders)
        try:
            hubresponse = request.urlopen(hubrequest)
        except (request.HTTPError, request.URLError) as exc:
            # We retry by default 3 times before failing
            _log.info("PuSH url %r gave error %r", huburl, exc)
            try:
                return handle_push_urls.retry(exc=exc, throw=False)
            except Exception as e:
                # All retries failed, Failure is no tragedy here, probably.
                _log.warn('Failed to notify PuSH server for feed {}. '
                          'Giving up.'.format(feed_url))
                return False


################################
# Media processing initial steps
################################
class ProcessMedia(celery.Task):
    """
    Pass this entry off for processing.
    """

    name = 'process_media'

    def run(self, media_id, feed_url, reprocess_action, reprocess_info=None):
        """
        Pass the media entry off to the appropriate processing function
        (for now just process_image...)

        :param media_id: MediaEntry().id
        :param feed_url: The feed URL that the PuSH server needs to be
            updated for.
        :param reprocess_action: What particular action should be run. For
            example, 'initial'.
        :param reprocess: A dict containing all of the necessary reprocessing
            info for the media_type.
        """
        reprocess_info = reprocess_info or {}
        entry, manager = get_entry_and_processing_manager(media_id)

        # Try to process, and handle expected errors.
        try:
            processor_class = manager.get_processor(reprocess_action, entry)

            with processor_class(manager, entry) as processor:
                # Initial state change has to be here because
                # the entry.state gets recorded on processor_class init
                entry.state = 'processing'
                entry.save()

                _log.debug('Processing {}'.format(entry))

                try:
                    processor.process(**reprocess_info)
                except Exception as exc:
                    if processor.entry_orig_state == 'processed':
                        _log.error(
                            'Entry {} failed to process due to the following'
                            ' error: {}'.format(entry.id, exc))
                        _log.info(
                            'Setting entry.state back to "processed"')
                        pass
                    else:
                        raise

            # We set the state to processed and save the entry here so there's
            # no need to save at the end of the processing stage, probably ;)
            entry.state = 'processed'
            entry.save()

            # Notify the PuSH servers as async task
            if mgg.app_config["push_urls"] and feed_url:
                handle_push_urls.subtask().delay(feed_url)

            json_processing_callback(entry)
        except BaseProcessingFail as exc:
            mark_entry_failed(entry.id, exc)
            json_processing_callback(entry)
            return

        except ImportError as exc:
            _log.error(
                'Entry {} failed to process due to an import error: {}'\
                    .format(
                    entry.title,
                    exc))

            mark_entry_failed(entry.id, exc)
            json_processing_callback(entry)

        except Exception as exc:
            _log.error('An unhandled exception was raised while'
                    + ' processing {}'.format(
                        entry))

            mark_entry_failed(entry.id, exc)
            json_processing_callback(entry)
            raise

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """
        If the processing failed we should mark that in the database.

        Assuming that the exception raised is a subclass of
        BaseProcessingFail, we can use that to get more information
        about the failure and store that for conveying information to
        users about the failure, etc.
        """
        entry_id = args[0]
        mark_entry_failed(entry_id, exc)

        entry = mgg.database.MediaEntry.query.filter_by(id=entry_id).first()
        json_processing_callback(entry)
        mgg.database.reset_after_request()

    def after_return(self, *args, **kwargs):
        """
        This is called after the task has returned, we should clean up.

        We need to rollback the database to prevent ProgrammingError exceptions
        from being raised.
        """
        # In eager mode we get DetachedInstanceError, we do rollback on_failure
        # to deal with that case though when in eager mode.
        if not celery.app.default_app.conf['CELERY_ALWAYS_EAGER']:
            mgg.database.reset_after_request()


tasks.register(ProcessMedia)
