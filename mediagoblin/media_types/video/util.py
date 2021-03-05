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

from mediagoblin import mg_globals as mgg

ACCEPTED_RESOLUTIONS = {
    '144p': (256, 144),
    '240p': (352, 240),
    '360p': (480, 360),
    '480p': (858, 480),
    '720p': (1280, 720),
    '1080p': (1920, 1080),
    'webm': (640, 640),
}

_log = logging.getLogger(__name__)


def skip_transcode(metadata, size):
    '''
    Checks video metadata against configuration values for skip_transcode.

    Returns True if the video matches the requirements in the configuration.
    '''
    config = mgg.global_config['plugins']['mediagoblin.media_types.video']\
            ['skip_transcode']

    # XXX: how were we supposed to use it?
    medium_config = mgg.global_config['media:medium']

    _log.debug('skip_transcode config: {}'.format(config))

    metadata_tags = metadata.get_tags()
    if not metadata_tags:
        return False

    if config['mime_types'] and metadata_tags.get_string('mimetype')[0]:
        if not metadata_tags.get_string('mimetype')[1] in config['mime_types']:
            return False

    if (config['container_formats'] and
            metadata_tags.get_string('container-format')[0]):
        if not (metadata_tags.get_string('container-format')[1] in
                config['container_formats']):
            return False

    if config['video_codecs']:
        for video_info in metadata.get_video_streams():
            video_tags = video_info.get_tags()
            if not video_tags:
                return False
            if not (video_tags.get_string('video-codec')[1] in
                    config['video_codecs']):
                return False

    if config['audio_codecs']:
        for audio_info in metadata.get_audio_streams():
            audio_tags = audio_info.get_tags()
            if not audio_tags:
                return False
            if not (audio_tags.get_string('audio-codec')[1] in
                    config['audio_codecs']):
                return False

    if config['dimensions_match']:
        for video_info in metadata.get_video_streams():
            if not video_info.get_height() <= size[1]:
                return False
            if not video_info.get_width() <= size[0]:
                return False

    return True
