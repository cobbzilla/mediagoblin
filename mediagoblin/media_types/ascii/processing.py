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
import chardet
import os
try:
    from PIL import Image
except ImportError:
    import Image
import logging

from mediagoblin import mg_globals as mgg
from mediagoblin.processing import (
    create_pub_filepath, FilenameBuilder,
    MediaProcessor, ProcessingManager,
    get_process_filename, copy_original,
    store_public, request_from_args)
from mediagoblin.media_types.ascii import asciitoimage

_log = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = ['txt', 'asc', 'nfo']
MEDIA_TYPE = 'mediagoblin.media_types.ascii'


def sniff_handler(media_file, filename):
    _log.info('Sniffing {}'.format(MEDIA_TYPE))

    name, ext = os.path.splitext(filename)
    clean_ext = ext[1:].lower()

    if clean_ext in SUPPORTED_EXTENSIONS:
        return MEDIA_TYPE

    return None


class CommonAsciiProcessor(MediaProcessor):
    """
    Provides a base for various ascii processing steps
    """
    acceptable_files = ['original', 'unicode']

    def common_setup(self):
        self.ascii_config = mgg.global_config['plugins'][
            'mediagoblin.media_types.ascii']

         # Conversions subdirectory to avoid collisions
        self.conversions_subdir = os.path.join(
            self.workbench.dir, 'conversions')
        os.mkdir(self.conversions_subdir)

        # Pull down and set up the processing file
        self.process_filename = get_process_filename(
            self.entry, self.workbench, self.acceptable_files)
        self.name_builder = FilenameBuilder(self.process_filename)

        self.charset = None

    def copy_original(self):
        copy_original(
            self.entry, self.process_filename,
            self.name_builder.fill('{basename}{ext}'))

    def _detect_charset(self, orig_file):
        d_charset = chardet.detect(orig_file.read())

        # Only select a non-utf-8 charset if chardet is *really* sure
        # Tested with "Feli\x0109an superjaron", which was detected
        if d_charset['confidence'] < 0.9:
            self.charset = 'utf-8'
        else:
            self.charset = d_charset['encoding']

        _log.info('Charset detected: {}\nWill interpret as: {}'.format(
                  d_charset,
                  self.charset))

        # Rewind the file
        orig_file.seek(0)

    def store_unicode_file(self):
        with open(self.process_filename, 'rb') as orig_file:
            self._detect_charset(orig_file)
            unicode_filepath = create_pub_filepath(self.entry,
                                                   'ascii-portable.txt')

            with mgg.public_store.get_file(unicode_filepath, 'wb') \
                    as unicode_file:
                # Decode the original file from its detected charset (or UTF8)
                # Encode the unicode instance to ASCII and replace any
                # non-ASCII with an HTML entity (&#
                unicode_file.write(
                    str(orig_file.read().decode(
                            self.charset)).encode(
                                'ascii',
                                'xmlcharrefreplace'))

        self.entry.media_files['unicode'] = unicode_filepath

    def generate_thumb(self, font=None, thumb_size=None):
        with open(self.process_filename, 'rb') as orig_file:
            # If no font kwarg, check config
            if not font:
                font = self.ascii_config.get('thumbnail_font', None)
            if not thumb_size:
                thumb_size = (mgg.global_config['media:thumb']['max_width'],
                              mgg.global_config['media:thumb']['max_height'])

            if self._skip_resizing(font, thumb_size):
                return

            tmp_thumb = os.path.join(
                self.conversions_subdir,
                self.name_builder.fill('{basename}.thumbnail.png'))

            ascii_converter_args = {}

            # If there is a font from either the config or kwarg, update
            # ascii_converter_args
            if font:
                ascii_converter_args.update(
                    {'font': self.ascii_config['thumbnail_font']})

            converter = asciitoimage.AsciiToImage(
                **ascii_converter_args)

            thumb = converter._create_image(
                orig_file.read())

            thumb.thumbnail(thumb_size, Image.ANTIALIAS)
            thumb.save(tmp_thumb);

            thumb_info = {'font': font,
                          'width': thumb_size[0],
                          'height': thumb_size[1]}

            _log.debug('Copying local file to public storage')
            store_public(self.entry, 'thumb', tmp_thumb,
                         self.name_builder.fill('{basename}.thumbnail.jpg'))

            self.entry.set_file_metadata('thumb', **thumb_info)


    def _skip_resizing(self, font, thumb_size):
        thumb_info = self.entry.get_file_metadata('thumb')

        if not thumb_info:
            return False

        skip = True

        if thumb_info.get('font') != font:
            skip = False
        elif thumb_info.get('width') != thumb_size[0]:
            skip = False
        elif thumb_info.get('height') != thumb_size[1]:
            skip = False

        return skip


class InitialProcessor(CommonAsciiProcessor):
    """
    Initial processing step for new ascii media
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
            '--thumb_size',
            nargs=2,
            metavar=('max_width', 'max_width'),
            type=int)

        parser.add_argument(
            '--font',
            help='the thumbnail font')

        return parser

    @classmethod
    def args_to_request(cls, args):
        return request_from_args(
            args, ['thumb_size', 'font'])

    def process(self, thumb_size=None, font=None):
        self.common_setup()
        self.store_unicode_file()
        self.generate_thumb(thumb_size=thumb_size, font=font)
        self.copy_original()
        self.delete_queue_file()


class Resizer(CommonAsciiProcessor):
    """
    Resizing process steps for processed media
    """
    name = 'resize'
    description = 'Resize thumbnail'
    thumb_size = 'thumb_size'

    @classmethod
    def media_is_eligible(cls, entry=None, state=None):
        """
        Determine if this media type is eligible for processing
        """
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


class AsciiProcessingManager(ProcessingManager):
    def __init__(self):
        super().__init__()
        self.add_processor(InitialProcessor)
        self.add_processor(Resizer)
