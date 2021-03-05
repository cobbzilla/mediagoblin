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

import os
import sys
import datetime
import logging

from celery import Celery
from kombu import Exchange, Queue
from mediagoblin.tools.pluginapi import hook_runall


_log = logging.getLogger(__name__)


MANDATORY_CELERY_IMPORTS = [
    'mediagoblin.processing.task',
    'mediagoblin.notifications.task',
    'mediagoblin.submit.task',
    'mediagoblin.media_types.video.processing',
]

DEFAULT_SETTINGS_MODULE = 'mediagoblin.init.celery.dummy_settings_module'


def get_celery_settings_dict(app_config, global_config,
                             force_celery_always_eager=False):
    """
    Get a celery settings dictionary from reading the config
    """
    if 'celery' in global_config:
        celery_conf = global_config['celery']
    else:
        celery_conf = {}

    # Add x-max-priority to config
    celery_conf['CELERY_QUEUES'] = (
        Queue('default', Exchange('default'), routing_key='default',
              queue_arguments={'x-max-priority': 10}),
    )

    celery_settings = {}

    # Add all celery settings from config
    for key, value in celery_conf.items():
        celery_settings[key] = value

    # TODO: use default result stuff here if it exists

    # add mandatory celery imports
    celery_imports = celery_settings.setdefault('CELERY_IMPORTS', [])
    celery_imports.extend(MANDATORY_CELERY_IMPORTS)

    if force_celery_always_eager:
        celery_settings['CELERY_ALWAYS_EAGER'] = True
        celery_settings['CELERY_EAGER_PROPAGATES_EXCEPTIONS'] = True

    # Garbage collection periodic task
    frequency = app_config.get('garbage_collection', 60)
    if frequency:
        frequency = int(frequency)
        celery_settings['CELERYBEAT_SCHEDULE'] = {
            'garbage-collection': {
                'task': 'mediagoblin.submit.task.collect_garbage',
                'schedule': datetime.timedelta(minutes=frequency),
            }
        }

    return celery_settings


def setup_celery_app(app_config, global_config,
                     settings_module=DEFAULT_SETTINGS_MODULE,
                     force_celery_always_eager=False):
    """
    Setup celery without using terrible setup-celery-module hacks.
    """
    celery_settings = get_celery_settings_dict(
        app_config, global_config, force_celery_always_eager)
    celery_app = Celery()
    celery_app.config_from_object(celery_settings)

    hook_runall('celery_setup', celery_app)


def setup_celery_from_config(app_config, global_config,
                             settings_module=DEFAULT_SETTINGS_MODULE,
                             force_celery_always_eager=False,
                             set_environ=True):
    """
    Take a mediagoblin app config and try to set up a celery settings
    module from this.

    Args:
    - app_config: the application config section
    - global_config: the entire ConfigObj loaded config, all sections
    - settings_module: the module to populate, as a string
    - force_celery_always_eager: whether or not to force celery into
      always eager mode; good for development and small installs
    - set_environ: if set, this will CELERY_CONFIG_MODULE to the
      settings_module
    """
    celery_settings = get_celery_settings_dict(
        app_config, global_config, force_celery_always_eager)

    __import__(settings_module)
    this_module = sys.modules[settings_module]

    for key, value in celery_settings.items():
        setattr(this_module, key, value)

    if set_environ:
        os.environ['CELERY_CONFIG_MODULE'] = settings_module

    # Replace the default celery.current_app.conf if celery has already been
    # initiated
    from celery import current_app

    _log.info('Setting celery configuration from object "{}"'.format(
        settings_module))
    current_app.config_from_object(this_module)

    _log.debug('Celery broker host: {}'.format(current_app.conf['BROKER_HOST']))
