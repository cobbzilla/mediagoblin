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

import argparse
import os.path
import logging
import datetime
import celery

import six

from celery import group, chord
from mediagoblin import mg_globals as mgg
from mediagoblin.processing import (
    FilenameBuilder, BaseProcessingFail,
    ProgressCallback, MediaProcessor,
    ProcessingManager, request_from_args,
    get_process_filename, store_public,
    copy_original, get_entry_and_processing_manager)
from mediagoblin.processing.task import ProcessMedia
from mediagoblin.tools.translate import lazy_pass_to_ugettext as _
from mediagoblin.media_types import MissingComponents

from . import transcoders
from .util import skip_transcode, ACCEPTED_RESOLUTIONS

_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)

MEDIA_TYPE = 'mediagoblin.media_types.video'


class VideoTranscodingFail(BaseProcessingFail):
    '''
    Error raised if video transcoding fails
    '''
    general_message = _(u'Video transcoding failed')


def sniffer(media_file):
    '''New style sniffer, used in two-steps check; requires to have .name'''
    _log.info('Sniffing {0}'.format(MEDIA_TYPE))
    try:
        data = transcoders.discover(media_file.name)
    except Exception as e:
        # this is usually GLib.GError, but we don't really care which one
        _log.warning(u'GStreamer: {0}'.format(six.text_type(e)))
        raise MissingComponents(u'GStreamer: {0}'.format(six.text_type(e)))
    _log.debug('Discovered: {0}'.format(data))

    if not data.get_video_streams():
        raise MissingComponents('No video streams found in this video')

    if data.get_result() != 0:  # it's 0 if success
        try:
            missing = data.get_misc().get_string('name')
            _log.warning('GStreamer: missing {0}'.format(missing))
        except AttributeError as e:
            # AttributeError happens here on gstreamer >1.4, when get_misc
            # returns None. There is a special function to get info about
            # missing plugin. This info should be printed to logs for admin and
            # showed to the user in a short and nice version
            details = data.get_missing_elements_installer_details()
            _log.warning('GStreamer: missing: {0}'.format(', '.join(details)))
            missing = u', '.join([u'{0} ({1})'.format(*d.split('|')[3:])
                                  for d in details])
        raise MissingComponents(u'{0} is missing'.format(missing))

    return MEDIA_TYPE


def sniff_handler(media_file, filename):
    try:
        return sniffer(media_file)
    except:
        _log.error('Could not discover {0}'.format(filename))
        return None

def get_tags(stream_info):
    'gets all tags and their values from stream info'
    taglist = stream_info.get_tags()
    if not taglist:
        return {}
    tags = []
    taglist.foreach(
            lambda list, tag: tags.append((tag, list.get_value_index(tag, 0))))
    tags = dict(tags)

    # date/datetime should be converted from GDate/GDateTime to strings
    if 'date' in tags:
        date = tags['date']
        tags['date'] = "%s-%s-%s" % (
                date.year, date.month, date.day)

    if 'datetime' in tags:
        # TODO: handle timezone info; gst.get_time_zone_offset +
        # python's tzinfo should help
        dt = tags['datetime']
        tags['datetime'] = datetime.datetime(
            dt.get_year(), dt.get_month(), dt.get_day(), dt.get_hour(),
            dt.get_minute(), dt.get_second(),
            dt.get_microsecond()).isoformat()
    for k, v in tags.copy().items():
        # types below are accepted by json; others must not present
        if not isinstance(v, (dict, list, six.string_types, int, float, bool,
                              type(None))):
            del tags[k]
    return dict(tags)

def store_metadata(media_entry, metadata):
    """
    Store metadata from this video for this media entry.
    """
    stored_metadata = dict()
    audio_info_list = metadata.get_audio_streams()
    if audio_info_list:
        stored_metadata['audio'] = []
    for audio_info in audio_info_list:
        stored_metadata['audio'].append(
                {
                    'channels': audio_info.get_channels(),
                    'bitrate': audio_info.get_bitrate(),
                    'depth': audio_info.get_depth(),
                    'languange': audio_info.get_language(),
                    'sample_rate': audio_info.get_sample_rate(),
                    'tags': get_tags(audio_info)
                })

    video_info_list = metadata.get_video_streams()
    if video_info_list:
        stored_metadata['video'] = []
    for video_info in video_info_list:
        stored_metadata['video'].append(
                {
                    'width': video_info.get_width(),
                    'height': video_info.get_height(),
                    'bitrate': video_info.get_bitrate(),
                    'depth': video_info.get_depth(),
                    'videorate': [video_info.get_framerate_num(),
                                  video_info.get_framerate_denom()],
                    'tags': get_tags(video_info)
                })

    stored_metadata['common'] = {
        'duration': metadata.get_duration(),
        'tags': get_tags(metadata),
    }
    # Only save this field if there's something to save
    if len(stored_metadata):
        media_entry.media_data_init(orig_metadata=stored_metadata)

# =====================


@celery.task()
def main_task(entry_id, resolution, medium_size, **process_info):
    entry, manager = get_entry_and_processing_manager(entry_id)
    print "\nEntered main_task\n"
    with CommonVideoProcessor(manager, entry) as processor:
        processor.common_setup(resolution)
        processor.transcode(medium_size=tuple(medium_size), vp8_quality=process_info['vp8_quality'],
                            vp8_threads=process_info['vp8_threads'], vorbis_quality=process_info['vorbis_quality'])
        processor.generate_thumb(thumb_size=process_info['thumb_size'])
        processor.store_orig_metadata()
        print "\nExited main_task\n"


@celery.task()
def complimentary_task(entry_id, resolution, medium_size, **process_info):    
    entry, manager = get_entry_and_processing_manager(entry_id)
    print "\nEntered complimentary_task\n"
    with CommonVideoProcessor(manager, entry) as processor:
        processor.common_setup(resolution)
        processor.transcode(medium_size=tuple(medium_size), vp8_quality=process_info['vp8_quality'],
                            vp8_threads=process_info['vp8_threads'], vorbis_quality=process_info['vorbis_quality'])
        print "\nExited complimentary_task\n"


@celery.task()
def processing_cleanup(entry_id):
    print "\nEnter processing_cleanup()\n"
    entry, manager = get_entry_and_processing_manager(entry_id)
    with CommonVideoProcessor(manager, entry) as processor:
        processor.delete_queue_file()
        print "\nDeleted queue_file\n"

# =====================


class CommonVideoProcessor(MediaProcessor):
    """
    Provides a base for various video processing steps
    """
    acceptable_files = ['original, best_quality', 'webm_144p', 'webm_360p',
                        'webm_480p', 'webm_720p', 'webm_1080p', 'webm_video'] 

    def common_setup(self, resolution=None):
        self.video_config = mgg \
            .global_config['plugins'][MEDIA_TYPE]

        # Pull down and set up the processing file
        self.process_filename = get_process_filename(
            self.entry, self.workbench, self.acceptable_files)
        self.name_builder = FilenameBuilder(self.process_filename)
        
        self.transcoder = transcoders.VideoTranscoder()
        self.did_transcode = False

        if resolution:
            self.curr_file = 'webm_' + str(resolution)
            self.part_filename = (self.name_builder.fill('{basename}.' +
                                  str(resolution) + '.webm'))
        else:
            self.curr_file = 'webm_video'
            self.part_filename = self.name_builder.fill('{basename}.medium.webm')

        print self.curr_file, ":      Done common_setup()"

    def copy_original(self):
        # If we didn't transcode, then we need to keep the original
        raise NotImplementedError

    def _keep_best(self):
        """
        If there is no original, keep the best file that we have
        """
        raise NotImplementedError

    def _skip_processing(self, keyname, **kwargs):
        file_metadata = self.entry.get_file_metadata(keyname)

        if not file_metadata:
            return False
        skip = True

        if 'webm' in keyname:
            if kwargs.get('medium_size') != file_metadata.get('medium_size'):
                skip = False
            elif kwargs.get('vp8_quality') != file_metadata.get('vp8_quality'):
                skip = False
            elif kwargs.get('vp8_threads') != file_metadata.get('vp8_threads'):
                skip = False
            elif kwargs.get('vorbis_quality') != \
                    file_metadata.get('vorbis_quality'):
                skip = False
        elif keyname == 'thumb':
            if kwargs.get('thumb_size') != file_metadata.get('thumb_size'):
                skip = False

        return skip


    def transcode(self, medium_size=None, vp8_quality=None, vp8_threads=None,
                  vorbis_quality=None):
        print self.curr_file, ":      Enter transcode"
        progress_callback = ProgressCallback(self.entry)
        tmp_dst = os.path.join(self.workbench.dir, self.part_filename)

        if not medium_size:
            medium_size = (
                mgg.global_config['media:medium']['max_width'],
                mgg.global_config['media:medium']['max_height'])
        if not vp8_quality:
            vp8_quality = self.video_config['vp8_quality']
        if not vp8_threads:
            vp8_threads = self.video_config['vp8_threads']
        if not vorbis_quality:
            vorbis_quality = self.video_config['vorbis_quality']

        file_metadata = {'medium_size': medium_size,
                         'vp8_threads': vp8_threads,
                         'vp8_quality': vp8_quality,
                         'vorbis_quality': vorbis_quality}

        if self._skip_processing(self.curr_file, **file_metadata):
            return

        metadata = transcoders.discover(self.process_filename)
        orig_dst_dimensions = (metadata.get_video_streams()[0].get_width(),
                               metadata.get_video_streams()[0].get_height())

        # Figure out whether or not we need to transcode this video or
        # if we can skip it
        if skip_transcode(metadata, medium_size):
            _log.debug('Skipping transcoding')

            # If there is an original and transcoded, delete the transcoded
            # since it must be of lower quality then the original
            if self.entry.media_files.get('original') and \
               self.entry.media_files.get(self.curr_file):
                self.entry.media_files[self.curr_file].delete()

        else:
            print self.curr_file, ":      ->1"
            self.transcoder.transcode(self.process_filename, tmp_dst,
                                      vp8_quality=vp8_quality,
                                      vp8_threads=vp8_threads,
                                      vorbis_quality=vorbis_quality,
                                      progress_callback=progress_callback,
                                      dimensions=tuple(medium_size))
            print self.curr_file, ":      ->2"
            if self.transcoder.dst_data:
                print self.curr_file, ":      ->3"
                # Push transcoded video to public storage
                _log.debug('Saving medium...')
                store_public(self.entry, self.curr_file, tmp_dst, self.part_filename)
                _log.debug('Saved medium')

                print self.curr_file, ":      ->4"
                # Is this the file_metadata that paroneayea was talking about?
                self.entry.set_file_metadata(self.curr_file, **file_metadata)

                self.did_transcode = True
                print self.curr_file, ":      Done transcode()"

    def generate_thumb(self, thumb_size=None):
        print self.curr_file, ":      Enter generate_thumb()"
        # Temporary file for the video thumbnail (cleaned up with workbench)
        tmp_thumb = os.path.join(self.workbench.dir,
                                 self.name_builder.fill(
                                     '{basename}.thumbnail.jpg'))

        if not thumb_size:
            thumb_size = (mgg.global_config['media:thumb']['max_width'],)

        if self._skip_processing('thumb', thumb_size=thumb_size):
            return

        # We will only use the width so that the correct scale is kept
        transcoders.capture_thumb(
            self.process_filename,
            tmp_thumb,
            thumb_size[0])

        # Checking if the thumbnail was correctly created.  If it was not,
        # then just give up.
        if not os.path.exists (tmp_thumb):
            return

        # Push the thumbnail to public storage
        _log.debug('Saving thumbnail...')
        store_public(self.entry, 'thumb', tmp_thumb,
                     self.name_builder.fill('{basename}.thumbnail.jpg'))

        self.entry.set_file_metadata('thumb', thumb_size=thumb_size)
        print self.curr_file, ":      Done generate_thumb()"

    def store_orig_metadata(self):
        print self.curr_file, ":      Enter store_orig_metadata()"
        # Extract metadata and keep a record of it
        metadata = transcoders.discover(self.process_filename)

        # metadata's stream info here is a DiscovererContainerInfo instance,
        # it gets split into DiscovererAudioInfo and DiscovererVideoInfo;
        # metadata itself has container-related data in tags, like video-codec
        store_metadata(self.entry, metadata)
        print self.curr_file, ":      Done store_orig_metadata()"


class InitialProcessor(CommonVideoProcessor):
    """
    Initial processing steps for new video
    """
    name = "initial"
    description = "Initial processing"

    @classmethod
    def media_is_eligible(cls, entry=None, state=None):
        if not state:
            state = entry.state
        return state in (
            "unprocessed", "failed")

    @classmethod
    def generate_parser(cls):
        parser = argparse.ArgumentParser(
            description=cls.description,
            prog=cls.name)

        parser.add_argument(
            '--medium_size',
            nargs=2,
            metavar=('max_width', 'max_height'),
            type=int)

        parser.add_argument(
            '--vp8_quality',
            type=int,
            help='Range 0..10')

        parser.add_argument(
            '--vp8_threads',
            type=int,
            help='0 means number_of_CPUs - 1')

        parser.add_argument(
            '--vorbis_quality',
            type=float,
            help='Range -0.1..1')

        parser.add_argument(
            '--thumb_size',
            nargs=2,
            metavar=('max_width', 'max_height'),
            type=int)

        return parser

    @classmethod
    def args_to_request(cls, args):
        return request_from_args(
            args, ['medium_size', 'vp8_quality', 'vp8_threads',
                   'vorbis_quality', 'thumb_size'])

    def process(self, medium_size=None, vp8_threads=None, vp8_quality=None,
                vorbis_quality=None, thumb_size=None, resolution=None):
        self.common_setup(resolution=resolution)
        self.store_orig_metadata()
        self.transcode(medium_size=medium_size, vp8_quality=vp8_quality,
                       vp8_threads=vp8_threads, vorbis_quality=vorbis_quality)

        self.generate_thumb(thumb_size=thumb_size)
        self.delete_queue_file()


class Resizer(CommonVideoProcessor):
    """
    Video thumbnail resizing process steps for processed media
    """
    name = 'resize'
    description = 'Resize thumbnail'
    thumb_size = 'thumb_size'

    @classmethod
    def media_is_eligible(cls, entry=None, state=None):
        if not state:
            state = entry.state
        return state in 'processed'

    @classmethod
    def generate_parser(cls):
        parser = argparse.ArgumentParser(
            description=cls.description,
            prog=cls.name)

        parser.add_argument(
            '--thumb_size',
            nargs=2,
            metavar=('max_width', 'max_height'),
            type=int)

        # Needed for gmg reprocess thumbs to work
        parser.add_argument(
            'file',
            nargs='?',
            default='thumb',
            choices=['thumb'])

        return parser

    @classmethod
    def args_to_request(cls, args):
        return request_from_args(
            args, ['thumb_size', 'file'])

    def process(self, thumb_size=None, file=None):
        self.common_setup()
        self.generate_thumb(thumb_size=thumb_size)


class Transcoder(CommonVideoProcessor):
    """
    Transcoding processing steps for processed video
    """
    name = 'transcode'
    description = 'Re-transcode video'

    @classmethod
    def media_is_eligible(cls, entry=None, state=None):
        if not state:
            state = entry.state
        return state in 'processed'

    @classmethod
    def generate_parser(cls):
        parser = argparse.ArgumentParser(
            description=cls.description,
            prog=cls.name)

        parser.add_argument(
            '--medium_size',
            nargs=2,
            metavar=('max_width', 'max_height'),
            type=int)

        parser.add_argument(
            '--vp8_quality',
            type=int,
            help='Range 0..10')

        parser.add_argument(
            '--vp8_threads',
            type=int,
            help='0 means number_of_CPUs - 1')

        parser.add_argument(
            '--vorbis_quality',
            type=float,
            help='Range -0.1..1')

        return parser

    @classmethod
    def args_to_request(cls, args):
        return request_from_args(
            args, ['medium_size', 'vp8_threads', 'vp8_quality',
                   'vorbis_quality'])

    def process(self, medium_size=None, vp8_quality=None, vp8_threads=None,
                vorbis_quality=None):
        self.common_setup()
        self.transcode(medium_size=medium_size, vp8_threads=vp8_threads,
                       vp8_quality=vp8_quality, vorbis_quality=vorbis_quality)


class VideoProcessingManager(ProcessingManager):
    def __init__(self):
        super(VideoProcessingManager, self).__init__()
        self.add_processor(InitialProcessor)
        self.add_processor(Resizer)
        self.add_processor(Transcoder)

    def workflow(self, entry_id, feed_url, reprocess_action, reprocess_info=None):

        reprocess_info = reprocess_info or {}
        if 'vp8_quality' not in reprocess_info:
            reprocess_info['vp8_quality'] = None
        if 'vorbis_quality' not in reprocess_info:
            reprocess_info['vorbis_quality'] = None
        if 'vp8_threads' not in reprocess_info:
            reprocess_info['vp8_threads'] = None
        if 'thumb_size' not in reprocess_info:
            reprocess_info['thumb_size'] = None

        transcoding_tasks = group([
            main_task.signature(args=(entry_id, '480p', ACCEPTED_RESOLUTIONS['480p']),
                                kwargs=reprocess_info, queue='default',
                                priority=5, immutable=True),
        ])

        cleanup_task = processing_cleanup.signature(args=(entry_id,),
                                                    queue='default', immutable=True)

        """
            complimentary_task.signature(args=(entry_id, '360p', ACCEPTED_RESOLUTIONS['360p']),
                                         kwargs=reprocess_info, queue='default',
                                         priority=4, immutable=True),
            complimentary_task.signature(args=(entry_id, '720p', ACCEPTED_RESOLUTIONS['720p']),
                                         kwargs=reprocess_info, queue='default',
                                         priority=3, immutable=True),
        main_task.apply_async(args=(entry_id, '480p', ACCEPTED_RESOLUTIONS['480p']),
                              kwargs=reprocess_info, queue='default',
                              priority=5, immutable=True)
        processing_cleanup.apply_async(args=(entry_id,), queue='default', immutable=True)
        """

        chord(transcoding_tasks)(cleanup_task)

        # main_task(entry_id, '480p', ACCEPTED_RESOLUTIONS['480p'], **reprocess_info)
        # processing_cleanup(entry_id)
