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

import copy
import logging
import os
import pkg_resources

from configobj import ConfigObj, flatten_errors
from validate import Validator


_log = logging.getLogger(__name__)


CONFIG_SPEC_PATH = pkg_resources.resource_filename(
    'mediagoblin', 'config_spec.ini')


def _setup_defaults(config, config_path, extra_defaults=None):
    """
    Setup DEFAULTS in a config object from an (absolute) config_path.
    """
    extra_defaults = extra_defaults or {}

    config.setdefault('DEFAULT', {})
    config['DEFAULT']['here'] = os.path.dirname(config_path)
    config['DEFAULT']['__file__'] = config_path

    for key, value in extra_defaults.items():
        config['DEFAULT'].setdefault(key, value)


def read_mediagoblin_config(config_path, config_spec_path=CONFIG_SPEC_PATH):
    """
    Read a config object from config_path.

    Does automatic value transformation based on the config_spec.
    Also provides %(__file__)s and %(here)s values of this file and
    its directory respectively similar to paste deploy.

    Also reads for [plugins] section, appends all config_spec.ini
    files from said plugins into the general config_spec specification.

    This function doesn't itself raise any exceptions if validation
    fails, you'll have to do something

    Args:
     - config_path: path to the config file
     - config_spec_path: config file that provides defaults and value types
       for validation / conversion.  Defaults to mediagoblin/config_spec.ini

    Returns:
      A tuple like: (config, validation_result)
      ... where 'conf' is the parsed config object and 'validation_result'
      is the information from the validation process.
    """
    config_path = os.path.abspath(config_path)

    # PRE-READ of config file.  This allows us to fetch the plugins so
    # we can add their plugin specs to the general config_spec.
    config = ConfigObj(
        config_path,
        interpolation="ConfigParser")

    # temporary bootstrap, just setup here and __file__... we'll do this again
    _setup_defaults(config, config_path)

    # Now load the main config spec
    config_spec = ConfigObj(
        config_spec_path,
        encoding="UTF8", list_values=False, _inspec=True)

    # HACK to get MediaGoblin running under Docker/Python 3. Without this line,
    # `./bin/gmg dbupdate` fails as the configuration under 'DEFAULT' in
    # config_spec still had %(here)s markers in it, when these should have been
    # replaced with actual paths, resulting in
    # "configobj.MissingInterpolationOption: missing option "here" in
    # interpolation". This issue doesn't seem to appear when running on Guix,
    # but adding this line also doesn't appear to cause problems on Guix.
    _setup_defaults(config_spec, config_path)

    # Set up extra defaults that will be pushed into the rest of the
    # configs.  This is a combined extrapolation of defaults based on
    mainconfig_defaults = copy.copy(config_spec.get("DEFAULT", {}))
    mainconfig_defaults.update(config["DEFAULT"])

    plugins = config.get("plugins", {}).keys()
    plugin_configs = {}

    for plugin in plugins:
        try:
            plugin_config_spec_path = pkg_resources.resource_filename(
                plugin, "config_spec.ini")
            if not os.path.exists(plugin_config_spec_path):
                continue

            plugin_config_spec = ConfigObj(
                plugin_config_spec_path,
                encoding="UTF8", list_values=False, _inspec=True)
            _setup_defaults(
                plugin_config_spec, config_path, mainconfig_defaults)

            if not "plugin_spec" in plugin_config_spec:
                continue

            plugin_configs[plugin] = plugin_config_spec["plugin_spec"]

        except ImportError:
            _log.warning(
                "When setting up config section, could not import '%s'" %
                plugin)

    # append the plugin specific sections of the config spec
    config_spec["plugins"] = plugin_configs

    _setup_defaults(config_spec, config_path, mainconfig_defaults)

    config = ConfigObj(
        config_path,
        configspec=config_spec,
        encoding="UTF8",
        interpolation="ConfigParser")

    _setup_defaults(config, config_path, mainconfig_defaults)

    # For now the validator just works with the default functions,
    # but in the future if we want to add additional validation/configuration
    # functions we'd add them to validator.functions here.
    #
    # See also:
    #   http://www.voidspace.org.uk/python/validate.html#adding-functions
    validator = Validator()
    validation_result = config.validate(validator, preserve_errors=True)

    return config, validation_result


REPORT_HEADER = """\
There were validation problems loading this config file:
--------------------------------------------------------
"""


def generate_validation_report(config, validation_result):
    """
    Generate a report if necessary of problems while validating.

    Returns:
      Either a string describing for a user the problems validating
      this config or None if there are no problems.
    """
    report = []

    # Organize the report
    for entry in flatten_errors(config, validation_result):
        # each entry is a tuple
        section_list, key, error = entry

        if key is not None:
            section_list.append(key)
        else:
            section_list.append('[missing section]')

        section_string = ':'.join(section_list)

        if error == False:
            # We don't care about missing values for now.
            continue

        report.append("{} = {}".format(section_string, error))

    if report:
        return REPORT_HEADER + "\n".join(report)
    else:
        return None
