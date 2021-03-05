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

from mediagoblin import mg_globals as mgg
from mediagoblin.media_types import MediaManagerBase
from mediagoblin.media_types.video.processing import (VideoProcessingManager,
        sniff_handler, sniffer)


MEDIA_TYPE = 'mediagoblin.media_types.video'
ACCEPTED_EXTENSIONS = [
        "mp4", "mov", "webm", "avi", "3gp", "3gpp", "mkv", "ogv", "m4v"]


class VideoMediaManager(MediaManagerBase):
    human_readable = "Video"
    display_template = "mediagoblin/media_displays/video.html"
    default_thumb = "images/media_thumbs/video.jpg"
    type_icon = "images/type_icons/video.png"

    # Used by the media_entry.get_display_media method
    default_webm_type = 'video/webm; codecs="vp8, vorbis"'

    @property
    def media_fetch_order(self):
        video_config = mgg.global_config['plugins'][MEDIA_TYPE]
        video_res = video_config['available_resolutions']
        video_res.remove(video_config['default_resolution'])
        video_res.insert(0, video_config['default_resolution'])
        video_res = ['webm_{}'.format(x) for x in video_res]
        return (['webm_video'] + video_res + ['original'])


def get_media_type_and_manager(ext):
    if ext in ACCEPTED_EXTENSIONS:
        return MEDIA_TYPE, VideoMediaManager

def type_match_handler(ext):
    if ext in ACCEPTED_EXTENSIONS:
        return MEDIA_TYPE, VideoMediaManager, sniffer

hooks = {
    'type_match_handler': type_match_handler,
    'sniff_handler': sniff_handler,
    ('media_manager', MEDIA_TYPE): lambda: VideoMediaManager,
    ('reprocess_manager', MEDIA_TYPE): lambda: VideoProcessingManager,
}
